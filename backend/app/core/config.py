"""
Configuration settings for KingFlow Barber
Includes email, SMS, and WhatsApp notification settings
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""

    # ==================== DATABASE ====================
    DATABASE_URL: str = "mysql+pymysql://kingflow:kingflow123@localhost:3306/kingflow_barber"

    # ==================== SECURITY ====================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ==================== EMAIL / SMTP ====================
    SMTP_HOST: str = "smtp.gmail.com"  # or smtp.sendgrid.net, smtp.mailgun.org
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None  # Your email or SMTP username
    SMTP_PASSWORD: Optional[str] = None  # Your email password or API key
    SMTP_FROM_EMAIL: str = "noreply@kingflowbarber.com"
    SMTP_FROM_NAME: str = "KingFlow Barber"
    SMTP_TLS: bool = True

    # Email feature flags
    SEND_CONFIRMATION_EMAILS: bool = True
    SEND_REMINDER_EMAILS: bool = True
    SEND_CANCELLATION_EMAILS: bool = True
    SEND_COMPLETION_EMAILS: bool = True

    # ==================== SMS / TWILIO ====================
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None  # Your Twilio phone number

    # SMS feature flags
    SEND_SMS_NOTIFICATIONS: bool = False  # Enable when Twilio is configured

    # ==================== WHATSAPP / TWILIO ====================
    TWILIO_WHATSAPP_NUMBER: Optional[str] = None  # Format: whatsapp:+14155238886

    # WhatsApp feature flags
    SEND_WHATSAPP_NOTIFICATIONS: bool = False  # Enable when Twilio WhatsApp is configured

    # ==================== NOTIFICATIONS ====================
    NOTIFICATION_RETRY_ATTEMPTS: int = 3
    NOTIFICATION_RETRY_DELAY: int = 60  # seconds

    # Reminder settings
    REMINDER_HOURS_BEFORE: int = 24  # Send reminder 24h before

    # ==================== APPLICATION ====================
    APP_NAME: str = "KingFlow Barber"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ==================== CORS ====================
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()


# ==================== EMAIL PROVIDER EXAMPLES ====================

"""
### GMAIL SMTP Configuration:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password  # Not your regular password!
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_TLS=True

Note: You need to enable "Less secure app access" or use "App Passwords" in Gmail.

### SENDGRID SMTP Configuration:
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_TLS=True

### MAILGUN SMTP Configuration:
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=postmaster@your-domain.mailgun.org
SMTP_PASSWORD=your-mailgun-password
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_TLS=True

### TWILIO SMS Configuration:
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890
SEND_SMS_NOTIFICATIONS=True

### TWILIO WHATSAPP Configuration:
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
SEND_WHATSAPP_NOTIFICATIONS=True
"""
