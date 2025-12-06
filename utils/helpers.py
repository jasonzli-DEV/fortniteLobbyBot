"""Utility helpers for the bot."""
import logging
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


def format_uptime(start_time: datetime) -> str:
    """Format uptime as human-readable string."""
    delta = datetime.utcnow() - start_time
    total_seconds = int(delta.total_seconds())
    
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def format_time_remaining(last_activity: datetime, timeout_minutes: int) -> str:
    """Format remaining time before timeout."""
    elapsed = datetime.utcnow() - last_activity
    remaining = timedelta(minutes=timeout_minutes) - elapsed
    
    if remaining.total_seconds() <= 0:
        return "0s"
    
    total_seconds = int(remaining.total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def calculate_remaining_seconds(last_activity: datetime, timeout_minutes: int) -> int:
    """Calculate remaining seconds before timeout."""
    elapsed = datetime.utcnow() - last_activity
    remaining = timedelta(minutes=timeout_minutes) - elapsed
    return max(0, int(remaining.total_seconds()))


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., '2 hours ago')."""
    if dt is None:
        return "Never"
    
    delta = datetime.utcnow() - dt
    total_seconds = int(delta.total_seconds())
    
    if total_seconds < 60:
        return "Just now"
    
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def get_rarity_emoji(rarity: str) -> str:
    """Get emoji for cosmetic rarity."""
    rarity_emojis = {
        "common": "⬜",
        "uncommon": "🟢",
        "rare": "🔵",
        "epic": "🟣",
        "legendary": "🟠",
        "mythic": "🟡",
        "icon series": "🔷",
        "gaming legends": "🎮",
        "marvel": "🔴",
        "dc": "🦇",
        "star wars": "⭐",
    }
    return rarity_emojis.get(rarity.lower(), "⬜")


def get_status_emoji(status: str) -> str:
    """Get emoji for bot status."""
    status_emojis = {
        "active": "🟢",
        "idle_warning": "🟡",
        "stopped": "⚫",
        "error": "🔴",
        "banned": "🔴"
    }
    return status_emojis.get(status.lower(), "⚫")


def truncate_string(s: str, max_length: int = 50) -> str:
    """Truncate string with ellipsis if too long."""
    if len(s) <= max_length:
        return s
    return s[:max_length - 3] + "..."
