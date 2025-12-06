"""
Configuration settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # MongoDB Connection
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    
    # Discord Bot
    discord_bot_token: str = Field(..., env="DISCORD_BOT_TOKEN")
    discord_guild_id: str | None = Field(None, env="DISCORD_GUILD_ID")
    
    # Security
    encryption_key: str = Field(..., env="ENCRYPTION_KEY")
    
    # Timeout Settings
    default_session_timeout: int = Field(30, env="DEFAULT_SESSION_TIMEOUT")
    timeout_warning_threshold: int = Field(5, env="TIMEOUT_WARNING_THRESHOLD")
    session_extension_duration: int = Field(15, env="SESSION_EXTENSION_DURATION")
    max_extensions_per_session: int = Field(2, env="MAX_EXTENSIONS_PER_SESSION")
    
    # Resource Limits
    max_accounts_per_user: int = Field(5, env="MAX_ACCOUNTS_PER_USER")
    max_concurrent_bots_per_user: int = Field(3, env="MAX_CONCURRENT_BOTS_PER_USER")
    max_concurrent_bots_global: int = Field(50, env="MAX_CONCURRENT_BOTS_GLOBAL")
    command_rate_limit: int = Field(10, env="COMMAND_RATE_LIMIT")
    
    # Cosmetic Search Settings
    cosmetic_results_per_page: int = Field(25, env="COSMETIC_RESULTS_PER_PAGE")
    cosmetic_cache_refresh_hours: int = Field(24, env="COSMETIC_CACHE_REFRESH_HOURS")
    
    # Admin Settings
    admin_user_id: str | None = Field(None, env="ADMIN_USER_ID")
    
    # System Settings
    environment: str = Field("production", env="ENVIRONMENT")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
