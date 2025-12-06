"""Fortnite bot instance manager using fortnitepy."""
import asyncio
import logging
import base64
from datetime import datetime
from typing import Dict, Optional, Callable, Any
from bson import ObjectId

import fortnitepy
from fortnitepy.ext import commands as fn_commands

from config import get_settings
from database import db, CurrentCosmetics
from utils import decrypt_credentials

logger = logging.getLogger(__name__)


def _patch_fortnitepy_for_android():
    """
    Monkey-patch fortnitepy to work with Android client token.
    
    The issue is that fortnitepy's default iOS client is disabled by Epic,
    and the Android client doesn't have permission for the GraphQL endpoint.
    
    This patch makes the GraphQL call return empty data instead of failing.
    """
    import fortnitepy.http as http_module
    
    original_graphql = http_module.HTTPClient.account_graphql_get_clients_external_auths
    
    async def patched_graphql(self, **kwargs):
        """Return empty external auths instead of calling the GraphQL endpoint."""
        try:
            return await original_graphql(self, **kwargs)
        except fortnitepy.errors.HTTPException as e:
            # If we get a 404, return empty data
            if "404" in str(e):
                logger.warning("GraphQL endpoint returned 404, using empty external auths")
                return {'myAccount': {'externalAuths': []}}
            raise
    
    http_module.HTTPClient.account_graphql_get_clients_external_auths = patched_graphql
    logger.info("Patched fortnitepy for Android client compatibility")


# Apply the patch when this module loads
_patch_fortnitepy_for_android()

# fortniteNewSwitchGameClient - supports device_code flow and works for auth
SWITCH_CLIENT_ID = "98f7e42c2e3a4f86a74eb43fbb41ed39"
SWITCH_CLIENT_SECRET = "0a2449a2-001a-451e-afec-3e812901c4d7"
SWITCH_TOKEN = base64.b64encode(f"{SWITCH_CLIENT_ID}:{SWITCH_CLIENT_SECRET}".encode()).decode()

# fortniteAndroidGameClient - used for device auth (has deviceAuths permission)
ANDROID_CLIENT_ID = "3f69e56c7649492c8cc29f1af08a8a12"
ANDROID_CLIENT_SECRET = "b51ee9cb12234f50a69efa67ef53812e"
ANDROID_TOKEN = base64.b64encode(f"{ANDROID_CLIENT_ID}:{ANDROID_CLIENT_SECRET}".encode()).decode()

# fortnitePCGameClient - used for game
PC_CLIENT_ID = "ec684b8c687f479fadea3cb2ad83f5c6"
PC_CLIENT_SECRET = "e1f31c211f28413186262d37a13fc84d"
PC_TOKEN = base64.b64encode(f"{PC_CLIENT_ID}:{PC_CLIENT_SECRET}".encode()).decode()

# launcherAppClient2 - has device_auth grant AND can generate exchange codes
LAUNCHER_CLIENT_ID = "34a02cf8f4414e29b15921876da36f9a"
LAUNCHER_CLIENT_SECRET = "daafbccc737745039dffe53d94fc76cf"
LAUNCHER_TOKEN = base64.b64encode(f"{LAUNCHER_CLIENT_ID}:{LAUNCHER_CLIENT_SECRET}".encode()).decode()

# fortniteiOSGameClient - default fortnitepy client (may be partially disabled but has full permissions)
IOS_CLIENT_ID = "3446cd72694c4a4485d81b77adbb2141"
IOS_CLIENT_SECRET = "9209d4a5e25a457fb9b07489d313b41a"
IOS_TOKEN = base64.b64encode(f"{IOS_CLIENT_ID}:{IOS_CLIENT_SECRET}".encode()).decode()


