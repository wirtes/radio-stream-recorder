"""
Database configuration and base model setup for the audio stream recorder.
"""

from datetime import datetime
from enum import Enum
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class RecordingStatus(Enum):
    """Enumeration for recording session status."""
    SCHEDULED = "scheduled"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TransferStatus(Enum):
    """Enumeration for file transfer status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DatabaseManager:
    """Manages database connection and session creation."""
    
    def __init__(self, database_url: str = "sqlite:///data/audio_recorder.db"):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self):
        """Get a database session."""
        return self.SessionLocal()


# Global database manager instance
_db_manager = None


def init_db(database_url: str = "sqlite:///data/audio_recorder.db"):
    """Initialize the database connection."""
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    return _db_manager


def create_tables():
    """Create all database tables."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    _db_manager.create_tables()


def get_db_manager():
    """Get the database manager instance."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_manager


def get_db_session():
    """Get a database session context manager."""
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    
    class SessionContext:
        def __enter__(self):
            self.session = _db_manager.get_session()
            return self.session
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is not None:
                self.session.rollback()
            else:
                self.session.commit()
            self.session.close()
    
    return SessionContext()