"""
Test configuration and utilities for web interface tests.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from src.web.app import create_app
from src.config import Config


class TestWebConfig(Config):
    """Test configuration for web interface."""
    
    TESTING = True
    DEBUG = True
    DATABASE_URL = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key-for-testing'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing
    
    # Override directories for testing
    LOG_DIR = tempfile.mkdtemp()
    RECORDINGS_DIR = tempfile.mkdtemp()
    ARTWORK_DIR = tempfile.mkdtemp()
    SSH_CONFIG_DIR = tempfile.mkdtemp()
    
    # Test-specific settings
    MAX_CONCURRENT_RECORDINGS = 1
    MAX_ARTWORK_SIZE_MB = 1  # Smaller for testing


@pytest.fixture(scope='session')
def test_app():
    """Create test application for the entire test session."""
    app = create_app(TestWebConfig)
    
    with app.app_context():
        # Initialize test database
        from src.models.database import DatabaseManager
        db_manager = DatabaseManager(TestWebConfig.DATABASE_URL)
        db_manager.create_tables()
        
        yield app


@pytest.fixture
def app(test_app):
    """Provide test application for individual tests."""
    return test_app


@pytest.fixture
def client(app):
    """Create test client for making requests."""
    return app.test_client()


@pytest.fixture
def mock_database_manager():
    """Mock database manager for testing."""
    with patch('src.models.database.DatabaseManager') as mock_db:
        mock_instance = MagicMock()
        mock_db.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_stream_recorder():
    """Mock stream recorder for testing."""
    with patch('src.services.stream_recorder.StreamRecorder') as mock_recorder:
        mock_instance = MagicMock()
        mock_recorder.return_value = mock_instance
        
        # Default successful test result
        mock_instance.test_stream_connection.return_value = {
            'success': True,
            'message': 'Connection successful',
            'format': 'mp3',
            'bitrate': '128k'
        }
        
        yield mock_instance


@pytest.fixture
def sample_stream_data():
    """Sample stream configuration data for testing."""
    return {
        'name': 'Test Stream',
        'stream_url': 'http://example.com/test-stream',
        'artist': 'Test Artist',
        'album': 'Test Album',
        'album_artist': 'Test Album Artist',
        'output_filename_pattern': '{date}_{name}.mp3',
        'scp_destination': 'user@example.com:/recordings/'
    }


@pytest.fixture
def sample_schedule_data():
    """Sample schedule data for testing."""
    return {
        'stream_config_id': 1,
        'cron_expression': '0 9 * * 1-5',
        'duration_minutes': 60,
        'max_retries': 3,
        'is_active': True
    }


@pytest.fixture
def mock_system_metrics():
    """Mock system metrics for testing."""
    return {
        'timestamp': '2023-01-01T12:00:00Z',
        'cpu': {
            'usage_percent': 25.5,
            'count': 4
        },
        'memory': {
            'total_gb': 8.0,
            'available_gb': 4.0,
            'used_gb': 4.0,
            'usage_percent': 50.0
        },
        'disk': {
            'total_gb': 100.0,
            'free_gb': 60.0,
            'used_gb': 40.0,
            'usage_percent': 40.0
        },
        'network': {
            'bytes_sent': 1024000,
            'bytes_recv': 2048000,
            'packets_sent': 1000,
            'packets_recv': 1500
        }
    }


def create_test_image_file(filename='test.png', size=1024):
    """Create a test image file for upload testing."""
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=f'.{filename.split(".")[-1]}', delete=False) as tmp_file:
        # Create fake image data
        fake_png_header = b'\x89PNG\r\n\x1a\n'
        fake_image_data = fake_png_header + b'0' * (size - len(fake_png_header))
        tmp_file.write(fake_image_data)
        return tmp_file.name


def cleanup_test_files(*file_paths):
    """Clean up test files."""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except OSError:
                pass  # Ignore cleanup errors


class MockStreamConfiguration:
    """Mock stream configuration object."""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.name = kwargs.get('name', 'Test Stream')
        self.stream_url = kwargs.get('stream_url', 'http://example.com/stream')
        self.artist = kwargs.get('artist', 'Test Artist')
        self.album = kwargs.get('album', 'Test Album')
        self.album_artist = kwargs.get('album_artist', 'Test Album Artist')
        self.artwork_path = kwargs.get('artwork_path', None)
        self.output_filename_pattern = kwargs.get('output_filename_pattern', '{date}_{name}.mp3')
        self.scp_destination = kwargs.get('scp_destination', 'user@host:/path/')
        self.created_at = kwargs.get('created_at', '2023-01-01T00:00:00Z')
        self.updated_at = kwargs.get('updated_at', '2023-01-01T00:00:00Z')


class MockRecordingSchedule:
    """Mock recording schedule object."""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.stream_config_id = kwargs.get('stream_config_id', 1)
        self.cron_expression = kwargs.get('cron_expression', '0 9 * * *')
        self.duration_minutes = kwargs.get('duration_minutes', 60)
        self.is_active = kwargs.get('is_active', True)
        self.next_run_time = kwargs.get('next_run_time', None)
        self.last_run_time = kwargs.get('last_run_time', None)
        self.retry_count = kwargs.get('retry_count', 0)
        self.max_retries = kwargs.get('max_retries', 3)
        self.created_at = kwargs.get('created_at', '2023-01-01T00:00:00Z')
        self.updated_at = kwargs.get('updated_at', '2023-01-01T00:00:00Z')


class MockRecordingSession:
    """Mock recording session object."""
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.schedule_id = kwargs.get('schedule_id', 1)
        self.start_time = kwargs.get('start_time', '2023-01-01T09:00:00Z')
        self.end_time = kwargs.get('end_time', None)
        self.status = kwargs.get('status', 'completed')
        self.output_file_path = kwargs.get('output_file_path', '/recordings/test.mp3')
        self.error_message = kwargs.get('error_message', None)
        self.file_size_bytes = kwargs.get('file_size_bytes', 1024000)
        self.transfer_status = kwargs.get('transfer_status', 'completed')


# Test data generators
def generate_test_streams(count=5):
    """Generate test stream configurations."""
    streams = []
    for i in range(count):
        streams.append(MockStreamConfiguration(
            id=i + 1,
            name=f'Test Stream {i + 1}',
            stream_url=f'http://example.com/stream{i + 1}',
            artist=f'Artist {i + 1}',
            album=f'Album {i + 1}',
            album_artist=f'Album Artist {i + 1}'
        ))
    return streams


def generate_test_schedules(count=3):
    """Generate test recording schedules."""
    schedules = []
    cron_expressions = ['0 9 * * *', '0 14 * * 1-5', '0 20 * * 0']
    
    for i in range(count):
        schedules.append(MockRecordingSchedule(
            id=i + 1,
            stream_config_id=i + 1,
            cron_expression=cron_expressions[i % len(cron_expressions)],
            duration_minutes=60 + (i * 30)
        ))
    return schedules


def generate_test_sessions(count=10):
    """Generate test recording sessions."""
    sessions = []
    statuses = ['completed', 'failed', 'recording', 'processing']
    
    for i in range(count):
        sessions.append(MockRecordingSession(
            id=i + 1,
            schedule_id=(i % 3) + 1,
            status=statuses[i % len(statuses)],
            file_size_bytes=1024000 + (i * 100000)
        ))
    return sessions