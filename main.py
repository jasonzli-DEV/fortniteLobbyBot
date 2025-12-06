"""
Fortnite Multi-Bot Management System

Main application entry point. This initializes and runs the Discord bot
along with all supporting services.
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from config import get_settings
from database import db
from bot import bot_manager, cosmetic_search
from services import create_timeout_monitor

# Configure logging
def setup_logging():
    """Configure application logging."""
    settings = get_settings()
    
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Create formatters
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Reduce noise from libraries
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('fortnitepy').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


logger = setup_logging()


class FortniteBot(commands.Bot):
    """Main Discord bot class."""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = False  # We only use slash commands
        
        super().__init__(
            command_prefix="!",  # Not used, but required
            intents=intents,
            help_command=None  # We use our own help command
        )
        
        self.timeout_monitor = None
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        logger.info("Setting up bot...")
        
        # Connect to database
        await db.connect()
        
        # Load cosmetic cache
        await cosmetic_search.refresh_cache()
        
        # Load command cogs
        cog_path = Path(__file__).parent / "discord_bot" / "commands"
        
        cogs = [
            "discord_bot.commands.account_commands",
            "discord_bot.commands.bot_commands",
            "discord_bot.commands.cosmetic_commands",
            "discord_bot.commands.preset_commands",
            "discord_bot.commands.utility_commands",
            "discord_bot.commands.dashboard_commands",
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")
        
        # Sync commands
        if self.settings.discord_guild_id:
            # Sync to specific guild (faster for development)
            guild = discord.Object(id=int(self.settings.discord_guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to guild {self.settings.discord_guild_id}")
        else:
            # Sync globally
            await self.tree.sync()
            logger.info("Synced commands globally")
        
        # Start timeout monitor
        self.timeout_monitor = create_timeout_monitor(self)
        await self.timeout_monitor.start()
        
    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info("Bot setup complete!")
        # Set presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Fortnite lobbies"
            )
        )
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a guild."""
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
    
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot leaves a guild."""
        logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
    
    async def on_command_error(self, ctx, error):
        """Handle command errors."""
        logger.error(f"Command error: {error}")
    
    async def close(self):
        """Clean shutdown."""
        logger.info("Shutting down...")
        
        # Stop timeout monitor
        if self.timeout_monitor:
            await self.timeout_monitor.stop()
        
        # Stop all bots
        stopped = await bot_manager.stop_all_bots("shutdown")
        logger.info(f"Stopped {stopped} bot(s)")
        
        # Disconnect from database
        await db.disconnect()
        
        await super().close()
        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    settings = get_settings()
    
    logger.info("=" * 50)
    logger.info("Fortnite Multi-Bot Management System")
    logger.info("=" * 50)
    logger.info(f"Environment: {settings.environment}")
    
    # Create and run bot
    bot = FortniteBot()
    
    # Handle shutdown signals
    def signal_handler():
        asyncio.create_task(bot.close())
    
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    try:
        await bot.start(settings.discord_bot_token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
