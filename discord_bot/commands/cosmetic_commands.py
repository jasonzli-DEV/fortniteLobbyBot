"""Cosmetic Discord commands."""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from config import get_settings
from database import db, CurrentCosmetics
from bot import bot_manager, cosmetic_search
from utils import get_rarity_emoji
from discord_bot.views import CosmeticSearchModal, CosmeticSearchView

logger = logging.getLogger(__name__)


class CosmeticCommands(commands.Cog):
    """Commands for customizing bot cosmetics."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
    
    async def _get_running_bot(self, interaction: discord.Interaction, epic_username: str):
        """Helper to get a running bot instance."""
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            await interaction.response.send_message(
                f"❌ Account `{epic_username}` not found.",
                ephemeral=True
            )
            return None, None
        
        bot_instance = bot_manager.get_bot(account.id)
        if not bot_instance:
            await interaction.response.send_message(
                f"⚠️ Bot `{epic_username}` is not currently online.\n"
                f"Use `/startbot {epic_username}` to start it first.",
                ephemeral=True
            )
            return None, None
        
        return account, bot_instance
    
    async def _cosmetic_search_flow(
        self,
        interaction: discord.Interaction,
        epic_username: str,
        cosmetic_type: str,
        apply_callback
    ):
        """Handle the cosmetic search and selection flow."""
        account, bot_instance = await self._get_running_bot(interaction, epic_username)
        if not account:
            return
        
        # Show search modal
        modal = CosmeticSearchModal(cosmetic_type)
        await interaction.response.send_modal(modal)
        
        # Wait for modal submission
        try:
            await modal.wait()
        except Exception:
            return
        
        if not modal.search_query:
            return
        
        # Perform search and show results
        await self._show_search_results(
            interaction,
            account,
            bot_instance,
            cosmetic_type,
            modal.search_query,
            page=1,
            apply_callback=apply_callback
        )
    
    async def _show_search_results(
        self,
        interaction: discord.Interaction,
        account,
        bot_instance,
        cosmetic_type: str,
        query: str,
        page: int,
        apply_callback
    ):
        """Show cosmetic search results with pagination."""
        results, total_count, total_pages = await cosmetic_search.search(
            cosmetic_type=cosmetic_type,
            query=query,
            page=page
        )
        
        if not results:
            await interaction.followup.send(
                f"❌ No {cosmetic_type}s found matching `{query}`.\n"
                f"Try a different search term.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"🔍 Search results for \"{query}\"",
            description=f"Found {total_count} {cosmetic_type}(s). Select one below:",
            color=discord.Color.blue()
        )
        
        async def on_select(inter: discord.Interaction, cosmetic):
            await inter.response.defer(ephemeral=True)
            success = await apply_callback(bot_instance, cosmetic)
            
            if success:
                # Update session cosmetics
                session = await db.get_active_session(account.id)
                if session:
                    cosmetics = session.current_cosmetics
                    if cosmetic_type == "skin":
                        cosmetics.skin = cosmetic.display_name
                        cosmetics.skin_id = cosmetic.cosmetic_id
                    elif cosmetic_type == "backbling":
                        cosmetics.backbling = cosmetic.display_name
                        cosmetics.backbling_id = cosmetic.cosmetic_id
                    elif cosmetic_type == "pickaxe":
                        cosmetics.pickaxe = cosmetic.display_name
                        cosmetics.pickaxe_id = cosmetic.cosmetic_id
                    
                    await db.update_session_cosmetics(session.id, cosmetics)
                
                result_embed = discord.Embed(
                    title=f"✅ {cosmetic_type.title()} Changed!",
                    description=f"**{cosmetic.display_name}**",
                    color=discord.Color.green()
                )
                result_embed.add_field(name="Rarity", value=f"{get_rarity_emoji(cosmetic.rarity)} {cosmetic.rarity.title()}", inline=True)
                result_embed.add_field(name="Bot", value=account.epic_username, inline=True)
                
                await inter.edit_original_response(embed=result_embed, view=None)
            else:
                await inter.edit_original_response(
                    content=f"❌ Failed to apply {cosmetic_type}. Please try again.",
                    embed=None,
                    view=None
                )
        
        async def on_page_change(inter: discord.Interaction, new_page: int):
            await inter.response.defer(ephemeral=True)
            await self._show_search_results(
                inter, account, bot_instance, cosmetic_type,
                query, new_page, apply_callback
            )
        
        view = CosmeticSearchView(
            cosmetics=results,
            page=page,
            total_pages=total_pages,
            cosmetic_type=cosmetic_type,
            query=query,
            on_select=on_select,
            on_page_change=on_page_change
        )
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="setskin", description="Change bot outfit")
    @app_commands.describe(epic_username="The Epic username of the bot")
    async def set_skin(self, interaction: discord.Interaction, epic_username: str):
        """Change bot skin with interactive search."""
        async def apply_skin(bot_instance, cosmetic):
            return await bot_instance.set_skin(cosmetic.cosmetic_id)
        
        await self._cosmetic_search_flow(interaction, epic_username, "skin", apply_skin)
    
    @app_commands.command(name="setbackbling", description="Change bot back bling")
    @app_commands.describe(epic_username="The Epic username of the bot")
    async def set_backbling(self, interaction: discord.Interaction, epic_username: str):
        """Change bot back bling with interactive search."""
        async def apply_backbling(bot_instance, cosmetic):
            return await bot_instance.set_backbling(cosmetic.cosmetic_id)
        
        await self._cosmetic_search_flow(interaction, epic_username, "backbling", apply_backbling)
    
    @app_commands.command(name="setpickaxe", description="Change bot pickaxe")
    @app_commands.describe(epic_username="The Epic username of the bot")
    async def set_pickaxe(self, interaction: discord.Interaction, epic_username: str):
        """Change bot pickaxe with interactive search."""
        async def apply_pickaxe(bot_instance, cosmetic):
            return await bot_instance.set_pickaxe(cosmetic.cosmetic_id)
        
        await self._cosmetic_search_flow(interaction, epic_username, "pickaxe", apply_pickaxe)
    
    @app_commands.command(name="emote", description="Make the bot perform an emote")
    @app_commands.describe(epic_username="The Epic username of the bot")
    async def emote(self, interaction: discord.Interaction, epic_username: str):
        """Make bot perform an emote with interactive search."""
        async def apply_emote(bot_instance, cosmetic):
            return await bot_instance.play_emote(cosmetic.cosmetic_id)
        
        await self._cosmetic_search_flow(interaction, epic_username, "emote", apply_emote)
    
    @app_commands.command(name="setlevel", description="Set bot battle pass level")
    @app_commands.describe(
        epic_username="The Epic username of the bot",
        level="Battle pass level (1-200)"
    )
    async def set_level(self, interaction: discord.Interaction, epic_username: str, level: int):
        """Set bot's battle pass level."""
        # Validate level
        if level < 1 or level > 200:
            await interaction.response.send_message(
                "❌ Level must be between 1 and 200.",
                ephemeral=True
            )
            return
        
        account, bot_instance = await self._get_running_bot(interaction, epic_username)
        if not account:
            return
        
        await interaction.response.defer(ephemeral=True)
        
        success = await bot_instance.set_level(level)
        
        if success:
            # Update session
            session = await db.get_active_session(account.id)
            if session:
                cosmetics = session.current_cosmetics
                cosmetics.level = level
                await db.update_session_cosmetics(session.id, cosmetics)
            
            await interaction.followup.send(
                f"✅ Level set to **{level}** for `{account.epic_username}`",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Failed to set level. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(name="setcrowns", description="Set bot crown wins count")
    @app_commands.describe(
        epic_username="The Epic username of the bot",
        count="Number of crown wins"
    )
    async def set_crowns(self, interaction: discord.Interaction, epic_username: str, count: int):
        """Set bot's crown wins."""
        # Validate count
        if count < 0:
            await interaction.response.send_message(
                "❌ Crown wins must be a positive number.",
                ephemeral=True
            )
            return
        
        account, bot_instance = await self._get_running_bot(interaction, epic_username)
        if not account:
            return
        
        await interaction.response.defer(ephemeral=True)
        
        success = await bot_instance.set_crown_wins(count)
        
        if success:
            # Update session
            session = await db.get_active_session(account.id)
            if session:
                cosmetics = session.current_cosmetics
                cosmetics.crown_wins = count
                await db.update_session_cosmetics(session.id, cosmetics)
            
            await interaction.followup.send(
                f"✅ Crown wins set to **{count}** for `{account.epic_username}`",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Failed to set crown wins. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(name="synccosmetics", description="Copy cosmetics from one bot to another")
    @app_commands.describe(
        from_username="Source bot Epic username",
        to_username="Target bot Epic username (or 'all' for all bots)"
    )
    async def sync_cosmetics(
        self,
        interaction: discord.Interaction,
        from_username: str,
        to_username: str
    ):
        """Copy cosmetics between bots."""
        discord_id = str(interaction.user.id)
        
        # Get source account and session
        source_account = await db.get_epic_account_by_username(discord_id, from_username)
        if not source_account:
            await interaction.response.send_message(
                f"❌ Source account `{from_username}` not found.",
                ephemeral=True
            )
            return
        
        source_session = await db.get_active_session(source_account.id)
        if not source_session:
            await interaction.response.send_message(
                f"❌ No active session found for `{from_username}`.",
                ephemeral=True
            )
            return
        
        cosmetics = source_session.current_cosmetics
        
        await interaction.response.defer(ephemeral=True)
        
        if to_username.lower() == "all":
            # Apply to all running bots
            user_bots = bot_manager.get_user_bots(discord_id)
            applied = 0
            
            for bot_instance in user_bots:
                if str(bot_instance.account_id) != str(source_account.id):
                    success = await bot_instance.apply_cosmetics(cosmetics)
                    if success:
                        applied += 1
            
            await interaction.followup.send(
                f"✅ Synced cosmetics to {applied} bot(s)!",
                ephemeral=True
            )
        else:
            # Apply to specific bot
            target_account = await db.get_epic_account_by_username(discord_id, to_username)
            if not target_account:
                await interaction.followup.send(
                    f"❌ Target account `{to_username}` not found.",
                    ephemeral=True
                )
                return
            
            target_bot = bot_manager.get_bot(target_account.id)
            if not target_bot:
                await interaction.followup.send(
                    f"❌ Bot `{to_username}` is not running.",
                    ephemeral=True
                )
                return
            
            success = await target_bot.apply_cosmetics(cosmetics)
            
            if success:
                await interaction.followup.send(
                    f"✅ Synced cosmetics from `{from_username}` to `{to_username}`!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to sync cosmetics.",
                    ephemeral=True
                )


async def setup(bot: commands.Bot):
    """Set up the cosmetic commands cog."""
    await bot.add_cog(CosmeticCommands(bot))