class FortniteBotInstance:
    """Wrapper for a single fortnitepy client instance."""
    
    def __init__(
        self,
        account_id: ObjectId,
        session_id: ObjectId,
        discord_id: str,
        epic_username: str,
        credentials: dict
    ):
        self.account_id = account_id
        self.session_id = session_id
        self.discord_id = discord_id
        self.epic_username = epic_username
        self.credentials = credentials
        
        self.client: Optional[fortnitepy.Client] = None
        self.session_start: datetime = datetime.utcnow()
        self.last_activity: datetime = datetime.utcnow()
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> bool:
        """Start the Fortnite bot client."""
        try:
            # Epic has disabled the default iOS client.
            # Testing with Android for both tokens - maybe PC token is the issue
            
            logger.info(f"Starting bot {self.epic_username} with Android token for both ios and fortnite")
            
            device_auth = fortnitepy.DeviceAuth(
                device_id=self.credentials["device_id"],
                account_id=self.credentials["account_id"],
                secret=self.credentials["secret"],
                ios_token=ANDROID_TOKEN,     # Android has device_auth grant
                fortnite_token=ANDROID_TOKEN # Try Android for both
            )
            
            self.client = fortnitepy.Client(
                auth=device_auth,
                default_party_member_config=fortnitepy.DefaultPartyMemberConfig(
                    meta=(
                        lambda m: m.set_banner(
                            icon="OtherBanner28",
                            color="DefaultColor18",
                            season_level=100
                        ),
                    )
                )
            )
            
            # Set up event handlers
            self._setup_event_handlers()
            
            # Start client in background task
            self._running = True
            self._task = asyncio.create_task(self._run_client())
            
            # Wait a bit for connection
            await asyncio.sleep(3)
            
            if self.client.is_ready():
                logger.info(f"Bot {self.epic_username} started successfully")
                return True
            else:
                logger.warning(f"Bot {self.epic_username} not ready after start")
                return True  # Still running, might take longer
                
        except Exception as e:
            logger.error(f"Failed to start bot {self.epic_username}: {e}")
            self._running = False
            return False
    
    async def _run_client(self) -> None:
        """Run the client (blocking)."""
        try:
            await self.client.start()
        except asyncio.CancelledError:
            logger.info(f"Bot {self.epic_username} task cancelled")
        except fortnitepy.errors.AuthException as e:
            logger.error(f"Bot {self.epic_username} auth error: {e}")
            if hasattr(e, 'original') and e.original:
                logger.error(f"Original error: {e.original}")
                if hasattr(e.original, 'message_code'):
                    logger.error(f"Message code: {e.original.message_code}")
                if hasattr(e.original, 'raw'):
                    logger.error(f"Raw response: {e.original.raw}")
        except Exception as e:
            logger.error(f"Bot {self.epic_username} error: {e}")
            # Log the full exception chain
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
        finally:
            self._running = False
    
    def _setup_event_handlers(self) -> None:
        """Set up fortnitepy event handlers."""
        
        @self.client.event
        async def event_ready():
            logger.info(f"Bot {self.epic_username} is ready")
            await self.update_activity()
        
        @self.client.event
        async def event_party_invite(invitation: fortnitepy.ReceivedPartyInvitation):
            await invitation.accept()
            await self.update_activity()
            logger.info(f"Bot {self.epic_username} accepted party invite")
        
        @self.client.event
        async def event_friend_request(request: fortnitepy.IncomingPendingFriend):
            await request.accept()
            await self.update_activity()
            logger.info(f"Bot {self.epic_username} accepted friend request from {request.display_name}")
        
        @self.client.event
        async def event_party_member_join(member: fortnitepy.PartyMember):
            await self.update_activity()
        
        @self.client.event
        async def event_party_member_leave(member: fortnitepy.PartyMember):
            await self.update_activity()
    
    async def stop(self, reason: str = "manual") -> None:
        """Stop the Fortnite bot client."""
        self._running = False
        
        try:
            if self.client:
                # Leave party gracefully
                if self.client.party:
                    try:
                        await self.client.party.me.leave()
                    except Exception:
                        pass
                
                # Close client
                await self.client.close()
                
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            
            # Update session in database
            await db.end_session(self.session_id, reason)
            
            logger.info(f"Bot {self.epic_username} stopped: {reason}")
            
        except Exception as e:
            logger.error(f"Error stopping bot {self.epic_username}: {e}")
    
    async def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
        await db.update_session_activity(self.session_id)
    
    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running and self.client is not None
    
    @property
    def is_ready(self) -> bool:
        """Check if bot is ready."""
        return self.is_running and self.client.is_ready()
    
    async def set_skin(self, skin_id: str) -> bool:
        """Set the bot's skin."""
        try:
            if not self.is_ready:
                return False
            
            await self.client.party.me.set_outfit(asset=skin_id)
            await self.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to set skin for {self.epic_username}: {e}")
            return False
    
    async def set_backbling(self, backbling_id: str) -> bool:
        """Set the bot's back bling."""
        try:
            if not self.is_ready:
                return False
            
            await self.client.party.me.set_backpack(asset=backbling_id)
            await self.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to set backbling for {self.epic_username}: {e}")
            return False
    
    async def set_pickaxe(self, pickaxe_id: str) -> bool:
        """Set the bot's pickaxe."""
        try:
            if not self.is_ready:
                return False
            
            await self.client.party.me.set_pickaxe(asset=pickaxe_id)
            await self.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to set pickaxe for {self.epic_username}: {e}")
            return False
    
    async def play_emote(self, emote_id: str) -> bool:
        """Play an emote."""
        try:
            if not self.is_ready:
                return False
            
            await self.client.party.me.set_emote(asset=emote_id)
            await self.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to play emote for {self.epic_username}: {e}")
            return False
    
    async def set_level(self, level: int) -> bool:
        """Set the bot's battle pass level."""
        try:
            if not self.is_ready:
                return False
            
            await self.client.party.me.set_banner(
                season_level=level
            )
            await self.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to set level for {self.epic_username}: {e}")
            return False
    
    async def set_crown_wins(self, count: int) -> bool:
        """Set the bot's crown wins."""
        try:
            if not self.is_ready:
                return False
            
            # Crown wins are set via party member meta
            await self.client.party.me.edit_and_keep(
                partial(
                    self.client.party.me.set_crowned_wins,
                    count
                )
            )
            await self.update_activity()
            return True
        except Exception as e:
            logger.error(f"Failed to set crown wins for {self.epic_username}: {e}")
            return False
    
    async def apply_cosmetics(self, cosmetics: CurrentCosmetics) -> bool:
        """Apply a full set of cosmetics."""
        success = True
        
        if cosmetics.skin_id:
            success = success and await self.set_skin(cosmetics.skin_id)
        
        if cosmetics.backbling_id:
            success = success and await self.set_backbling(cosmetics.backbling_id)
        
        if cosmetics.pickaxe_id:
            success = success and await self.set_pickaxe(cosmetics.pickaxe_id)
        
        if cosmetics.level:
            success = success and await self.set_level(cosmetics.level)
        
        # Update session cosmetics in database
        await db.update_session_cosmetics(self.session_id, cosmetics)
        
        return success


