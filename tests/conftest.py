"""
Pytest configuration and fixtures for testing.
"""

import pytest
import tempfile
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.database import Base, DatabaseManager
from src.models.repositories import ConfigurationRepository, ScheduleRepository, SessionRepository


@pytest.fixture(scope="function")
def temp_db():
    """Create a temporary SQLite database for testing."""
    # Create temporary file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    # Create database manager with temporary database
    db_manager = DatabaseManager(f"sqlite:///{db_path}")
    db_manager.create_tables()
    
    yield db_manager
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def config_repo(temp_db):
    """Create ConfigurationRepository with temporary database."""
    return ConfigurationRepository(temp_db)


@pytest.fixture
def schedule_repo(temp_db):
    """Create ScheduleRepository with temporary database."""
    return ScheduleRepository(temp_db)


@pytest.fixture
def session_repo(temp_db):
    """Create SessionRepository with temporary database."""
    return SessionRepository(temp_db)


@pytest.fixture
def sample_stream_config_data():
    """Sample stream configuration data for testing."""
    return {
        "name": "Test Stream",
        "stream_url": "https://example.com/stream.mp3",
        "artist": "Test Artist",
        "album": "Test Album",
        "album_artist": "Test Album Artist",
        "artwork_path": "/path/to/artwork.jpg",
        "output_filename_pattern": "{date}_{name}.mp3",
        "scp_destination": "user@host:/path/to/destination"
    }


@pytest.fixture
def sample_schedule_data():
    """Sample recording schedule data for testing."""
    return {
        "stream_config_id": 1,
        "cron_expression": "0 1 * * *",  # Daily at 1 AM
        "duration_minutes": 60,
        "is_active": True,
        "max_retries": 3
    }


@pytest.fixture
def sample_session_data():
    """Sample recording session data for testing."""
    return {
        "schedule_id": 1,
        "start_time": datetime.utcnow()
    }