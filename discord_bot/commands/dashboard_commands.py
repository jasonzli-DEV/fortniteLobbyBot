"""Dashboard and Admin Discord commands with comprehensive UI - single message approach."""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime
from typing import Optional
import asyncio

from config import get_settings
from database import db
from bot import bot_manager, cosmetic_search
from bot.device_auth import device_auth_service
from utils import get_status_emoji, encrypt_credentials, decrypt_credentials

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_session_uptime(session_start: datetime) -> str:
    """Format session uptime as human-readable string."""
    delta = datetime.utcnow() - session_start
    total_seconds = int(delta.total_seconds())
    
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


# =============================================================================
# MODALS
# =============================================================================

class StatusModal(discord.ui.Modal, title="Set Status"):
    """Modal for setting bot status message."""
    
    status_text = discord.ui.TextInput(
        label="Status Message",
        placeholder="Playing with friends...",
        max_length=100,
        required=True
    )
    
    def __init__(self, cog, discord_id, account_id, username):
        super().__init__()
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
    
    async def on_submit(self, interaction: discord.Interaction):
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(self.account_id))
        if not bot_instance or not bot_instance.client:
            await interaction.response.send_message("Bot not running!", ephemeral=True)
            return
        
        try:
            success = await bot_instance.set_status(self.status_text.value)
            if success:
                # Return to dashboard
                embed = await self.cog._build_dashboard_embed(self.discord_id)
                embed.description = f"✅ Status set to: **{self.status_text.value}**"
                view = DashboardView(self.cog, self.discord_id)
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.send_message("❌ Failed to set status", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class LevelModal(discord.ui.Modal, title="Set Level"):
    """Modal for setting bot level."""
    
    level = discord.ui.TextInput(
        label="Level (1-200)",
        placeholder="Enter level...",
        max_length=3,
        required=True
    )
    
    def __init__(self, cog, discord_id, account_id, username):
        super().__init__()
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level.value)
            if not 1 <= level <= 200:
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("Invalid level (1-200)", ephemeral=True)
            return
        
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(self.account_id))
        if not bot_instance or not bot_instance.client:
            await interaction.response.send_message("Bot not running!", ephemeral=True)
            return
        
        try:
            await bot_instance.client.party.me.set_banner(
                icon=bot_instance.client.party.me.banner[0],
                color=bot_instance.client.party.me.banner[1],
                season_level=level
            )
            # Return to dashboard
            embed = await self.cog._build_dashboard_embed(self.discord_id)
            embed.description = f"✅ Level set to **{level}**"
            view = DashboardView(self.cog, self.discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class CosmeticSearchModal(discord.ui.Modal, title="Search Cosmetics"):
    """Modal to search for cosmetics."""
    
    query = discord.ui.TextInput(
        label="Search",
        placeholder="Enter cosmetic name...",
        max_length=50,
        required=True
    )
    
    def __init__(self, cog, discord_id, account_id, cosmetic_type):
        super().__init__()
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.cosmetic_type = cosmetic_type
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        results, total, pages = await cosmetic_search.search(
            cosmetic_type=self.cosmetic_type,
            query=self.query.value,
            page=1
        )
        
        if not results:
            # Return to dashboard with error
            embed = await self.cog._build_dashboard_embed(self.discord_id)
            embed.description = f"❌ No {self.cosmetic_type}s found for '{self.query.value}'"
            view = DashboardView(self.cog, self.discord_id)
            await interaction.edit_original_response(embed=embed, view=view)
            return
        
        # Show results in the same message
        embed = discord.Embed(
            title=f"🔍 {self.cosmetic_type.title()} Results",
            description=f"Found {total} results for '{self.query.value}'\nSelect one below:",
            color=discord.Color.blue()
        )
        
        view = CosmeticResultsView(
            self.cog, self.discord_id, self.account_id,
            self.cosmetic_type, results
        )
        
        await interaction.edit_original_response(embed=embed, view=view)


# =============================================================================
# COSMETIC RESULTS VIEW
# =============================================================================

class CosmeticResultsView(discord.ui.View):
    """View showing cosmetic search results with selection."""
    
    def __init__(self, cog, discord_id, account_id, cosmetic_type, results):
        super().__init__(timeout=120)
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.cosmetic_type = cosmetic_type
        self.results = results
        
        # Add select menu
        options = []
        for item in results[:25]:
            name = item.name if hasattr(item, 'name') else item.get('name', 'Unknown')
            cosmetic_id = item.cosmetic_id if hasattr(item, 'cosmetic_id') else item.get('id', '')
            rarity = item.rarity if hasattr(item, 'rarity') else item.get('rarity', {}).get('displayValue', '')
            
            options.append(discord.SelectOption(
                label=name[:100],
                description=rarity[:100] if rarity else "Unknown Rarity",
                value=cosmetic_id
            ))
        
        if options:
            select = discord.ui.Select(placeholder="Select cosmetic...", options=options)
            select.callback = self.select_callback
            self.add_item(select)
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        view = DashboardView(self.cog, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def select_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.discord_id:
            return
        
        cosmetic_id = interaction.data['values'][0]
        
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(self.account_id))
        if not bot_instance or not bot_instance.client:
            embed = await self.cog._build_dashboard_embed(self.discord_id)
            embed.description = "❌ Bot not running!"
            view = DashboardView(self.cog, self.discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        # Check if the bot has a party
        if not bot_instance.client.party or not bot_instance.client.party.me:
            embed = await self.cog._build_dashboard_embed(self.discord_id)
            embed.description = "❌ Bot is not in a party yet. Please wait a moment and try again."
            view = DashboardView(self.cog, self.discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        await interaction.response.defer()
        
        try:
            # Log for debugging
            logger.info(f"Setting {self.cosmetic_type} with ID: {cosmetic_id}")
            logger.info(f"Party state: party={bot_instance.client.party}, me={bot_instance.client.party.me}")
            
            me = bot_instance.client.party.me
            
            # Check if party member is in dummy state (not fully joined)
            if hasattr(me, '_dummy') and me._dummy:
                logger.warning("Party member is in dummy state - not fully connected yet!")
                embed = await self.cog._build_dashboard_embed(self.discord_id)
                embed.description = "❌ Bot is still connecting to party. Please wait a moment and try again."
                view = DashboardView(self.cog, self.discord_id)
                await interaction.edit_original_response(embed=embed, view=view)
                return
            
            # Wait for meta to be ready (important for fortnitepy)
            try:
                await asyncio.wait_for(me.meta.meta_ready_event.wait(), timeout=5.0)
                logger.info("Meta ready event is set, proceeding with cosmetic change")
            except asyncio.TimeoutError:
                logger.warning("Meta ready event timed out!")
                embed = await self.cog._build_dashboard_embed(self.discord_id)
                embed.description = "❌ Bot meta not ready. Please wait a moment and try again."
                view = DashboardView(self.cog, self.discord_id)
                await interaction.edit_original_response(embed=embed, view=view)
                return
            
            # Log edit lock state
            logger.info(f"Edit lock state: locked={me.edit_lock.locked()}, dummy={getattr(me, '_dummy', 'N/A')}")
            
            if self.cosmetic_type == "outfit":
                # Use the standard await pattern - fortnitepy will handle the patch
                result = await me.set_outfit(asset=cosmetic_id)
                logger.info(f"set_outfit returned: {result}")
            elif self.cosmetic_type == "backpack":
                result = await me.set_backpack(asset=cosmetic_id)
                logger.info(f"set_backpack returned: {result}")
            elif self.cosmetic_type == "pickaxe":
                result = await me.set_pickaxe(asset=cosmetic_id)
                logger.info(f"set_pickaxe returned: {result}")
            elif self.cosmetic_type == "emote":
                # Emotes are instant actions
                result = await me.set_emote(asset=cosmetic_id)
                logger.info(f"set_emote returned: {result}")
            
            # Log the current outfit after setting
            logger.info(f"Current outfit after set: {me.outfit}")
            logger.info(f"Successfully applied {self.cosmetic_type}: {cosmetic_id}")
            
            # Find the name
            name = cosmetic_id
            for item in self.results:
                item_id = item.cosmetic_id if hasattr(item, 'cosmetic_id') else item.get('id', '')
                if item_id == cosmetic_id:
                    name = item.name if hasattr(item, 'name') else item.get('name', cosmetic_id)
                    break
            
            # Return to dashboard with success
            embed = await self.cog._build_dashboard_embed(self.discord_id)
            embed.description = f"✅ Applied {self.cosmetic_type}: **{name}**"
            view = DashboardView(self.cog, self.discord_id)
            await interaction.edit_original_response(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Failed to set {self.cosmetic_type}: {e}", exc_info=True)
            embed = await self.cog._build_dashboard_embed(self.discord_id)
            embed.description = f"❌ Error: {e}"
            view = DashboardView(self.cog, self.discord_id)
            await interaction.edit_original_response(embed=embed, view=view)


# =============================================================================
# FRIEND SEARCH MODAL
# =============================================================================

class FriendSearchModal(discord.ui.Modal, title="Add Friend"):
    """Modal to search for Epic Games users."""
    
    query = discord.ui.TextInput(
        label="Epic Username",
        placeholder="Enter Epic Games username...",
        max_length=50,
        required=True
    )
    
    def __init__(self, cog, discord_id, account_id, username):
        super().__init__()
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(self.account_id))
        if not bot_instance or not bot_instance.client:
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            embed.description = "❌ Bot not running!"
            await interaction.edit_original_response(embed=embed, view=view)
            return
        
        results = await bot_instance.search_users(self.query.value)
        
        if not results:
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            embed.description = f"❌ No users found for '{self.query.value}'"
            await interaction.edit_original_response(embed=embed, view=view)
            return
        
        # Show results
        embed = discord.Embed(
            title="👥 User Search Results",
            description=f"Found {len(results)} user(s) for '{self.query.value}'\nSelect one to add as friend:",
            color=discord.Color.blue()
        )
        
        view = FriendResultsView(
            self.cog, self.discord_id, self.account_id, self.username, results
        )
        
        await interaction.edit_original_response(embed=embed, view=view)


# =============================================================================
# FRIEND RESULTS VIEW
# =============================================================================

class FriendResultsView(discord.ui.View):
    """View showing user search results for friend requests."""
    
    def __init__(self, cog, discord_id, account_id, username, results):
        super().__init__(timeout=120)
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
        self.results = results
        
        # Add select menu
        options = []
        for user in results[:25]:
            display_name = user.get('display_name', 'Unknown')
            user_id = user.get('id', '')
            external = user.get('external_auths', {})
            platform = next(iter(external.keys()), None) if external else None
            desc = f"Platform: {platform}" if platform else "Epic Games"
            
            options.append(discord.SelectOption(
                label=display_name[:100],
                description=desc[:100],
                value=user_id
            ))
        
        if options:
            select = discord.ui.Select(placeholder="Select user to add...", options=options)
            select.callback = self.select_callback
            self.add_item(select)
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def select_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.discord_id:
            return
        
        user_id = interaction.data['values'][0]
        
        # Find the display name
        display_name = user_id
        for user in self.results:
            if user.get('id') == user_id:
                display_name = user.get('display_name', user_id)
                break
        
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(self.account_id))
        if not bot_instance or not bot_instance.client:
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            embed.description = "❌ Bot not running!"
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        await interaction.response.defer()
        
        try:
            success, message = await bot_instance.send_friend_request(user_id)
            
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            if success:
                embed.description = f"✅ Friend request sent to **{display_name}**!"
            else:
                embed.description = f"⚠️ {message}"
            await interaction.edit_original_response(embed=embed, view=view)
            
        except Exception as e:
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            embed.description = f"❌ Error: {e}"
            view = DashboardView(self.cog, self.discord_id)
            await interaction.edit_original_response(embed=embed, view=view)


# =============================================================================
# ACCOUNT SELECT VIEW
# =============================================================================

class AccountSelectView(discord.ui.View):
    """Dropdown to select an account for operations."""
    
    def __init__(self, cog, discord_id, accounts, operation):
        super().__init__(timeout=120)
        self.cog = cog
        self.discord_id = discord_id
        self.operation = operation
        
        options = []
        for acc in accounts[:25]:
            bot = bot_manager.get_bot(acc.id)
            status = "🟢" if bot and bot._running else "⚫"
            options.append(discord.SelectOption(
                label=acc.epic_username,
                description=f"{status} {'Online' if bot else 'Offline'}",
                value=str(acc.id)
            ))
        
        select = discord.ui.Select(placeholder=f"Select account to {operation}...", options=options)
        select.callback = self.select_callback
        self.add_item(select)
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        view = DashboardView(self.cog, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def select_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.discord_id:
            return
        
        account_id = interaction.data['values'][0]
        
        if self.operation == "start":
            await self.cog._handle_start_bot(interaction, account_id)
        elif self.operation == "stop":
            await self.cog._handle_stop_bot(interaction, account_id)
        elif self.operation == "remove":
            await self.cog._show_remove_confirm(interaction, account_id)
        elif self.operation == "cosmetics":
            await self.cog._show_cosmetics_menu(interaction, account_id)
        elif self.operation == "friends":
            await self.cog._show_friends_menu(interaction, account_id)
        elif self.operation == "status":
            await self.cog._show_status_modal(interaction, account_id)


# =============================================================================
# COSMETICS MENU VIEW
# =============================================================================

class CosmeticsMenuView(discord.ui.View):
    """Menu for cosmetic options."""
    
    def __init__(self, cog, discord_id, account_id, username):
        super().__init__(timeout=120)
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
    
    @discord.ui.button(label="Skin", style=discord.ButtonStyle.primary, emoji="👤", row=0)
    async def set_skin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = CosmeticSearchModal(self.cog, self.discord_id, self.account_id, "outfit")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Backbling", style=discord.ButtonStyle.primary, emoji="🎒", row=0)
    async def set_backbling(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = CosmeticSearchModal(self.cog, self.discord_id, self.account_id, "backpack")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Pickaxe", style=discord.ButtonStyle.primary, emoji="⛏️", row=0)
    async def set_pickaxe(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = CosmeticSearchModal(self.cog, self.discord_id, self.account_id, "pickaxe")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Emote", style=discord.ButtonStyle.primary, emoji="💃", row=1)
    async def emote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = CosmeticSearchModal(self.cog, self.discord_id, self.account_id, "emote")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Level", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def set_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = LevelModal(self.cog, self.discord_id, self.account_id, self.username)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, emoji="💬", row=1)
    async def set_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = StatusModal(self.cog, self.discord_id, self.account_id, self.username)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, emoji="◀️", row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        view = DashboardView(self.cog, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=view)


# =============================================================================
# FRIENDS MENU VIEW
# =============================================================================

class FriendsMenuView(discord.ui.View):
    """View for managing friends - view, add, and remove."""
    
    def __init__(self, cog, discord_id, account_id, username, friends=None):
        super().__init__(timeout=120)
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
        self.friends = friends or []
        
        # Add friend removal dropdown if there are friends
        if self.friends:
            options = []
            for friend in self.friends[:25]:
                status = "🟢" if friend.get('online') else "⚫"
                options.append(discord.SelectOption(
                    label=friend.get('display_name', 'Unknown')[:100],
                    description=f"{status} {'Online' if friend.get('online') else 'Offline'}",
                    value=friend.get('id', '')
                ))
            
            select = discord.ui.Select(placeholder="Select friend to remove...", options=options)
            select.callback = self.remove_friend_callback
            self.add_item(select)
    
    async def remove_friend_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.discord_id:
            return
        
        friend_id = interaction.data['values'][0]
        
        # Find the display name
        display_name = friend_id
        for friend in self.friends:
            if friend.get('id') == friend_id:
                display_name = friend.get('display_name', friend_id)
                break
        
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(self.account_id))
        if not bot_instance or not bot_instance.client:
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            embed.description = "❌ Bot not running!"
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        await interaction.response.defer()
        
        try:
            friend = bot_instance.client.get_friend(friend_id)
            if friend:
                await friend.remove()
                embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
                embed.description = f"✅ Removed **{display_name}** from friends!"
            else:
                embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
                embed.description = f"⚠️ Could not find friend to remove"
            await interaction.edit_original_response(embed=embed, view=view)
        except Exception as e:
            embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
            embed.description = f"❌ Error: {e}"
            await interaction.edit_original_response(embed=embed, view=view)
    
    @discord.ui.button(label="Add Friend", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def add_friend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        modal = FriendSearchModal(self.cog, self.discord_id, self.account_id, self.username)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed, view = await self.cog._build_friends_embed(self.discord_id, self.account_id, self.username)
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.danger, emoji="◀️", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        view = DashboardView(self.cog, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=view)


# =============================================================================
# CONFIRM REMOVE VIEW
# =============================================================================

class ConfirmRemoveView(discord.ui.View):
    """Confirm account removal - inline in dashboard."""
    
    def __init__(self, cog, discord_id, account_id, username):
        super().__init__(timeout=60)
        self.cog = cog
        self.discord_id = discord_id
        self.account_id = account_id
        self.username = username
    
    @discord.ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        
        await interaction.response.defer()
        
        from bson import ObjectId
        bot = bot_manager.get_bot(ObjectId(self.account_id))
        if bot:
            await bot_manager.stop_bot(ObjectId(self.account_id), "removed")
        
        await db.remove_epic_account(self.discord_id, self.username)
        
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        embed.description = f"✅ Removed `{self.username}`"
        view = DashboardView(self.cog, self.discord_id)
        await interaction.edit_original_response(embed=embed, view=view)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        view = DashboardView(self.cog, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=view)


# =============================================================================
# ADD ACCOUNT VIEW  
# =============================================================================

class AddAccountView(discord.ui.View):
    """View for adding an account with device code."""
    
    def __init__(self, cog, discord_id):
        super().__init__(timeout=600)
        self.cog = cog
        self.discord_id = discord_id
        self.cancelled = False
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        self.cancelled = True
        device_auth_service.cancel_session(self.discord_id)
        
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        embed.description = "❌ Authentication cancelled"
        view = DashboardView(self.cog, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=view)
        self.stop()


# =============================================================================
# MAIN DASHBOARD VIEW
# =============================================================================

class DashboardView(discord.ui.View):
    """Main interactive dashboard view."""
    
    def __init__(self, cog, discord_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.discord_id = discord_id
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Add Account", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        await self.cog._start_add_account(interaction)
    
    @discord.ui.button(label="Start Bot", style=discord.ButtonStyle.primary, emoji="🚀", row=1)
    async def start_bot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        await self.cog._show_account_select(interaction, "start")
    
    @discord.ui.button(label="Stop Bot", style=discord.ButtonStyle.danger, emoji="⏹️", row=1)
    async def stop_bot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        await self.cog._show_account_select(interaction, "stop")
    
    @discord.ui.button(label="Cosmetics", style=discord.ButtonStyle.primary, emoji="🎨", row=1)
    async def cosmetics(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        await self.cog._show_account_select(interaction, "cosmetics")
    
    @discord.ui.button(label="Friends", style=discord.ButtonStyle.primary, emoji="👥", row=1)
    async def friends(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        await self.cog._show_account_select(interaction, "friends")
    
    @discord.ui.button(label="Start All", style=discord.ButtonStyle.success, emoji="▶️", row=2)
    async def start_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        
        await interaction.response.defer()
        
        accounts = await db.get_epic_accounts(self.discord_id)
        started = 0
        for account in accounts:
            if not bot_manager.get_bot(account.id):
                success, _ = await bot_manager.start_bot(
                    account_id=account.id,
                    discord_id=self.discord_id,
                    epic_username=account.epic_username,
                    encrypted_credentials=account.encrypted_credentials
                )
                if success:
                    started += 1
        
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        embed.description = f"✅ Started {started} bot(s)" if started else "All bots already running!"
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Stop All", style=discord.ButtonStyle.danger, emoji="⏹️", row=2)
    async def stop_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        
        await interaction.response.defer()
        
        user_bots = bot_manager.get_user_bots(self.discord_id)
        stopped = 0
        for bot_instance in list(user_bots):
            success, _ = await bot_manager.stop_bot(bot_instance.account_id, "dashboard")
            if success:
                stopped += 1
        
        embed = await self.cog._build_dashboard_embed(self.discord_id)
        embed.description = f"✅ Stopped {stopped} bot(s)" if stopped else "No bots running!"
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Remove", style=discord.ButtonStyle.secondary, emoji="🗑️", row=2)
    async def remove_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.discord_id:
            return
        await self.cog._show_account_select(interaction, "remove")


# =============================================================================
# ADMIN VIEW
# =============================================================================

class BroadcastModal(discord.ui.Modal, title="Broadcast Message"):
    """Modal for sending broadcast to all active users."""
    
    message = discord.ui.TextInput(
        label="Message",
        placeholder="Enter message to broadcast...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Get all active sessions
        active_sessions = await db.get_all_active_sessions()
        notified_users = set()
        sent = 0
        
        for session in active_sessions:
            if session.discord_id in notified_users:
                continue
            
            user = await db.get_user(session.discord_id)
            if user and user.last_active_channel_id:
                try:
                    channel = self.cog.bot.get_channel(int(user.last_active_channel_id))
                    if channel:
                        embed = discord.Embed(
                            title="📢 System Announcement",
                            description=self.message.value,
                            color=discord.Color.gold(),
                            timestamp=datetime.utcnow()
                        )
                        embed.set_footer(text="From Bot Administrator")
                        await channel.send(f"<@{session.discord_id}>", embed=embed)
                        sent += 1
                        notified_users.add(session.discord_id)
                except Exception as e:
                    logger.error(f"Failed to send broadcast: {e}")
        
        embed = await self.cog._build_admin_embed()
        embed.description = f"📢 Broadcast sent to {sent} user(s)"
        view = AdminView(self.cog)
        await interaction.edit_original_response(embed=embed, view=view)


class AdminView(discord.ui.View):
    """Admin control panel view with enhanced controls."""
    
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog._is_admin(str(interaction.user.id)):
            return
        embed = await self.cog._build_admin_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="My Dashboard", style=discord.ButtonStyle.primary, emoji="📊", row=0)
    async def my_dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Switch to personal dashboard."""
        if not self.cog._is_admin(str(interaction.user.id)):
            return
        discord_id = str(interaction.user.id)
        embed = await self.cog._build_dashboard_embed(discord_id)
        view = DashboardView(self.cog, discord_id)
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Broadcast", style=discord.ButtonStyle.primary, emoji="📢", row=1)
    async def broadcast(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Send broadcast to all active users."""
        if not self.cog._is_admin(str(interaction.user.id)):
            return
        modal = BroadcastModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Refresh Cosmetics", style=discord.ButtonStyle.secondary, emoji="🎨", row=1)
    async def refresh_cosmetics(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Force refresh cosmetic cache."""
        if not self.cog._is_admin(str(interaction.user.id)):
            return
        await interaction.response.defer()
        
        refreshed = await cosmetic_search.refresh_cache(force=True)
        
        embed = await self.cog._build_admin_embed()
        embed.description = "✅ Cosmetic cache refreshed!" if refreshed else "ℹ️ Cache already up to date"
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Stop All Bots", style=discord.ButtonStyle.danger, emoji="🛑", row=2)
    async def stop_all_bots(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog._is_admin(str(interaction.user.id)):
            return
        
        await interaction.response.defer()
        stopped = await bot_manager.stop_all_bots("admin_shutdown")
        
        embed = await self.cog._build_admin_embed()
        embed.description = f"🛑 Stopped {stopped} bot(s) globally"
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Clear Stale Sessions", style=discord.ButtonStyle.secondary, emoji="🧹", row=2)
    async def clear_stale(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Clear sessions for bots that are no longer running."""
        if not self.cog._is_admin(str(interaction.user.id)):
            return
        await interaction.response.defer()
        
        # Get all active sessions and check if bots are running
        active_sessions = await db.get_all_active_sessions()
        cleared = 0
        
        for session in active_sessions:
            bot = bot_manager.get_bot(session.account_id)
            if not bot:
                await db.end_session(session.id, "stale_cleanup")
                cleared += 1
        
        embed = await self.cog._build_admin_embed()
        embed.description = f"🧹 Cleared {cleared} stale session(s)"
        await interaction.edit_original_response(embed=embed, view=self)


# =============================================================================
# MAIN COG
# =============================================================================

class DashboardCommands(commands.Cog):
    """Dashboard and Admin commands with full UI."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
    
    def _is_admin(self, user_id: str) -> bool:
        """Check if user is admin."""
        return self.settings.admin_user_id and user_id == self.settings.admin_user_id
    
    # =========================================================================
    # EMBED BUILDERS
    # =========================================================================
    
    async def _build_dashboard_embed(self, discord_id: str) -> discord.Embed:
        """Build the dashboard embed for a user."""
        user = await db.get_user(discord_id)
        accounts = await db.get_epic_accounts(discord_id)
        running_bots = bot_manager.get_user_bots(discord_id)
        is_admin = self._is_admin(discord_id)
        
        embed = discord.Embed(
            title="📊 Fortnite Bot Dashboard",
            description="Manage your bots with the buttons below",
            color=discord.Color.gold() if is_admin else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Stats - show unlimited for admin
        if is_admin:
            accounts_text = f"{len(accounts)} (♾️ Unlimited)"
            running_text = f"{len(running_bots)} (♾️ Unlimited)"
            timeout_text = "♾️ Unlimited"
        else:
            accounts_text = f"{len(accounts)}/{self.settings.max_accounts_per_user}"
            running_text = f"{len(running_bots)}/{self.settings.max_concurrent_bots_per_user}"
            timeout_text = f"{self.settings.default_session_timeout}min"
        
        embed.add_field(
            name="📈 Statistics",
            value=(
                f"**Accounts:** {accounts_text}\n"
                f"**Running:** {running_text}\n"
                f"**Timeout:** {timeout_text}"
            ),
            inline=True
        )
        
        # Bot Status
        status_lines = []
        for account in accounts[:8]:
            bot_instance = bot_manager.get_bot(account.id)
            if bot_instance and bot_instance._running:
                uptime = format_session_uptime(bot_instance.session_start)
                status_lines.append(f"🟢 **{account.epic_username}** ({uptime})")
            else:
                status_lines.append(f"⚫ **{account.epic_username}**")
        
        if status_lines:
            embed.add_field(
                name="🤖 Bots",
                value="\n".join(status_lines),
                inline=False
            )
        else:
            embed.add_field(
                name="🤖 Bots",
                value="No accounts yet. Click **Add Account** to get started!",
                inline=False
            )
        
        if is_admin:
            embed.set_footer(text="👑 Admin Mode • Unlimited Uptime")
        else:
            embed.set_footer(text="Use buttons below to manage")
        
        return embed
    
    async def _build_admin_embed(self) -> discord.Embed:
        """Build the admin panel embed with comprehensive stats."""
        global_sessions = await db.count_global_active_sessions()
        all_bots = list(bot_manager.active_bots.values())
        unique_users = set(b.discord_id for b in all_bots)
        
        # Get total user and account counts
        total_users = await db.db.users.count_documents({})
        total_accounts = await db.db.epic_accounts.count_documents({})
        
        embed = discord.Embed(
            title="🔧 Admin Control Panel",
            description="System administration and monitoring",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        # Global Stats
        embed.add_field(
            name="🌐 Live Stats",
            value=(
                f"**Active Bots:** {len(all_bots)}/{self.settings.max_concurrent_bots_global}\n"
                f"**Active Sessions:** {global_sessions}\n"
                f"**Active Users:** {len(unique_users)}\n"
                f"**Connected Guilds:** {len(self.bot.guilds)}"
            ),
            inline=True
        )
        
        # Database Stats
        embed.add_field(
            name="📊 Database",
            value=(
                f"**Total Users:** {total_users}\n"
                f"**Total Accounts:** {total_accounts}\n"
                f"**Environment:** {self.settings.environment}\n"
                f"**Timeout:** {self.settings.default_session_timeout}min"
            ),
            inline=True
        )
        
        # Active Bots List
        if all_bots:
            bot_lines = []
            for bot_instance in all_bots[:8]:
                uptime = format_session_uptime(bot_instance.session_start)
                bot_lines.append(f"🟢 **{bot_instance.epic_username}** ({uptime})")
            
            if len(all_bots) > 8:
                bot_lines.append(f"*... +{len(all_bots) - 8} more*")
            
            embed.add_field(
                name="🤖 Active Bots",
                value="\n".join(bot_lines),
                inline=False
            )
        else:
            embed.add_field(
                name="🤖 Active Bots",
                value="No bots currently running",
                inline=False
            )
        
        embed.set_footer(text="👑 Admin Panel • You have unlimited privileges")
        return embed
    
    # =========================================================================
    # HANDLERS
    # =========================================================================
    
    async def _start_add_account(self, interaction: discord.Interaction):
        """Start the add account flow - stays in same message."""
        discord_id = str(interaction.user.id)
        is_admin = self._is_admin(discord_id)
        
        account_count = await db.count_user_accounts(discord_id)
        if not is_admin and account_count >= self.settings.max_accounts_per_user:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = f"❌ Maximum accounts reached ({account_count}/{self.settings.max_accounts_per_user})"
            view = DashboardView(self, discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        await interaction.response.defer()
        
        success, session, error = await device_auth_service.start_device_code_flow(discord_id)
        
        if not success:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = f"❌ Failed: {error}"
            view = DashboardView(self, discord_id)
            await interaction.edit_original_response(embed=embed, view=view)
            return
        
        embed = discord.Embed(
            title="🔐 Add Epic Games Account",
            description=(
                f"**Your Code:** `{session.user_code}`\n\n"
                f"1️⃣ Click the link below\n"
                f"2️⃣ Log in to Epic Games\n"
                f"3️⃣ Enter the code above\n\n"
                f"[🔗 Click here to enter code]({session.verification_uri})\n\n"
                f"⏱️ Expires in {session.expires_in // 60} minutes"
            ),
            color=discord.Color.blue()
        )
        
        view = AddAccountView(self, discord_id)
        await interaction.edit_original_response(embed=embed, view=view)
        
        # Poll in background
        async def poll():
            try:
                success, credentials, error = await device_auth_service.poll_for_completion(discord_id)
                
                if view.cancelled:
                    return
                
                if not success:
                    embed = await self._build_dashboard_embed(discord_id)
                    embed.description = f"❌ {error}"
                    view2 = DashboardView(self, discord_id)
                    try:
                        await interaction.edit_original_response(embed=embed, view=view2)
                    except:
                        pass
                    return
                
                # Check duplicate
                existing = await db.get_epic_account_by_epic_id(credentials["account_id"])
                if existing:
                    embed = await self._build_dashboard_embed(discord_id)
                    embed.description = f"⚠️ `{credentials['display_name']}` is already registered!"
                    view2 = DashboardView(self, discord_id)
                    try:
                        await interaction.edit_original_response(embed=embed, view=view2)
                    except:
                        pass
                    return
                
                # Save
                encrypted = encrypt_credentials(
                    credentials["device_id"],
                    credentials["account_id"],
                    credentials["secret"],
                    credentials.get("client_token")
                )
                
                await db.add_epic_account(
                    discord_id=discord_id,
                    epic_username=credentials["display_name"],
                    epic_display_name=credentials["display_name"],
                    epic_account_id=credentials["account_id"],
                    encrypted_credentials=encrypted
                )
                
                embed = await self._build_dashboard_embed(discord_id)
                embed.description = f"✅ Added `{credentials['display_name']}`!"
                view2 = DashboardView(self, discord_id)
                try:
                    await interaction.edit_original_response(embed=embed, view=view2)
                except:
                    pass
                
            except Exception as e:
                logger.error(f"Error in add account poll: {e}")
        
        asyncio.create_task(poll())
    
    async def _show_account_select(self, interaction: discord.Interaction, operation: str):
        """Show account selection dropdown - edits same message."""
        discord_id = str(interaction.user.id)
        accounts = await db.get_epic_accounts(discord_id)
        
        if not accounts:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = "❌ No accounts. Add one first!"
            view = DashboardView(self, discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        # Filter based on operation
        filtered = accounts
        if operation == "start":
            filtered = [a for a in accounts if not bot_manager.get_bot(a.id)]
            if not filtered:
                embed = await self._build_dashboard_embed(discord_id)
                embed.description = "All bots already running!"
                view = DashboardView(self, discord_id)
                await interaction.response.edit_message(embed=embed, view=view)
                return
        elif operation == "stop":
            filtered = [a for a in accounts if bot_manager.get_bot(a.id)]
            if not filtered:
                embed = await self._build_dashboard_embed(discord_id)
                embed.description = "No bots running!"
                view = DashboardView(self, discord_id)
                await interaction.response.edit_message(embed=embed, view=view)
                return
        elif operation == "cosmetics" or operation == "status":
            filtered = [a for a in accounts if bot_manager.get_bot(a.id)]
            if not filtered:
                embed = await self._build_dashboard_embed(discord_id)
                embed.description = "Start a bot first!"
                view = DashboardView(self, discord_id)
                await interaction.response.edit_message(embed=embed, view=view)
                return
        
        embed = discord.Embed(
            title=f"Select Account to {operation.title()}",
            description="Choose from the dropdown below",
            color=discord.Color.blue()
        )
        
        view = AccountSelectView(self, discord_id, filtered, operation)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _handle_start_bot(self, interaction: discord.Interaction, account_id: str):
        """Handle starting a single bot."""
        from bson import ObjectId
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_id(ObjectId(account_id))
        if not account:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = "❌ Account not found!"
            view = DashboardView(self, discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        await interaction.response.defer()
        
        success, message = await bot_manager.start_bot(
            account_id=account.id,
            discord_id=discord_id,
            epic_username=account.epic_username,
            encrypted_credentials=account.encrypted_credentials
        )
        
        embed = await self._build_dashboard_embed(discord_id)
        embed.description = f"✅ Started `{account.epic_username}`" if success else f"❌ {message}"
        view = DashboardView(self, discord_id)
        await interaction.edit_original_response(embed=embed, view=view)
    
    async def _handle_stop_bot(self, interaction: discord.Interaction, account_id: str):
        """Handle stopping a single bot."""
        from bson import ObjectId
        discord_id = str(interaction.user.id)
        
        await interaction.response.defer()
        
        success, message = await bot_manager.stop_bot(ObjectId(account_id), "dashboard")
        
        embed = await self._build_dashboard_embed(discord_id)
        embed.description = f"✅ {message}" if success else f"❌ {message}"
        view = DashboardView(self, discord_id)
        await interaction.edit_original_response(embed=embed, view=view)
    
    async def _show_remove_confirm(self, interaction: discord.Interaction, account_id: str):
        """Show removal confirmation - inline."""
        from bson import ObjectId
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_id(ObjectId(account_id))
        if not account:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = "❌ Account not found!"
            view = DashboardView(self, discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        embed = discord.Embed(
            title="⚠️ Confirm Removal",
            description=f"Remove `{account.epic_username}`?\n\nThis cannot be undone.",
            color=discord.Color.orange()
        )
        
        view = ConfirmRemoveView(self, discord_id, account_id, account.epic_username)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _show_cosmetics_menu(self, interaction: discord.Interaction, account_id: str):
        """Show cosmetics menu for an account."""
        from bson import ObjectId
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_id(ObjectId(account_id))
        if not account:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = "❌ Account not found!"
            view = DashboardView(self, discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        embed = discord.Embed(
            title=f"🎨 Cosmetics: {account.epic_username}",
            description="Select what you want to change",
            color=discord.Color.purple()
        )
        
        view = CosmeticsMenuView(self, discord_id, account_id, account.epic_username)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _show_friends_menu(self, interaction: discord.Interaction, account_id: str):
        """Show friends menu for an account."""
        discord_id = str(interaction.user.id)
        
        from bson import ObjectId
        account = await db.get_epic_account_by_id(ObjectId(account_id))
        if not account:
            embed = await self._build_dashboard_embed(discord_id)
            embed.description = "❌ Account not found!"
            view = DashboardView(self, discord_id)
            await interaction.response.edit_message(embed=embed, view=view)
            return
        
        embed, view = await self._build_friends_embed(discord_id, account_id, account.epic_username)
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _build_friends_embed(self, discord_id: str, account_id: str, username: str):
        """Build friends embed and view for an account."""
        from bson import ObjectId
        bot_instance = bot_manager.get_bot(ObjectId(account_id))
        
        if not bot_instance or not bot_instance.client:
            embed = discord.Embed(
                title=f"👥 Friends: {username}",
                description="❌ Bot not running! Start the bot first.",
                color=discord.Color.red()
            )
            view = FriendsMenuView(self, discord_id, account_id, username, [])
            return embed, view
        
        friends = await bot_instance.get_friends_list()
        online_count = sum(1 for f in friends if f.get('online'))
        
        embed = discord.Embed(
            title=f"👥 Friends: {username}",
            description=f"**{len(friends)}** friends ({online_count} online)\n\nSelect a friend to remove or add a new one.",
            color=discord.Color.blue()
        )
        
        # Show first 10 friends in embed
        if friends:
            friend_list = []
            for f in friends[:10]:
                status = "🟢" if f.get('online') else "⚫"
                friend_list.append(f"{status} {f.get('display_name', 'Unknown')}")
            embed.add_field(
                name="Friends List",
                value="\n".join(friend_list) + (f"\n*...and {len(friends) - 10} more*" if len(friends) > 10 else ""),
                inline=False
            )
        else:
            embed.add_field(name="Friends List", value="No friends yet", inline=False)
        
        view = FriendsMenuView(self, discord_id, account_id, username, friends)
        return embed, view
    
    async def _show_status_modal(self, interaction: discord.Interaction, account_id: str):
        """Show status modal for an account."""
        from bson import ObjectId
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_id(ObjectId(account_id))
        if not account:
            return
        
        modal = StatusModal(self, discord_id, account_id, account.epic_username)
        await interaction.response.send_modal(modal)
    
    # =========================================================================
    # COMMANDS
    # =========================================================================
    
    @app_commands.command(name="dashboard", description="Open your bot control dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        """Show the user's dashboard."""
        discord_id = str(interaction.user.id)
        
        await db.get_or_create_user(discord_id, interaction.user.name)
        await db.update_user_channel(discord_id, str(interaction.channel_id))
        
        embed = await self._build_dashboard_embed(discord_id)
        view = DashboardView(self, discord_id)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="admin", description="Admin control panel (admin only)")
    async def admin(self, interaction: discord.Interaction):
        """Show the admin control panel."""
        discord_id = str(interaction.user.id)
        
        if not self._is_admin(discord_id):
            await interaction.response.send_message(
                "🚫 Access denied. Admin only.",
                ephemeral=True
            )
            return
        
        embed = await self._build_admin_embed()
        view = AdminView(self)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    """Set up the dashboard commands cog."""
    await bot.add_cog(DashboardCommands(bot))
