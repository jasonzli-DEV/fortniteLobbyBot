"""Bot control Discord commands."""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime

from config import get_settings
from database import db
from bot import bot_manager
from utils import format_uptime, format_time_remaining, get_status_emoji
from discord_bot.views import ConfirmView, BotStatusView

logger = logging.getLogger(__name__)


class BotCommands(commands.Cog):
    """Commands for controlling Fortnite bots."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
    
    @app_commands.command(name="start-bot", description="Start a specific Fortnite bot")
    @app_commands.describe(epic_username="The Epic username of the account to start")
    async def start_bot(self, interaction: discord.Interaction, epic_username: str):
        """Start a specific bot."""
        discord_id = str(interaction.user.id)
        
        # Get account
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            await interaction.response.send_message(
                f"❌ Account `{epic_username}` not found.\n"
                f"Use `/list-accounts` to see your connected accounts.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Update user's last active channel
        await db.update_user_channel(discord_id, str(interaction.channel_id))
        
        # Start the bot
        success, message = await bot_manager.start_bot(
            account_id=account.id,
            discord_id=discord_id,
            epic_username=account.epic_username,
            encrypted_credentials=account.encrypted_credentials
        )
        
        if success:
            embed = discord.Embed(
                title="🚀 Bot Started!",
                description=message,
                color=discord.Color.green()
            )
            embed.add_field(
                name="Timeout",
                value=f"{self.settings.default_session_timeout} minutes",
                inline=True
            )
            embed.add_field(
                name="Next Steps",
                value="• Use `/bot-status` to check status\n• Use `/set-skin` to change appearance",
                inline=False
            )
            
            # Log activity
            await db.log_activity(discord_id, "bot_start", {"epic_username": account.epic_username})
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
    
    @app_commands.command(name="stop-bot", description="Stop a specific Fortnite bot")
    @app_commands.describe(epic_username="The Epic username of the bot to stop")
    async def stop_bot(self, interaction: discord.Interaction, epic_username: str):
        """Stop a specific bot."""
        discord_id = str(interaction.user.id)
        
        # Get account
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            await interaction.response.send_message(
                f"❌ Account `{epic_username}` not found.",
                ephemeral=True
            )
            return
        
        # Check if running
        bot_instance = bot_manager.get_bot(account.id)
        if not bot_instance:
            await interaction.response.send_message(
                f"⚠️ Bot `{epic_username}` is not currently running.\n"
                f"Use `/start-bot {epic_username}` to start it.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Stop the bot
        success, message = await bot_manager.stop_bot(account.id, "manual")
        
        if success:
            await db.log_activity(discord_id, "bot_stop", {"epic_username": account.epic_username, "reason": "manual"})
            await interaction.followup.send(f"✅ {message}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
    
    @app_commands.command(name="start-all", description="Start all your Fortnite bots")
    async def start_all(self, interaction: discord.Interaction):
        """Start all bots for the user."""
        discord_id = str(interaction.user.id)
        
        accounts = await db.get_epic_accounts(discord_id)
        if not accounts:
            await interaction.response.send_message(
                "📭 You don't have any accounts to start.\n"
                "Use `/add-account` to add an Epic Games account.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        await db.update_user_channel(discord_id, str(interaction.channel_id))
        
        started = []
        failed = []
        
        for account in accounts:
            # Skip if already running
            if bot_manager.get_bot(account.id):
                continue
            
            # Check limits
            user_bots = len(bot_manager.get_user_bots(discord_id))
            if user_bots >= self.settings.max_concurrent_bots_per_user:
                failed.append(f"{account.epic_username} (limit reached)")
                continue
            
            success, message = await bot_manager.start_bot(
                account_id=account.id,
                discord_id=discord_id,
                epic_username=account.epic_username,
                encrypted_credentials=account.encrypted_credentials
            )
            
            if success:
                started.append(account.epic_username)
            else:
                failed.append(account.epic_username)
        
        embed = discord.Embed(
            title="🚀 Start All Bots",
            color=discord.Color.green() if started else discord.Color.orange()
        )
        
        if started:
            embed.add_field(
                name="✅ Started",
                value="\n".join(f"• {name}" for name in started),
                inline=False
            )
        
        if failed:
            embed.add_field(
                name="❌ Failed",
                value="\n".join(f"• {name}" for name in failed),
                inline=False
            )
        
        if not started and not failed:
            embed.description = "All bots are already running!"
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="stop-all", description="Stop all your running Fortnite bots")
    async def stop_all(self, interaction: discord.Interaction):
        """Stop all bots for the user."""
        discord_id = str(interaction.user.id)
        
        user_bots = bot_manager.get_user_bots(discord_id)
        if not user_bots:
            await interaction.response.send_message(
                "⚫ You don't have any running bots.",
                ephemeral=True
            )
            return
        
        # Confirm
        embed = discord.Embed(
            title="⚠️ Stop All Bots?",
            description=f"This will stop {len(user_bots)} running bot(s):\n" +
                        "\n".join(f"• {bot.epic_username}" for bot in user_bots),
            color=discord.Color.orange()
        )
        
        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if view.value:
            stopped = await bot_manager.stop_user_bots(discord_id, "manual")
            await interaction.edit_original_response(
                content=f"✅ Stopped {stopped} bot(s).",
                embed=None,
                view=None
            )
        else:
            await interaction.edit_original_response(
                content="❌ Cancelled.",
                embed=None,
                view=None
            )
    
    @app_commands.command(name="bot-status", description="Show status of your bots")
    @app_commands.describe(epic_username="Specific bot to check (optional)")
    async def show_bot_status(self, interaction: discord.Interaction, epic_username: str = None):
        """Show bot status."""
        discord_id = str(interaction.user.id)
        
        await db.update_user_channel(discord_id, str(interaction.channel_id))
        
        if epic_username:
            # Specific bot status
            account = await db.get_epic_account_by_username(discord_id, epic_username)
            if not account:
                await interaction.response.send_message(
                    f"❌ Account `{epic_username}` not found.",
                    ephemeral=True
                )
                return
            
            await self._send_single_bot_status(interaction, account)
        else:
            # All bots status
            await self._send_all_bots_status(interaction, discord_id)
    
    async def _send_single_bot_status(self, interaction: discord.Interaction, account):
        """Send status for a single bot."""
        bot_instance = bot_manager.get_bot(account.id)
        session = await db.get_active_session(account.id)
        
        embed = discord.Embed(
            title=f"🤖 Bot Status: {account.epic_username}",
            color=discord.Color.green() if bot_instance else discord.Color.dark_gray()
        )
        
        if bot_instance and session:
            embed.add_field(
                name="Status",
                value="🟢 **ONLINE**",
                inline=True
            )
            embed.add_field(
                name="Uptime",
                value=format_uptime(bot_instance.session_start),
                inline=True
            )
            embed.add_field(
                name="Timeout",
                value=f"{format_time_remaining(session.last_activity, session.timeout_minutes)} remaining",
                inline=True
            )
            
            # Cosmetics info
            cosmetics = session.current_cosmetics
            if cosmetics.skin:
                embed.add_field(name="Skin", value=cosmetics.skin, inline=True)
            if cosmetics.level:
                embed.add_field(name="Level", value=str(cosmetics.level), inline=True)
            if cosmetics.crown_wins:
                embed.add_field(name="Crowns", value=str(cosmetics.crown_wins), inline=True)
        else:
            embed.add_field(
                name="Status",
                value="⚫ **OFFLINE**",
                inline=True
            )
            if account.last_used:
                embed.add_field(
                    name="Last Used",
                    value=account.last_used.strftime("%Y-%m-%d %H:%M"),
                    inline=True
                )
        
        # Create view with action buttons
        async def on_start(inter, acc_id):
            await inter.response.defer(ephemeral=True)
            success, message = await bot_manager.start_bot(
                account_id=account.id,
                discord_id=str(inter.user.id),
                epic_username=account.epic_username,
                encrypted_credentials=account.encrypted_credentials
            )
            await inter.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
        
        async def on_stop(inter, acc_id):
            await inter.response.defer(ephemeral=True)
            success, message = await bot_manager.stop_bot(account.id, "manual")
            await inter.followup.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)
        
        async def on_extend(inter, acc_id):
            await self._extend_bot(inter, account)
        
        async def on_refresh(inter, acc_id):
            await inter.response.defer(ephemeral=True)
            await self._send_single_bot_status(inter, account)
        
        view = BotStatusView(
            str(account.id),
            bot_instance is not None,
            on_start, on_stop, on_extend, on_refresh
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _send_all_bots_status(self, interaction: discord.Interaction, discord_id: str):
        """Send status for all user's bots."""
        accounts = await db.get_epic_accounts(discord_id)
        
        if not accounts:
            await interaction.response.send_message(
                "📭 You don't have any accounts.\n"
                "Use `/add-account` to add an Epic Games account.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🤖 Your Fortnite Bots",
            color=discord.Color.blue()
        )
        
        for account in accounts:
            bot_instance = bot_manager.get_bot(account.id)
            session = await db.get_active_session(account.id)
            
            if bot_instance and session:
                status = "🟢 ONLINE"
                details = (
                    f"Uptime: {format_uptime(bot_instance.session_start)}\n"
                    f"Timeout: {format_time_remaining(session.last_activity, session.timeout_minutes)}"
                )
            else:
                status = "⚫ OFFLINE"
                last_used = account.last_used.strftime("%Y-%m-%d %H:%M") if account.last_used else "Never"
                details = f"Last used: {last_used}"
            
            embed.add_field(
                name=f"{account.epic_username} ({status})",
                value=details,
                inline=False
            )
        
        # Summary footer
        running = len(bot_manager.get_user_bots(discord_id))
        embed.set_footer(text=f"Running: {running}/{len(accounts)} | Limit: {self.settings.max_concurrent_bots_per_user}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="extend", description="Extend bot session timeout")
    @app_commands.describe(epic_username="The Epic username of the bot to extend")
    async def extend(self, interaction: discord.Interaction, epic_username: str):
        """Extend a bot's session timeout."""
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            await interaction.response.send_message(
                f"❌ Account `{epic_username}` not found.",
                ephemeral=True
            )
            return
        
        await self._extend_bot(interaction, account)
    
    async def _extend_bot(self, interaction: discord.Interaction, account):
        """Internal method to extend a bot's session."""
        bot_instance = bot_manager.get_bot(account.id)
        if not bot_instance:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"⚠️ Bot `{account.epic_username}` is not currently running.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"⚠️ Bot `{account.epic_username}` is not currently running.",
                    ephemeral=True
                )
            return
        
        session = await db.get_active_session(account.id)
        if not session:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Session not found.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Session not found.", ephemeral=True)
            return
        
        # Check extension limit
        if session.extensions_used >= self.settings.max_extensions_per_session:
            msg = (
                f"🚫 Maximum extensions reached ({session.extensions_used}/{self.settings.max_extensions_per_session})\n"
                f"The bot will stop when the timeout is reached."
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return
        
        # Extend session
        new_count = await db.extend_session(session.id, self.settings.session_extension_duration)
        
        # Update bot activity
        await bot_instance.update_activity()
        
        msg = (
            f"✅ Session extended for `{account.epic_username}`!\n"
            f"Added {self.settings.session_extension_duration} minutes.\n"
            f"Extensions used: {new_count}/{self.settings.max_extensions_per_session}"
        )
        
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    """Set up the bot commands cog."""
    await bot.add_cog(BotCommands(bot))