# Required for set_crowned_wins
from functools import partial


class BotInstanceManager:
    """Manager for all active Fortnite bot instances."""
    
    def __init__(self):
        self.active_bots: Dict[str, FortniteBotInstance] = {}  # account_id -> instance
        self._lock = asyncio.Lock()
    
    async def start_bot(
        self,
        account_id: ObjectId,
        discord_id: str,
        epic_username: str,
        encrypted_credentials: str
    ) -> tuple[bool, str]:
        """
        Start a new bot instance.
        
        Returns:
            Tuple of (success, message)
        """
        settings = get_settings()
        account_id_str = str(account_id)
        
        async with self._lock:
            # Check if already running
            if account_id_str in self.active_bots:
                return False, f"Bot `{epic_username}` is already running"
            
            # Check user limit
            user_bots = sum(1 for bot in self.active_bots.values() if bot.discord_id == discord_id)
            if user_bots >= settings.max_concurrent_bots_per_user:
                return False, f"Maximum concurrent bots reached ({user_bots}/{settings.max_concurrent_bots_per_user})"
            
            # Check global limit
            if len(self.active_bots) >= settings.max_concurrent_bots_global:
                return False, "Server is at maximum capacity. Please try again later."
            
            try:
                # Decrypt credentials
                credentials = decrypt_credentials(encrypted_credentials)
                
                # Create session in database
                session = await db.create_bot_session(
                    account_id=account_id,
                    discord_id=discord_id,
                    timeout_minutes=settings.default_session_timeout
                )
                
                # Create bot instance
                bot = FortniteBotInstance(
                    account_id=account_id,
                    session_id=session.id,
                    discord_id=discord_id,
                    epic_username=epic_username,
                    credentials=credentials
                )
                
                # Start the bot
                success = await bot.start()
                
                if success:
                    self.active_bots[account_id_str] = bot
                    await db.update_epic_account_status(credentials["account_id"], "active")
                    return True, f"Bot `{epic_username}` started successfully!"
                else:
                    await db.end_session(session.id, "error")
                    return False, f"Failed to start bot `{epic_username}`. The account may have issues."
                    
            except Exception as e:
                logger.error(f"Error starting bot {epic_username}: {e}")
                return False, f"Failed to start bot: {str(e)}"
    
    async def stop_bot(
        self,
        account_id: ObjectId,
        reason: str = "manual"
    ) -> tuple[bool, str]:
        """
        Stop a running bot instance.
        
        Returns:
            Tuple of (success, message)
        """
        account_id_str = str(account_id)
        
        async with self._lock:
            if account_id_str not in self.active_bots:
                return False, "Bot is not currently running"
            
            bot = self.active_bots[account_id_str]
            epic_username = bot.epic_username
            
            try:
                await bot.stop(reason)
                del self.active_bots[account_id_str]
                return True, f"Bot `{epic_username}` stopped successfully!"
            except Exception as e:
                logger.error(f"Error stopping bot {epic_username}: {e}")
                # Still remove from active bots
                del self.active_bots[account_id_str]
                return True, f"Bot `{epic_username}` stopped (with errors)"
    
    def get_bot(self, account_id: ObjectId) -> Optional[FortniteBotInstance]:
        """Get a bot instance by account ID."""
        return self.active_bots.get(str(account_id))
    
    def get_user_bots(self, discord_id: str) -> list[FortniteBotInstance]:
        """Get all bots for a user."""
        return [bot for bot in self.active_bots.values() if bot.discord_id == discord_id]
    
    async def stop_user_bots(self, discord_id: str, reason: str = "manual") -> int:
        """Stop all bots for a user. Returns count of stopped bots."""
        user_bots = self.get_user_bots(discord_id)
        stopped = 0
        
        for bot in user_bots:
            success, _ = await self.stop_bot(bot.account_id, reason)
            if success:
                stopped += 1
        
        return stopped
    
    async def stop_all_bots(self, reason: str = "shutdown") -> int:
        """Stop all running bots. Returns count of stopped bots."""
        stopped = 0
        account_ids = list(self.active_bots.keys())
        
        for account_id_str in account_ids:
            bot = self.active_bots.get(account_id_str)
            if bot:
                success, _ = await self.stop_bot(bot.account_id, reason)
                if success:
                    stopped += 1
        
        return stopped
    
    def get_bot_status(self, account_id: ObjectId) -> dict:
        """Get status info for a bot."""
        bot = self.get_bot(account_id)
        
        if not bot:
            return {"status": "offline", "running": False}
        
        return {
            "status": "online" if bot.is_ready else "starting",
            "running": bot.is_running,
            "session_start": bot.session_start,
            "last_activity": bot.last_activity,
            "epic_username": bot.epic_username
        }
    
    @property
    def active_count(self) -> int:
        """Get count of active bots."""
        return len(self.active_bots)


# Global bot manager instance
bot_manager = BotInstanceManager()
