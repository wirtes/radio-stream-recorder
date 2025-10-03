"""
Configuration management for Audio Stream Recorder.
Handles environment variables and application settings.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


class Config:
    """Application configuration class."""
    
    # Web Interface Configuration
    WEB_PORT: int = int(os.getenv('WEB_PORT', '8666'))
    WEB_HOST: str = os.getenv('WEB_HOST', '0.0.0.0')
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Flask Configuration
    DEBUG: bool = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    TESTING: bool = False
    WTF_CSRF_ENABLED: bool = True
    WTF_CSRF_TIME_LIMIT: int = 3600  # 1 hour
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB max file upload
    
    # Database Configuration
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///data/audio_recorder.db')
    DATA_DIR: str = os.getenv('DATA_DIR', 'data')
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR: str = os.getenv('LOG_DIR', 'logs')
    
    # Recording Configuration
    MAX_CONCURRENT_RECORDINGS: int = int(os.getenv('MAX_CONCURRENT_RECORDINGS', '3'))
    RECORDINGS_DIR: str = os.getenv('RECORDINGS_DIR', 'recordings')
    
    # File Transfer Configuration
    CLEANUP_AFTER_TRANSFER: bool = os.getenv('CLEANUP_AFTER_TRANSFER', 'true').lower() == 'true'
    
    # Artwork Configuration
    ARTWORK_DIR: str = os.getenv('ARTWORK_DIR', 'artwork')
    MAX_ARTWORK_SIZE_MB: int = int(os.getenv('MAX_ARTWORK_SIZE_MB', '10'))
    
    # SSH Configuration
    SSH_CONFIG_DIR: str = os.getenv('SSH_CONFIG_DIR', 'config')
    
    # Retry Configuration
    DEFAULT_MAX_RETRIES: int = int(os.getenv('DEFAULT_MAX_RETRIES', '3'))
    RETRY_DELAY_SECONDS: int = int(os.getenv('RETRY_DELAY_SECONDS', '60'))
    
    # FFmpeg Configuration
    FFMPEG_PATH: str = os.getenv('FFMPEG_PATH', 'ffmpeg')
    
    @classmethod
    def ensure_directories(cls) -> None:
        """Create necessary directories if they don't exist."""
        directories = [
            cls.LOG_DIR,
            cls.RECORDINGS_DIR,
            cls.ARTWORK_DIR,
            cls.SSH_CONFIG_DIR,
            'data'  # For database
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
    
    @classmethod
    def validate_config(cls) -> None:
        """Validate configuration settings."""
        if cls.WEB_PORT < 1 or cls.WEB_PORT > 65535:
            raise ValueError(f"Invalid WEB_PORT: {cls.WEB_PORT}")
        
        if cls.MAX_CONCURRENT_RECORDINGS < 1:
            raise ValueError(f"MAX_CONCURRENT_RECORDINGS must be at least 1")
        
        if cls.MAX_ARTWORK_SIZE_MB < 1:
            raise ValueError(f"MAX_ARTWORK_SIZE_MB must be at least 1")


# Global configuration instance
config = Config()