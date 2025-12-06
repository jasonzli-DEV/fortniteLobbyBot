"""Preset Discord commands."""
import discord
from discord import app_commands
from discord.ext import commands
import logging

from config import get_settings
from database import db, CurrentCosmetics
from bot import bot_manager
from utils import get_rarity_emoji
from discord_bot.views import ConfirmView, PresetListView

logger = logging.getLogger(__name__)


class PresetCommands(commands.Cog):
    """Commands for managing cosmetic presets."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
    
    @app_commands.command(name="save-preset", description="Save current bot cosmetics as a preset")
    @app_commands.describe(
        name="Name for the preset",
        epic_username="The Epic username of the bot to save from"
    )
    async def save_preset(
        self,
        interaction: discord.Interaction,
        name: str,
        epic_username: str
    ):
        """Save current cosmetics as a preset."""
        discord_id = str(interaction.user.id)
        
        # Validate preset name
        if len(name) > 32:
            await interaction.response.send_message(
                "❌ Preset name must be 32 characters or less.",
                ephemeral=True
            )
            return
        
        # Get account and session
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            await interaction.response.send_message(
                f"❌ Account `{epic_username}` not found.",
                ephemeral=True
            )
            return
        
        session = await db.get_active_session(account.id)
        if not session:
            await interaction.response.send_message(
                f"❌ No active session for `{epic_username}`.\n"
                f"Start the bot first with `/start-bot {epic_username}`",
                ephemeral=True
            )
            return
        
        cosmetics = session.current_cosmetics
        
        # Show confirmation with preview
        embed = discord.Embed(
            title=f"💾 Save Preset: {name}",
            description="Save these cosmetics?",
            color=discord.Color.blue()
        )
        
        if cosmetics.skin:
            embed.add_field(name="Skin", value=cosmetics.skin, inline=True)
        if cosmetics.backbling:
            embed.add_field(name="Back Bling", value=cosmetics.backbling, inline=True)
        if cosmetics.pickaxe:
            embed.add_field(name="Pickaxe", value=cosmetics.pickaxe, inline=True)
        embed.add_field(name="Level", value=str(cosmetics.level), inline=True)
        embed.add_field(name="Crowns", value=str(cosmetics.crown_wins), inline=True)
        
        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if view.value:
            await db.save_preset(discord_id, name, cosmetics)
            await interaction.edit_original_response(
                content=f"✅ Preset `{name}` saved successfully!",
                embed=None,
                view=None
            )
            logger.info(f"User {discord_id} saved preset '{name}'")
        else:
            await interaction.edit_original_response(
                content="❌ Preset save cancelled.",
                embed=None,
                view=None
            )
    
    @app_commands.command(name="load-preset", description="Apply a saved preset to a bot")
    @app_commands.describe(
        name="Name of the preset",
        epic_username="Target bot (or 'all' for all running bots)"
    )
    async def load_preset(
        self,
        interaction: discord.Interaction,
        name: str,
        epic_username: str
    ):
        """Load and apply a preset."""
        discord_id = str(interaction.user.id)
        
        # Get preset
        preset = await db.get_preset_by_name(discord_id, name)
        if not preset:
            await interaction.response.send_message(
                f"❌ Preset `{name}` not found.\n"
                f"Use `/list-presets` to see your saved presets.",
                ephemeral=True
            )
            return
        
        cosmetics = preset.cosmetics
        
        # Show confirmation
        embed = discord.Embed(
            title=f"📥 Load Preset: {preset.name}",
            color=discord.Color.blue()
        )
        
        if cosmetics.skin:
            embed.add_field(name="Skin", value=cosmetics.skin, inline=True)
        if cosmetics.backbling:
            embed.add_field(name="Back Bling", value=cosmetics.backbling, inline=True)
        if cosmetics.pickaxe:
            embed.add_field(name="Pickaxe", value=cosmetics.pickaxe, inline=True)
        embed.add_field(name="Level", value=str(cosmetics.level), inline=True)
        embed.add_field(name="Crowns", value=str(cosmetics.crown_wins), inline=True)
        
        target_desc = "all running bots" if epic_username.lower() == "all" else f"`{epic_username}`"
        embed.description = f"Apply to {target_desc}?"
        
        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if not view.value:
            await interaction.edit_original_response(
                content="❌ Preset load cancelled.",
                embed=None,
                view=None
            )
            return
        
        # Apply preset
        if epic_username.lower() == "all":
            user_bots = bot_manager.get_user_bots(discord_id)
            applied = 0
            
            for bot_instance in user_bots:
                success = await bot_instance.apply_cosmetics(cosmetics)
                if success:
                    applied += 1
            
            await interaction.edit_original_response(
                content=f"✅ Applied preset `{name}` to {applied} bot(s)!",
                embed=None,
                view=None
            )
        else:
            account = await db.get_epic_account_by_username(discord_id, epic_username)
            if not account:
                await interaction.edit_original_response(
                    content=f"❌ Account `{epic_username}` not found.",
                    embed=None,
                    view=None
                )
                return
            
            bot_instance = bot_manager.get_bot(account.id)
            if not bot_instance:
                await interaction.edit_original_response(
                    content=f"❌ Bot `{epic_username}` is not running.",
                    embed=None,
                    view=None
                )
                return
            
            success = await bot_instance.apply_cosmetics(cosmetics)
            
            if success:
                await interaction.edit_original_response(
                    content=f"✅ Applied preset `{name}` to `{epic_username}`!",
                    embed=None,
                    view=None
                )
            else:
                await interaction.edit_original_response(
                    content="❌ Failed to apply preset.",
                    embed=None,
                    view=None
                )
    
    @app_commands.command(name="list-presets", description="Show all your saved presets")
    async def list_presets(self, interaction: discord.Interaction):
        """List all saved presets."""
        discord_id = str(interaction.user.id)
        
        presets = await db.get_presets(discord_id)
        
        if not presets:
            await interaction.response.send_message(
                "📭 You don't have any saved presets.\n"
                "Use `/save-preset <name> <epic_username>` to save one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="📋 Your Presets",
            color=discord.Color.blue()
        )
        
        for preset in presets:
            cosmetics = preset.cosmetics
            details = []
            
            if cosmetics.skin:
                details.append(f"Skin: {cosmetics.skin}")
            if cosmetics.level:
                details.append(f"Level: {cosmetics.level}")
            if cosmetics.crown_wins:
                details.append(f"Crowns: {cosmetics.crown_wins}")
            
            embed.add_field(
                name=f"📦 {preset.name}",
                value="\n".join(details) if details else "Empty preset",
                inline=False
            )
        
        async def on_load(inter: discord.Interaction, preset_name: str):
            await inter.response.send_message(
                f"Use `/load-preset {preset_name} <epic_username>` to apply this preset.",
                ephemeral=True
            )
        
        async def on_delete(inter: discord.Interaction, preset_name: str):
            pass
        
        view = PresetListView(presets, on_load, on_delete)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="delete-preset", description="Delete a saved preset")
    @app_commands.describe(name="Name of the preset to delete")
    async def delete_preset(self, interaction: discord.Interaction, name: str):
        """Delete a preset."""
        discord_id = str(interaction.user.id)
        
        preset = await db.get_preset_by_name(discord_id, name)
        if not preset:
            await interaction.response.send_message(
                f"❌ Preset `{name}` not found.",
                ephemeral=True
            )
            return
        
        # Confirm deletion
        embed = discord.Embed(
            title="⚠️ Delete Preset?",
            description=f"Are you sure you want to delete `{preset.name}`?\n\nThis cannot be undone.",
            color=discord.Color.orange()
        )
        
        view = ConfirmView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        
        if view.value:
            await db.delete_preset(discord_id, name)
            await interaction.edit_original_response(
                content=f"✅ Preset `{name}` deleted.",
                embed=None,
                view=None
            )
            logger.info(f"User {discord_id} deleted preset '{name}'")
        else:
            await interaction.edit_original_response(
                content="❌ Deletion cancelled.",
                embed=None,
                view=None
            )


async def setup(bot: commands.Bot):
    """Set up the preset commands cog."""
    await bot.add_cog(PresetCommands(bot))
