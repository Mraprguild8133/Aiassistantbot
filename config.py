import os
import logging
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Config:
    """Configuration class for the Telegram bot"""
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
    
    # Google Gemini AI Configuration
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    
    # Flask Configuration
    SECRET_KEY = os.environ.get("SESSION_SECRET", "dev-secret-key")
    
    # MongoDB Configuration
    DATABASE_URL = os.environ.get("DATABASE_URL", "mongodb://localhost:27017/telegram_bot")
    
    @classmethod
    def get_mongodb_settings(cls):
        """Parse DATABASE_URL and return MongoDB connection settings"""
        if cls.DATABASE_URL.startswith('mongodb://'):
            parsed = urlparse(cls.DATABASE_URL)
            return {
                'host': parsed.hostname or 'localhost',
                'port': parsed.port or 27017,
                'username': parsed.username,
                'password': parsed.password,
                'db': parsed.path.lstrip('/') or 'telegram_bot'
            }
        else:
            # MongoDB Atlas or other connection string
            return {'host': cls.DATABASE_URL}
    
    # Deployment Configuration
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
    
    # Webhook Configuration
    WEBHOOK_HOST = "0.0.0.0"
    WEBHOOK_PORT = int(os.environ.get("PORT", 5000))
    WEBHOOK_PATH = f"/webhook/{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else "/webhook/token"
    
    @classmethod
    def validate(cls):
        """Validate that all required configuration is present"""
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN environment variable is required")
        
        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY environment variable is required")
            
        # Validate MongoDB connection
        try:
            cls.get_mongodb_settings()
        except Exception as e:
            errors.append(f"Invalid DATABASE_URL: {str(e)}")
            
        if errors:
            raise ValueError("Configuration errors: " + ", ".join(errors))
        
        return True
