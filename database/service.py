"""MongoDB database service using Motor async driver."""
import logging
from datetime import datetime
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId

from config import get_settings
from database.models import (
    User, EpicAccount, BotSession, CosmeticPreset, 
    CosmeticCache, ActivityLog, CurrentCosmetics
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """Async MongoDB database service."""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
    
    async def connect(self) -> None:
        """Connect to MongoDB."""
        settings = get_settings()
        self.client = AsyncIOMotorClient(settings.mongodb_uri)
        self.db = self.client.fortnite_bots
        await self._ensure_indexes()
        logger.info("Connected to MongoDB")
    
    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    async def _ensure_indexes(self) -> None:
        """Create required indexes for performance."""
        # Users
        await self.db.users.create_index("discord_id", unique=True)
        
        # Epic Accounts
        await self.db.epic_accounts.create_index("discord_id")
        await self.db.epic_accounts.create_index("epic_account_id", unique=True)
        await self.db.epic_accounts.create_index([("epic_username", 1), ("discord_id", 1)])
        
        # Bot Sessions
        await self.db.bot_sessions.create_index("discord_id")
        await self.db.bot_sessions.create_index("account_id")
        await self.db.bot_sessions.create_index("last_activity")
        await self.db.bot_sessions.create_index("status")
        
        # Cosmetic Presets
        await self.db.cosmetic_presets.create_index("discord_id")
        await self.db.cosmetic_presets.create_index([("name", 1), ("discord_id", 1)])
        
        # Cosmetic Cache
        await self.db.cosmetic_cache.create_index([("type", 1), ("cosmetic_id", 1)], unique=True)
        await self.db.cosmetic_cache.create_index([("type", 1), ("search_text", 1)])
        
        # Activity Log
        await self.db.activity_log.create_index("discord_id")
        await self.db.activity_log.create_index([("timestamp", -1)])
        
        logger.info("Database indexes ensured")
    
    # User Operations
    async def get_or_create_user(self, discord_id: str, discord_username: str) -> User:
        """Get existing user or create new one."""
        user_data = await self.db.users.find_one({"discord_id": discord_id})
        
        if user_data:
            # Update last active and username
            await self.db.users.update_one(
                {"discord_id": discord_id},
                {"$set": {"last_active": datetime.utcnow(), "discord_username": discord_username}}
            )
            return User(**user_data)
        
        # Create new user
        new_user = User(
            discord_id=discord_id,
            discord_username=discord_username
        )
        result = await self.db.users.insert_one(new_user.model_dump(by_alias=True, exclude={"id"}))
        new_user.id = result.inserted_id
        logger.info(f"Created new user: {discord_id}")
        return new_user
    
    async def update_user_channel(self, discord_id: str, channel_id: str) -> None:
        """Update user's last active channel for notifications."""
        await self.db.users.update_one(
            {"discord_id": discord_id},
            {"$set": {"last_active_channel_id": channel_id, "last_active": datetime.utcnow()}}
        )
    
    async def get_user(self, discord_id: str) -> Optional[User]:
        """Get user by Discord ID."""
        user_data = await self.db.users.find_one({"discord_id": discord_id})
        return User(**user_data) if user_data else None
    
    # Epic Account Operations
    async def add_epic_account(
        self,
        discord_id: str,
        epic_username: str,
        epic_display_name: str,
        epic_account_id: str,
        encrypted_credentials: str
    ) -> EpicAccount:
        """Add a new Epic Games account."""
        account = EpicAccount(
            discord_id=discord_id,
            epic_username=epic_username,
            epic_display_name=epic_display_name,
            epic_account_id=epic_account_id,
            encrypted_credentials=encrypted_credentials
        )
        result = await self.db.epic_accounts.insert_one(account.model_dump(by_alias=True, exclude={"id"}))
        account.id = result.inserted_id
        logger.info(f"Added Epic account {epic_username} for user {discord_id}")
        return account
    
    async def get_epic_accounts(self, discord_id: str) -> List[EpicAccount]:
        """Get all Epic accounts for a user."""
        cursor = self.db.epic_accounts.find({"discord_id": discord_id})
        accounts = await cursor.to_list(length=None)
        return [EpicAccount(**acc) for acc in accounts]
    
    async def get_epic_account_by_username(self, discord_id: str, epic_username: str) -> Optional[EpicAccount]:
        """Get specific Epic account by username."""
        account_data = await self.db.epic_accounts.find_one({
            "discord_id": discord_id,
            "epic_username": {"$regex": f"^{epic_username}$", "$options": "i"}
        })
        return EpicAccount(**account_data) if account_data else None
    
    async def get_epic_account_by_id(self, account_id: ObjectId) -> Optional[EpicAccount]:
        """Get Epic account by its ObjectId."""
        account_data = await self.db.epic_accounts.find_one({"_id": account_id})
        return EpicAccount(**account_data) if account_data else None
    
    async def update_epic_account_status(self, epic_account_id: str, status: str) -> None:
        """Update Epic account status."""
        await self.db.epic_accounts.update_one(
            {"epic_account_id": epic_account_id},
            {"$set": {"status": status, "last_used": datetime.utcnow()}}
        )
    
    async def get_epic_account_by_epic_id(self, epic_account_id: str) -> Optional[EpicAccount]:
        """Get Epic account by Epic account ID (globally, not user-specific)."""
        account_data = await self.db.epic_accounts.find_one({"epic_account_id": epic_account_id})
        return EpicAccount(**account_data) if account_data else None
    
    async def remove_epic_account(self, discord_id: str, epic_username: str) -> bool:
        """Remove an Epic account."""
        result = await self.db.epic_accounts.delete_one({
            "discord_id": discord_id,
            "epic_username": {"$regex": f"^{epic_username}$", "$options": "i"}
        })
        if result.deleted_count > 0:
            logger.info(f"Removed Epic account {epic_username} for user {discord_id}")
            return True
        return False
    
    async def count_user_accounts(self, discord_id: str) -> int:
        """Count user's Epic accounts."""
        return await self.db.epic_accounts.count_documents({"discord_id": discord_id})
    
    async def increment_account_sessions(self, account_id: ObjectId) -> None:
        """Increment session count for an account."""
        await self.db.epic_accounts.update_one(
            {"_id": account_id},
            {"$inc": {"total_sessions": 1}, "$set": {"last_used": datetime.utcnow()}}
        )
    
    # Bot Session Operations
    async def create_bot_session(
        self,
        account_id: ObjectId,
        discord_id: str,
        timeout_minutes: int
    ) -> BotSession:
        """Create a new bot session."""
        session = BotSession(
            account_id=account_id,
            discord_id=discord_id,
            timeout_minutes=timeout_minutes
        )
        result = await self.db.bot_sessions.insert_one(session.model_dump(by_alias=True, exclude={"id"}))
        session.id = result.inserted_id
        
        # Increment account and user session counts
        await self.increment_account_sessions(account_id)
        await self.db.users.update_one(
            {"discord_id": discord_id},
            {"$inc": {"total_sessions": 1}}
        )
        
        logger.info(f"Created bot session for account {account_id}")
        return session
    
    async def get_active_session(self, account_id: ObjectId) -> Optional[BotSession]:
        """Get active session for an account."""
        session_data = await self.db.bot_sessions.find_one({
            "account_id": account_id,
            "status": {"$in": ["active", "idle_warning"]}
        })
        return BotSession(**session_data) if session_data else None
    
    async def get_active_sessions_for_user(self, discord_id: str) -> List[BotSession]:
        """Get all active sessions for a user."""
        cursor = self.db.bot_sessions.find({
            "discord_id": discord_id,
            "status": {"$in": ["active", "idle_warning"]}
        })
        sessions = await cursor.to_list(length=None)
        return [BotSession(**s) for s in sessions]
    
    async def get_all_active_sessions(self) -> List[BotSession]:
        """Get all active sessions across all users."""
        cursor = self.db.bot_sessions.find({
            "status": {"$in": ["active", "idle_warning"]}
        })
        sessions = await cursor.to_list(length=None)
        return [BotSession(**s) for s in sessions]
    
    async def update_session_activity(self, session_id: ObjectId) -> None:
        """Update last activity timestamp for a session."""
        await self.db.bot_sessions.update_one(
            {"_id": session_id},
            {"$set": {"last_activity": datetime.utcnow(), "status": "active"}}
        )
    
    async def update_session_status(self, session_id: ObjectId, status: str) -> None:
        """Update session status."""
        await self.db.bot_sessions.update_one(
            {"_id": session_id},
            {"$set": {"status": status}}
        )
    
    async def end_session(self, session_id: ObjectId, reason: str) -> None:
        """End a bot session."""
        await self.db.bot_sessions.update_one(
            {"_id": session_id},
            {"$set": {
                "status": "stopped",
                "ended_at": datetime.utcnow(),
                "termination_reason": reason
            }}
        )
        logger.info(f"Ended session {session_id} with reason: {reason}")
    
    async def extend_session(self, session_id: ObjectId, extension_minutes: int) -> int:
        """Extend session and return new extensions count."""
        result = await self.db.bot_sessions.find_one_and_update(
            {"_id": session_id},
            {
                "$inc": {"extensions_used": 1, "timeout_minutes": extension_minutes},
                "$set": {"last_activity": datetime.utcnow(), "status": "active"}
            },
            return_document=True
        )
        return result["extensions_used"] if result else 0
    
    async def update_session_cosmetics(self, session_id: ObjectId, cosmetics: CurrentCosmetics) -> None:
        """Update session cosmetics."""
        await self.db.bot_sessions.update_one(
            {"_id": session_id},
            {"$set": {
                "current_cosmetics": cosmetics.model_dump(),
                "last_activity": datetime.utcnow()
            }}
        )
    
    async def count_user_active_sessions(self, discord_id: str) -> int:
        """Count active sessions for a user."""
        return await self.db.bot_sessions.count_documents({
            "discord_id": discord_id,
            "status": {"$in": ["active", "idle_warning"]}
        })
    
    async def count_global_active_sessions(self) -> int:
        """Count all active sessions globally."""
        return await self.db.bot_sessions.count_documents({
            "status": {"$in": ["active", "idle_warning"]}
        })
    
    # Cosmetic Preset Operations
    async def save_preset(
        self,
        discord_id: str,
        name: str,
        cosmetics: CurrentCosmetics
    ) -> CosmeticPreset:
        """Save or update a cosmetic preset."""
        existing = await self.db.cosmetic_presets.find_one({
            "discord_id": discord_id,
            "name": {"$regex": f"^{name}$", "$options": "i"}
        })
        
        if existing:
            await self.db.cosmetic_presets.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "cosmetics": cosmetics.model_dump(),
                    "updated_at": datetime.utcnow()
                }}
            )
            return CosmeticPreset(**{**existing, "cosmetics": cosmetics})
        
        preset = CosmeticPreset(
            discord_id=discord_id,
            name=name,
            cosmetics=cosmetics
        )
        result = await self.db.cosmetic_presets.insert_one(preset.model_dump(by_alias=True, exclude={"id"}))
        preset.id = result.inserted_id
        logger.info(f"Saved preset '{name}' for user {discord_id}")
        return preset
    
    async def get_presets(self, discord_id: str) -> List[CosmeticPreset]:
        """Get all presets for a user."""
        cursor = self.db.cosmetic_presets.find({"discord_id": discord_id})
        presets = await cursor.to_list(length=None)
        return [CosmeticPreset(**p) for p in presets]
    
    async def get_preset_by_name(self, discord_id: str, name: str) -> Optional[CosmeticPreset]:
        """Get specific preset by name."""
        preset_data = await self.db.cosmetic_presets.find_one({
            "discord_id": discord_id,
            "name": {"$regex": f"^{name}$", "$options": "i"}
        })
        return CosmeticPreset(**preset_data) if preset_data else None
    
    async def delete_preset(self, discord_id: str, name: str) -> bool:
        """Delete a preset."""
        result = await self.db.cosmetic_presets.delete_one({
            "discord_id": discord_id,
            "name": {"$regex": f"^{name}$", "$options": "i"}
        })
        return result.deleted_count > 0
    
    # Cosmetic Cache Operations
    async def cache_cosmetic(self, cosmetic: CosmeticCache) -> None:
        """Cache a cosmetic item."""
        await self.db.cosmetic_cache.update_one(
            {"type": cosmetic.type, "cosmetic_id": cosmetic.cosmetic_id},
            {"$set": cosmetic.model_dump(by_alias=True, exclude={"id"})},
            upsert=True
        )
    
    async def search_cosmetics(
        self,
        cosmetic_type: str,
        query: str,
        limit: int = 25,
        skip: int = 0
    ) -> List[CosmeticCache]:
        """Search cosmetics by type and query."""
        search_query = query.lower()
        cursor = self.db.cosmetic_cache.find({
            "type": cosmetic_type,
            "search_text": {"$regex": search_query, "$options": "i"}
        }).skip(skip).limit(limit)
        cosmetics = await cursor.to_list(length=limit)
        return [CosmeticCache(**c) for c in cosmetics]
    
    async def count_cosmetic_search(self, cosmetic_type: str, query: str) -> int:
        """Count cosmetic search results."""
        search_query = query.lower()
        return await self.db.cosmetic_cache.count_documents({
            "type": cosmetic_type,
            "search_text": {"$regex": search_query, "$options": "i"}
        })
    
    async def get_cosmetic_by_id(self, cosmetic_type: str, cosmetic_id: str) -> Optional[CosmeticCache]:
        """Get cosmetic by ID."""
        data = await self.db.cosmetic_cache.find_one({
            "type": cosmetic_type,
            "cosmetic_id": cosmetic_id
        })
        return CosmeticCache(**data) if data else None
    
    async def get_cosmetic_cache_age(self) -> Optional[datetime]:
        """Get the oldest cache entry date."""
        result = await self.db.cosmetic_cache.find_one(
            sort=[("last_updated", 1)]
        )
        return result["last_updated"] if result else None
    
    # Activity Log Operations
    async def log_activity(
        self,
        discord_id: str,
        action_type: str,
        details: dict,
        session_id: Optional[ObjectId] = None
    ) -> None:
        """Log an activity entry."""
        log_entry = ActivityLog(
            session_id=session_id,
            discord_id=discord_id,
            action_type=action_type,
            details=details
        )
        await self.db.activity_log.insert_one(log_entry.model_dump(by_alias=True, exclude={"id"}))


# Global database instance
db = DatabaseService()
