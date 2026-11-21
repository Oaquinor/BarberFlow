"""
Core configuration settings for KingFlow Barber.

All environment variables and application settings are centralized here.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore legacy deployment variables such as unused Redis/Celery URLs.
    )
    
    # Application
    APP_NAME: str = "KingFlow Barber"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_VERSION: str = "v1"
    FRONTEND_BASE_URL: str = "http://localhost:8000"
    
    # Database
    DATABASE_URL: str = "mysql+pymysql://kingflow@localhost:3307/kingflow_barber"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_API_URL: str = "http://127.0.0.1:3001/send"
    # Use the socket address by default; deployments behind a trusted proxy must
    # explicitly select the header that their platform overwrites.
    CLIENT_IP_HEADER: str = "socket"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    
    # Email (Optional - for notifications)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@kingflow.com"
    
    # File Storage
    UPLOAD_DIR: str = str(Path(__file__).resolve().parents[4] / "frontend" / "uploads")
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5MB
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    
    # Multi-tenant
    ENABLE_MULTI_TENANT: bool = True
    
    # Analytics
    ENABLE_ANALYTICS: bool = True
    
@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Using lru_cache ensures settings are loaded once and reused.
    """
    return Settings()
