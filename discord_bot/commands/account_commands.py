"""Account management Discord commands."""
import discord
from discord import app_commands
from discord.ext import commands
import logging

from config import get_settings
from database import db
from bot.device_auth import device_auth_service
from utils import encrypt_credentials, decrypt_credentials, get_status_emoji
from discord_bot.views import ConfirmView, AccountListView

logger = logging.getLogger(__name__)


class AccountCommands(commands.Cog):
    """Commands for managing Epic Games accounts."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = get_settings()
        self._pending_auth: dict = {}  # discord_id -> auth info
    
    @app_commands.command(name="addaccount", description="Add an Epic Games account via device auth")
    async def add_account(self, interaction: discord.Interaction):
        """Add a new Epic Games account."""
        discord_id = str(interaction.user.id)
        
        # Check account limit
        account_count = await db.count_user_accounts(discord_id)
        if account_count >= self.settings.max_accounts_per_user:
            await interaction.response.send_message(
                f"🚫 Maximum accounts reached ({account_count}/{self.settings.max_accounts_per_user})\n"
                f"Remove an account with `/removeaccount <username>` to add another.",
                ephemeral=True
            )
            return
        
        # Get or create user
        await db.get_or_create_user(discord_id, interaction.user.name)
        await db.update_user_channel(discord_id, str(interaction.channel_id))
        
        # Send auth URL
        auth_url = device_auth_service.get_auth_url()
        
        embed = discord.Embed(
            title="🔐 Add Epic Games Account",
            description=(
                "**Step 1:** Click the link below to authorize your Epic Games account\n"
                "**Step 2:** Log in to Epic Games and authorize the application\n"
                "**Step 3:** Copy the authorization code from the page\n"
                "**Step 4:** Use `/confirmauth <code>` to complete setup\n\n"
                f"[🔗 Click here to authorize]({auth_url})"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="The authorization code expires in 5 minutes")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="confirmauth", description="Confirm account authorization with the code")
    @app_commands.describe(code="The authorization code from Epic Games")
    async def confirm_auth(self, interaction: discord.Interaction, code: str):
        """Confirm account authorization with the provided code."""
        discord_id = str(interaction.user.id)
        
        await interaction.response.defer(ephemeral=True)
        
        # Exchange code for device auth
        success, credentials, error = await device_auth_service.exchange_code_for_device_auth(code)
        
        if not success:
            await interaction.followup.send(
                f"❌ Failed to authenticate with Epic Games\n{error}\n\nPlease try `/addaccount` again.",
                ephemeral=True
            )
            return
        
        # Check if account already exists
        existing = await db.get_epic_account_by_username(discord_id, credentials["display_name"])
        if existing:
            await interaction.followup.send(
                f"⚠️ Account `{credentials['display_name']}` is already connected!\n"
                f"Use `/listaccounts` to see your accounts.",
                ephemeral=True
            )
            return
        
        # Encrypt and store credentials
        encrypted = encrypt_credentials(
            credentials["device_id"],
            credentials["account_id"],
            credentials["secret"]
        )
        
        await db.add_epic_account(
            discord_id=discord_id,
            epic_username=credentials["display_name"],
            epic_display_name=credentials["display_name"],
            epic_account_id=credentials["account_id"],
            encrypted_credentials=encrypted
        )
        
        embed = discord.Embed(
            title="✅ Account Added Successfully!",
            description=f"**Epic Username:** `{credentials['display_name']}`",
            color=discord.Color.green()
        )
        embed.add_field(name="Next Steps", value=(
            "• Use `/startbot <username>` to start the bot\n"
            "• Use `/listaccounts` to see all your accounts\n"
            "• Use `/botstatus` to check bot status"
        ))
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"User {discord_id} added account {credentials['display_name']}")
    
    @app_commands.command(name="listaccounts", description="Show all your connected Epic accounts")
    async def list_accounts(self, interaction: discord.Interaction):
        """List all connected Epic accounts."""
        discord_id = str(interaction.user.id)
        
        accounts = await db.get_epic_accounts(discord_id)
        
        if not accounts:
            await interaction.response.send_message(
                "📭 You don't have any connected accounts.\n"
                "Use `/addaccount` to add your first Epic Games account!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🎮 Your Epic Games Accounts",
            color=discord.Color.blue()
        )
        
        for account in accounts:
            status_emoji = get_status_emoji(account.status)
            status_text = account.status.upper()
            
            last_used = "Never" if not account.last_used else account.last_used.strftime("%Y-%m-%d %H:%M")
            
            embed.add_field(
                name=f"{status_emoji} {account.epic_username}",
                value=(
                    f"Status: **{status_text}**\n"
                    f"Sessions: {account.total_sessions}\n"
                    f"Last used: {last_used}"
                ),
                inline=True
            )
        
        embed.set_footer(text=f"{len(accounts)}/{self.settings.max_accounts_per_user} accounts")
        
        # Add action buttons
        async def on_test(inter: discord.Interaction, username: str):
            await self._test_account(inter, username)
        
        async def on_remove(inter: discord.Interaction, username: str):
            await self._remove_account(inter, username)
        
        view = AccountListView(accounts, on_test, on_remove)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="removeaccount", description="Remove an Epic Games account")
    @app_commands.describe(epic_username="The Epic username to remove")
    async def remove_account(self, interaction: discord.Interaction, epic_username: str):
        """Remove an Epic Games account."""
        await self._remove_account(interaction, epic_username)
    
    async def _remove_account(self, interaction: discord.Interaction, epic_username: str):
        """Internal method to remove an account."""
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Account `{epic_username}` not found.\n"
                    f"Use `/listaccounts` to see your connected accounts.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Account `{epic_username}` not found.",
                    ephemeral=True
                )
            return
        
        # Confirm deletion
        embed = discord.Embed(
            title="⚠️ Confirm Account Removal",
            description=f"Are you sure you want to remove `{account.epic_username}`?\n\nThis action cannot be undone.",
            color=discord.Color.orange()
        )
        
        view = ConfirmView()
        
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
        await view.wait()
        
        if view.value:
            # Stop bot if running
            from bot import bot_manager
            if bot_manager.get_bot(account.id):
                await bot_manager.stop_bot(account.id, "account_removed")
            
            # Remove from database
            removed = await db.remove_epic_account(discord_id, epic_username)
            
            if removed:
                await interaction.edit_original_response(
                    content=f"✅ Account `{account.epic_username}` has been removed.",
                    embed=None,
                    view=None
                )
                logger.info(f"User {discord_id} removed account {account.epic_username}")
            else:
                await interaction.edit_original_response(
                    content="❌ Failed to remove account. Please try again.",
                    embed=None,
                    view=None
                )
        else:
            await interaction.edit_original_response(
                content="❌ Account removal cancelled.",
                embed=None,
                view=None
            )
    
    @app_commands.command(name="testaccount", description="Test an Epic Games account connection")
    @app_commands.describe(epic_username="The Epic username to test")
    async def test_account(self, interaction: discord.Interaction, epic_username: str):
        """Test an Epic Games account connection."""
        await self._test_account(interaction, epic_username)
    
    async def _test_account(self, interaction: discord.Interaction, epic_username: str):
        """Internal method to test an account."""
        discord_id = str(interaction.user.id)
        
        account = await db.get_epic_account_by_username(discord_id, epic_username)
        if not account:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ Account `{epic_username}` not found.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Account `{epic_username}` not found.",
                    ephemeral=True
                )
            return
        
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        # Decrypt and verify credentials
        try:
            credentials = decrypt_credentials(account.encrypted_credentials)
            is_valid, error = await device_auth_service.verify_device_auth(
                credentials["device_id"],
                credentials["account_id"],
                credentials["secret"]
            )
            
            if is_valid:
                await db.update_epic_account_status(account.epic_account_id, "active")
                await interaction.followup.send(
                    f"✅ Account `{account.epic_username}` is working correctly!",
                    ephemeral=True
                )
            else:
                await db.update_epic_account_status(account.epic_account_id, "error")
                await interaction.followup.send(
                    f"❌ Account `{account.epic_username}` has issues:\n{error}\n\n"
                    f"You may need to remove and re-add this account.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error testing account {epic_username}: {e}")
            await interaction.followup.send(
                f"❌ Error testing account: {str(e)}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Set up the account commands cog."""
    await bot.add_cog(AccountCommands(bot))
