"""Timeout monitor background task."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import discord

from config import get_settings
from database import db
from bot import bot_manager
from utils import calculate_remaining_seconds, format_time_remaining

logger = logging.getLogger(__name__)


class TimeoutMonitor:
    """Background task that monitors bot sessions for timeouts."""
    
    def __init__(self, discord_bot: discord.Client):
        self.discord_bot = discord_bot
        self.settings = get_settings()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the timeout monitor."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Timeout monitor started")
    
    async def stop(self) -> None:
        """Stop the timeout monitor."""
        self._running = False
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Timeout monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_sessions()
            except Exception as e:
                logger.error(f"Error in timeout monitor: {e}")
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute
    
    async def _check_sessions(self) -> None:
        """Check all active sessions for timeouts."""
        active_sessions = await db.get_all_active_sessions()
        warning_threshold = self.settings.timeout_warning_threshold * 60  # Convert to seconds
        
        for session in active_sessions:
            try:
                remaining = calculate_remaining_seconds(
                    session.last_activity,
                    session.timeout_minutes
                )
                
                if remaining <= 0:
                    # Session has timed out
                    await self._handle_timeout(session)
                    
                elif remaining <= warning_threshold and session.status != "idle_warning":
                    # Send warning
                    await self._send_warning(session, remaining)
                    
            except Exception as e:
                logger.error(f"Error checking session {session.id}: {e}")
    
    async def _handle_timeout(self, session) -> None:
        """Handle a timed out session."""
        logger.info(f"Session {session.id} timed out")
        
        # Get account info for logging
        account = await db.get_epic_account_by_id(session.account_id)
        epic_username = account.epic_username if account else "Unknown"
        
        # Stop the bot
        bot_instance = bot_manager.get_bot(session.account_id)
        if bot_instance:
            await bot_manager.stop_bot(session.account_id, "timeout")
        else:
            # Just update session in database
            await db.end_session(session.id, "timeout")
        
        # Try to send notification
        await self._send_timeout_notification(session, epic_username)
        
        # Log activity
        await db.log_activity(
            session.discord_id,
            "timeout",
            {"epic_username": epic_username, "session_id": str(session.id)}
        )
    
    async def _send_warning(self, session, remaining_seconds: int) -> None:
        """Send a timeout warning to the user."""
        # Update session status
        await db.update_session_status(session.id, "idle_warning")
        
        # Get user's last active channel
        user = await db.get_user(session.discord_id)
        if not user or not user.last_active_channel_id:
            return
        
        # Get account info
        account = await db.get_epic_account_by_id(session.account_id)
        epic_username = account.epic_username if account else "Unknown"
        
        # Try to send warning
        try:
            channel = self.discord_bot.get_channel(int(user.last_active_channel_id))
            if not channel:
                channel = await self.discord_bot.fetch_channel(int(user.last_active_channel_id))
            
            if channel and isinstance(channel, discord.TextChannel):
                # We can't send ephemeral messages proactively, so we mention the user
                minutes_remaining = remaining_seconds // 60
                
                # Try to find the user
                try:
                    discord_user = await self.discord_bot.fetch_user(int(session.discord_id))
                    
                    # Send a message that will auto-delete
                    msg = await channel.send(
                        f"⏰ {discord_user.mention} Your bot `{epic_username}` will stop in "
                        f"**{minutes_remaining} minutes**. Use `/extend {epic_username}` to continue.",
                        delete_after=300  # Delete after 5 minutes
                    )
                    
                    logger.info(f"Sent timeout warning for {epic_username} to {session.discord_id}")
                    
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass
                    
        except Exception as e:
            logger.debug(f"Could not send warning: {e}")
    
    async def _send_timeout_notification(self, session, epic_username: str) -> None:
        """Send notification that bot has timed out."""
        user = await db.get_user(session.discord_id)
        if not user or not user.last_active_channel_id:
            return
        
        try:
            channel = self.discord_bot.get_channel(int(user.last_active_channel_id))
            if not channel:
                channel = await self.discord_bot.fetch_channel(int(user.last_active_channel_id))
            
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    discord_user = await self.discord_bot.fetch_user(int(session.discord_id))
                    
                    await channel.send(
                        f"⚫ {discord_user.mention} Your bot `{epic_username}` has stopped due to inactivity. "
                        f"Use `/startbot {epic_username}` to restart.",
                        delete_after=600  # Delete after 10 minutes
                    )
                    
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass
                    
        except Exception as e:
            logger.debug(f"Could not send timeout notification: {e}")


# Global timeout monitor instance (initialized in main)
timeout_monitor: Optional[TimeoutMonitor] = None


def create_timeout_monitor(discord_bot: discord.Client) -> TimeoutMonitor:
    """Create and return a timeout monitor instance."""
    global timeout_monitor
    timeout_monitor = TimeoutMonitor(discord_bot)
    return timeout_monitor
