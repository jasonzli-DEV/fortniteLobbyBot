"""Discord UI components - views, modals, and buttons."""
import discord
from discord import ui
from typing import Optional, Callable, Any, List
import asyncio

from database import CosmeticCache
from utils import get_rarity_emoji


class ConfirmView(ui.View):
    """A simple confirmation view with Yes/No buttons."""
    
    def __init__(self, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.value: Optional[bool] = None
    
    @ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()
    
    @ui.button(label="No", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()


class CosmeticSearchModal(ui.Modal):
    """Modal for entering cosmetic search query."""
    
    def __init__(self, cosmetic_type: str):
        super().__init__(title=f"Search for {cosmetic_type.title()}")
        self.cosmetic_type = cosmetic_type
        self.search_query: Optional[str] = None
        
        self.query_input = ui.TextInput(
            label=f"Enter {cosmetic_type} name",
            placeholder=f"e.g., galaxy, renegade, travis...",
            min_length=2,
            max_length=50,
            required=True
        )
        self.add_item(self.query_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.search_query = self.query_input.value
        await interaction.response.defer()


class CosmeticButton(ui.Button):
    """Button for selecting a cosmetic."""
    
    def __init__(
        self,
        cosmetic: CosmeticCache,
        callback: Callable[[discord.Interaction, CosmeticCache], Any]
    ):
        emoji = get_rarity_emoji(cosmetic.rarity)
        label = cosmetic.display_name[:80] if len(cosmetic.display_name) > 80 else cosmetic.display_name
        
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"cosmetic_{cosmetic.cosmetic_id}"
        )
        self.cosmetic = cosmetic
        self._callback = callback
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self.cosmetic)


class CosmeticSearchView(ui.View):
    """View for displaying cosmetic search results with pagination."""
    
    def __init__(
        self,
        cosmetics: List[CosmeticCache],
        page: int,
        total_pages: int,
        cosmetic_type: str,
        query: str,
        on_select: Callable[[discord.Interaction, CosmeticCache], Any],
        on_page_change: Callable[[discord.Interaction, int], Any],
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.page = page
        self.total_pages = total_pages
        self.cosmetic_type = cosmetic_type
        self.query = query
        self.on_select = on_select
        self.on_page_change = on_page_change
        self.selected_cosmetic: Optional[CosmeticCache] = None
        
        # Add cosmetic buttons (max 20 per page to leave room for navigation)
        for cosmetic in cosmetics[:20]:
            self.add_item(CosmeticButton(cosmetic, self._handle_select))
        
        # Add navigation buttons if needed
        if total_pages > 1:
            self.add_item(PaginationButton("◀️ Previous", -1, page > 1, self._handle_page))
            self.add_item(PageIndicatorButton(page, total_pages))
            self.add_item(PaginationButton("Next ▶️", 1, page < total_pages, self._handle_page))
        
        # Add cancel button
        self.add_item(CancelButton(self._handle_cancel))
    
    async def _handle_select(self, interaction: discord.Interaction, cosmetic: CosmeticCache):
        self.selected_cosmetic = cosmetic
        self.stop()
        await self.on_select(interaction, cosmetic)
    
    async def _handle_page(self, interaction: discord.Interaction, direction: int):
        new_page = self.page + direction
        if 1 <= new_page <= self.total_pages:
            await self.on_page_change(interaction, new_page)
            self.stop()
    
    async def _handle_cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(content="❌ Search cancelled", embed=None, view=None)


class PaginationButton(ui.Button):
    """Button for pagination."""
    
    def __init__(
        self,
        label: str,
        direction: int,
        enabled: bool,
        callback: Callable[[discord.Interaction, int], Any]
    ):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            disabled=not enabled,
            row=4
        )
        self.direction = direction
        self._callback = callback
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self.direction)


class PageIndicatorButton(ui.Button):
    """Non-interactive button showing current page."""
    
    def __init__(self, page: int, total_pages: int):
        super().__init__(
            label=f"Page {page}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=4
        )
    
    async def callback(self, interaction: discord.Interaction):
        pass


class CancelButton(ui.Button):
    """Cancel button."""
    
    def __init__(self, callback: Callable[[discord.Interaction], Any]):
        super().__init__(
            label="Cancel",
            emoji="❌",
            style=discord.ButtonStyle.danger,
            row=4
        )
        self._callback = callback
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction)


class BotStatusView(ui.View):
    """View for bot status with action buttons."""
    
    def __init__(
        self,
        account_id: str,
        is_online: bool,
        on_start: Callable,
        on_stop: Callable,
        on_extend: Callable,
        on_refresh: Callable,
        timeout: float = 300.0
    ):
        super().__init__(timeout=timeout)
        self.account_id = account_id
        
        if is_online:
            self.add_item(ActionButton("Stop", "🛑", discord.ButtonStyle.danger, on_stop, account_id))
            self.add_item(ActionButton("Extend", "⏱️", discord.ButtonStyle.primary, on_extend, account_id))
        else:
            self.add_item(ActionButton("Start Bot", "🚀", discord.ButtonStyle.success, on_start, account_id))
        
        self.add_item(ActionButton("Refresh", "🔄", discord.ButtonStyle.secondary, on_refresh, account_id))


class ActionButton(ui.Button):
    """Generic action button."""
    
    def __init__(
        self,
        label: str,
        emoji: str,
        style: discord.ButtonStyle,
        callback: Callable,
        account_id: str
    ):
        super().__init__(label=label, emoji=emoji, style=style)
        self._callback = callback
        self.account_id = account_id
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self.account_id)


class AccountListView(ui.View):
    """View for listing accounts with action buttons."""
    
    def __init__(
        self,
        accounts: list,
        on_test: Callable,
        on_remove: Callable,
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        
        for account in accounts[:5]:  # Max 5 accounts
            self.add_item(AccountActionButton(
                f"Test {account.epic_username}",
                "🔍",
                discord.ButtonStyle.secondary,
                on_test,
                account.epic_username
            ))


class AccountActionButton(ui.Button):
    """Button for account actions."""
    
    def __init__(
        self,
        label: str,
        emoji: str,
        style: discord.ButtonStyle,
        callback: Callable,
        epic_username: str
    ):
        super().__init__(label=label[:80], emoji=emoji, style=style)
        self._callback = callback
        self.epic_username = epic_username
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self.epic_username)


class PresetListView(ui.View):
    """View for listing presets with action buttons."""
    
    def __init__(
        self,
        presets: list,
        on_load: Callable,
        on_delete: Callable,
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        
        for preset in presets[:10]:  # Max 10 presets
            self.add_item(PresetButton(
                f"Load: {preset.name}",
                "📥",
                discord.ButtonStyle.primary,
                on_load,
                preset.name
            ))


class PresetButton(ui.Button):
    """Button for preset actions."""
    
    def __init__(
        self,
        label: str,
        emoji: str,
        style: discord.ButtonStyle,
        callback: Callable,
        preset_name: str
    ):
        super().__init__(label=label[:80], emoji=emoji, style=style)
        self._callback = callback
        self.preset_name = preset_name
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self.preset_name)
