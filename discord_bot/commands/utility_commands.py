"""Utility Discord commands (help, stats, ping)."""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime

from config import get_settings
from database import db
from bot import bot_manager

logger = logging.getLogger(__name__)


class UtilityCommands(commands.Cog):
    """Utility commands for help, stats, and diagnostics."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
        self.start_time = datetime.utcnow()
    
    @app_commands.command(name="help", description="Show help information")
    @app_commands.describe(command="Specific command to get help for (optional)")
    async def help_command(self, interaction: discord.Interaction, command: str = None):
        """Show help information."""
        if command:
            await self._show_command_help(interaction, command)
        else:
            await self._show_all_help(interaction)
    
    async def _show_all_help(self, interaction: discord.Interaction):
        """Show help for all commands."""
        embed = discord.Embed(
            title="🤖 Fortnite Lobby Bot - Help",
            description="Control Fortnite bots via Discord commands. All responses are private (ephemeral).",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Account Management",
            value=(
                "`/addaccount` - Add Epic Games account\n"
                "`/confirmauth <code>` - Complete account setup\n"
                "`/listaccounts` - Show your accounts\n"
                "`/removeaccount <username>` - Remove an account\n"
                "`/testaccount <username>` - Test connection"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎮 Bot Control",
            value=(
                "`/startbot <username>` - Start a bot\n"
                "`/stopbot <username>` - Stop a bot\n"
                "`/startall` - Start all bots\n"
                "`/stopall` - Stop all bots\n"
                "`/botstatus [username]` - Check status\n"
                "`/extend <username>` - Extend timeout"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎨 Cosmetics",
            value=(
                "`/setskin <username>` - Change outfit\n"
                "`/setbackbling <username>` - Change back bling\n"
                "`/setpickaxe <username>` - Change pickaxe\n"
                "`/emote <username>` - Perform emote\n"
                "`/setlevel <username> <level>` - Set level (1-200)\n"
                "`/setcrowns <username> <count>` - Set crown wins\n"
                "`/synccosmetics <from> <to|all>` - Copy cosmetics"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📦 Presets",
            value=(
                "`/savepreset <name> <username>` - Save preset\n"
                "`/loadpreset <name> <username|all>` - Load preset\n"
                "`/listpresets` - Show presets\n"
                "`/deletepreset <name>` - Delete preset"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔧 Utility",
            value=(
                "`/help [command]` - Show help\n"
                "`/stats` - Show your statistics\n"
                "`/ping` - Check bot latency"
            ),
            inline=False
        )
        
        embed.set_footer(text="This is a free service! Use /help <command> for detailed info.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _show_command_help(self, interaction: discord.Interaction, command: str):
        """Show detailed help for a specific command."""
        command_info = {
            "addaccount": {
                "title": "/addaccount",
                "description": "Add a new Epic Games account using device authentication.",
                "usage": "/addaccount",
                "steps": "1. Run the command\n2. Click the authorization link\n3. Log in to Epic Games\n4. Copy the code and use `/confirmauth <code>`"
            },
            "startbot": {
                "title": "/startbot",
                "description": "Start a Fortnite lobby bot for a specific account.",
                "usage": "/startbot <epic_username>",
                "notes": "The bot will automatically accept party invites and friend requests."
            },
            "setskin": {
                "title": "/setskin",
                "description": "Change the bot's skin using interactive search.",
                "usage": "/setskin <epic_username>",
                "notes": "A search modal will appear. Type part of the skin name to find it."
            },
            "extend": {
                "title": "/extend",
                "description": "Extend a bot's session timeout.",
                "usage": "/extend <epic_username>",
                "notes": f"Adds {self.settings.session_extension_duration} minutes. Max {self.settings.max_extensions_per_session} extensions per session."
            }
        }
        
        info = command_info.get(command.lower().replace("/", ""))
        
        if not info:
            await interaction.response.send_message(
                f"❌ Command `{command}` not found. Use `/help` to see all commands.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=info["title"],
            description=info["description"],
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Usage", value=f"`{info['usage']}`", inline=False)
        
        if "steps" in info:
            embed.add_field(name="Steps", value=info["steps"], inline=False)
        
        if "notes" in info:
            embed.add_field(name="Notes", value=info["notes"], inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="stats", description="Show your usage statistics")
    async def stats(self, interaction: discord.Interaction):
        """Show user statistics."""
        discord_id = str(interaction.user.id)
        
        user = await db.get_user(discord_id)
        accounts = await db.get_epic_accounts(discord_id)
        presets = await db.get_presets(discord_id)
        running_bots = bot_manager.get_user_bots(discord_id)
        
        embed = discord.Embed(
            title="📊 Your Statistics",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Accounts",
            value=f"{len(accounts)}/{self.settings.max_accounts_per_user}",
            inline=True
        )
        
        embed.add_field(
            name="Running Bots",
            value=f"{len(running_bots)}/{self.settings.max_concurrent_bots_per_user}",
            inline=True
        )
        
        embed.add_field(
            name="Presets",
            value=str(len(presets)),
            inline=True
        )
        
        if user:
            embed.add_field(
                name="Total Sessions",
                value=str(user.total_sessions),
                inline=True
            )
            
            embed.add_field(
                name="Member Since",
                value=user.created_at.strftime("%Y-%m-%d"),
                inline=True
            )
        
        # Global stats
        global_bots = bot_manager.active_count
        embed.add_field(
            name="Global Active Bots",
            value=f"{global_bots}/{self.settings.max_concurrent_bots_global}",
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot latency."""
        latency = round(self.bot.latency * 1000)
        
        # Calculate uptime
        uptime = datetime.utcnow() - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
        
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green() if latency < 200 else discord.Color.orange()
        )
        
        embed.add_field(name="Latency", value=f"{latency}ms", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Active Bots", value=str(bot_manager.active_count), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Set up the utility commands cog."""
    await bot.add_cog(UtilityCommands(bot))
