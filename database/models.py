"""Database models using Pydantic for validation."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic models."""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v, handler=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, handler=None):
        return {"type": "string"}


class User(BaseModel):
    """User model tied to Discord identity."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    discord_id: str
    discord_username: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    last_active_channel_id: Optional[str] = None
    total_sessions: int = 0
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class EpicAccount(BaseModel):
    """Epic Games account model."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    discord_id: str
    epic_username: str
    epic_display_name: str
    epic_account_id: str
    encrypted_credentials: str
    status: str = "active"  # 'active', 'error', 'banned'
    added_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    total_sessions: int = 0
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class CurrentCosmetics(BaseModel):
    """Current cosmetics state for a bot."""
    skin: Optional[str] = None
    skin_id: Optional[str] = None
    backbling: Optional[str] = None
    backbling_id: Optional[str] = None
    pickaxe: Optional[str] = None
    pickaxe_id: Optional[str] = None
    level: int = 1
    crown_wins: int = 0


class PartyInfo(BaseModel):
    """Party information for a bot session."""
    in_party: bool = False
    party_size: int = 1
    is_leader: bool = False


class BotSession(BaseModel):
    """Active bot session model."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    account_id: PyObjectId
    discord_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"  # 'active', 'idle_warning', 'stopped'
    timeout_minutes: int = 30
    extensions_used: int = 0
    current_cosmetics: CurrentCosmetics = Field(default_factory=CurrentCosmetics)
    party_info: PartyInfo = Field(default_factory=PartyInfo)
    termination_reason: Optional[str] = None  # 'timeout', 'manual', 'error', 'crash'
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class CosmeticPreset(BaseModel):
    """Saved cosmetic preset model."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    discord_id: str
    name: str
    cosmetics: CurrentCosmetics
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class CosmeticCache(BaseModel):
    """Cached cosmetic item from Fortnite API."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    type: str  # 'skin', 'backbling', 'pickaxe', 'emote'
    cosmetic_id: str
    name: str
    display_name: str
    rarity: str
    description: Optional[str] = None
    search_text: str  # Lowercase for searching
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class ActivityLog(BaseModel):
    """Activity log entry model."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    session_id: Optional[PyObjectId] = None
    discord_id: str
    action_type: str  # 'bot_start', 'cosmetic_change', etc.
    details: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
