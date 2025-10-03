"""
Integration tests for the web interface.
"""

import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from flask import url_for

from src.web.app import create_app
from src.config import Config
from src.models.database import DatabaseManager


class TestConfig(Config):
    """Test configuration."""
    TESTING = True
    DATABASE_URL = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'
    WTF_CSRF_ENABLED = False  # Disable CSRF for testing


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app(TestConfig)
    
    with app.app_context():
        # Initialize test database
        db_manager = DatabaseManager(TestConfig.DATABASE_URL)
        db_manager.create_tables()
        
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()


class TestMainRoutes:
    """Test main web routes."""
    
    def test_dashboard_page(self, client):
        """Test dashboard page loads."""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Dashboard' in response.data
        assert b'Audio Stream Recorder' in response.data
    
    def test_streams_page(self, client):
        """Test streams page loads."""
        response = client.get('/streams')
        assert response.status_code == 200
        assert b'Stream Configurations' in response.data
    
    def test_new_stream_page(self, client):
        """Test new stream page loads."""
        response = client.get('/streams/new')
        assert response.status_code == 200
        assert b'Add New Stream Configuration' in response.data
    
    def test_schedules_page(self, client):
        """Test schedules page loads."""
        response = client.get('/schedules')
        assert response.status_code == 200
        assert b'Recording Schedules' in response.data
    
    def test_new_schedule_page(self, client):
        """Test new schedule page loads."""
        response = client.get('/schedules/new')
        assert response.status_code == 200
        assert b'Add New Recording Schedule' in response.data
    
    def test_sessions_page(self, client):
        """Test sessions page loads."""
        response = client.get('/sessions')
        assert response.status_code == 200
        assert b'Recording Sessions' in response.data
    
    def test_logs_page(self, client):
        """Test logs page loads."""
        response = client.get('/logs')
        assert response.status_code == 200
        assert b'System Logs' in response.data
    
    def test_settings_page(self, client):
        """Test settings page loads."""
        response = client.get('/settings')
        assert response.status_code == 200
        assert b'System Settings' in response.data
    
    def test_404_page(self, client):
        """Test 404 error page."""
        response = client.get('/nonexistent-page')
        assert response.status_code == 404


class TestAPIHealthCheck:
    """Test API health check endpoints."""
    
    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get('/api/health')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
        assert data['service'] == 'audio-stream-recorder'
        assert 'version' in data


class TestStreamConfigurationAPI:
    """Test stream configuration API endpoints."""
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_get_streams_empty(self, mock_repo_class, client):
        """Test getting streams when none exist."""
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = []
        mock_repo_class.return_value = mock_repo
        
        response = client.get('/api/streams')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data == []
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_create_stream_valid_data(self, mock_repo_class, client):
        """Test creating a stream with valid data."""
        mock_repo = MagicMock()
        mock_stream = MagicMock()
        mock_stream.id = 1
        mock_stream.name = 'Test Stream'
        mock_stream.stream_url = 'http://example.com/stream'
        mock_stream.artist = 'Test Artist'
        mock_stream.album = 'Test Album'
        mock_stream.album_artist = 'Test Album Artist'
        mock_stream.artwork_path = None
        mock_stream.output_filename_pattern = '{date}_{name}.mp3'
        mock_stream.scp_destination = 'user@host:/path/'
        mock_stream.created_at = '2023-01-01T00:00:00'
        mock_stream.updated_at = '2023-01-01T00:00:00'
        
        mock_repo.create.return_value = mock_stream
        mock_repo_class.return_value = mock_repo
        
        stream_data = {
            'name': 'Test Stream',
            'stream_url': 'http://example.com/stream',
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_artist': 'Test Album Artist',
            'output_filename_pattern': '{date}_{name}.mp3',
            'scp_destination': 'user@host:/path/'
        }
        
        response = client.post('/api/streams', 
                             data=json.dumps(stream_data),
                             content_type='application/json')
        assert response.status_code == 201
        
        data = json.loads(response.data)
        assert data['id'] == 1
        assert data['name'] == 'Test Stream'
    
    def test_create_stream_invalid_data(self, client):
        """Test creating a stream with invalid data."""
        invalid_data = {
            'name': '',  # Empty name should fail validation
            'stream_url': 'invalid-url',  # Invalid URL
            'artist': 'Test Artist'
            # Missing required fields
        }
        
        response = client.post('/api/streams',
                             data=json.dumps(invalid_data),
                             content_type='application/json')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'Validation Error'
    
    def test_create_stream_missing_json(self, client):
        """Test creating a stream without JSON data."""
        response = client.post('/api/streams')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_get_stream_by_id(self, mock_repo_class, client):
        """Test getting a specific stream by ID."""
        mock_repo = MagicMock()
        mock_stream = MagicMock()
        mock_stream.id = 1
        mock_stream.name = 'Test Stream'
        mock_repo.get_by_id.return_value = mock_stream
        mock_repo_class.return_value = mock_repo
        
        response = client.get('/api/streams/1')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['id'] == 1
        assert data['name'] == 'Test Stream'
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_get_stream_not_found(self, mock_repo_class, client):
        """Test getting a non-existent stream."""
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_class.return_value = mock_repo
        
        response = client.get('/api/streams/999')
        assert response.status_code == 404
        
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'Not Found'
    
    @patch('src.services.stream_recorder.StreamRecorder')
    def test_test_stream_url(self, mock_recorder_class, client):
        """Test stream URL testing endpoint."""
        mock_recorder = MagicMock()
        mock_recorder.test_stream_connection.return_value = {
            'success': True,
            'message': 'Connection successful'
        }
        mock_recorder_class.return_value = mock_recorder
        
        test_data = {'stream_url': 'http://example.com/stream'}
        
        response = client.post('/api/streams/test-url',
                             data=json.dumps(test_data),
                             content_type='application/json')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['stream_url'] == 'http://example.com/stream'
        assert data['connection_test']['success'] is True


class TestScheduleAPI:
    """Test schedule management API endpoints."""
    
    @patch('src.models.repositories.ScheduleRepository')
    def test_get_schedules_empty(self, mock_repo_class, client):
        """Test getting schedules when none exist."""
        mock_repo = MagicMock()
        mock_repo.get_all.return_value = []
        mock_repo_class.return_value = mock_repo
        
        response = client.get('/api/schedules')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data == []
    
    @patch('src.models.repositories.ScheduleRepository')
    @patch('src.models.repositories.ConfigurationRepository')
    def test_create_schedule_valid_data(self, mock_config_repo_class, mock_schedule_repo_class, client):
        """Test creating a schedule with valid data."""
        # Mock stream configuration exists
        mock_config_repo = MagicMock()
        mock_stream = MagicMock()
        mock_stream.id = 1
        mock_config_repo.get_by_id.return_value = mock_stream
        mock_config_repo_class.return_value = mock_config_repo
        
        # Mock schedule creation
        mock_schedule_repo = MagicMock()
        mock_schedule = MagicMock()
        mock_schedule.id = 1
        mock_schedule.stream_config_id = 1
        mock_schedule.cron_expression = '0 9 * * *'
        mock_schedule.duration_minutes = 60
        mock_schedule.is_active = True
        mock_schedule.next_run_time = None
        mock_schedule.last_run_time = None
        mock_schedule.retry_count = 0
        mock_schedule.max_retries = 3
        mock_schedule.created_at = '2023-01-01T00:00:00'
        mock_schedule.updated_at = '2023-01-01T00:00:00'
        
        mock_schedule_repo.create.return_value = mock_schedule
        mock_schedule_repo_class.return_value = mock_schedule_repo
        
        schedule_data = {
            'stream_config_id': 1,
            'cron_expression': '0 9 * * *',
            'duration_minutes': 60,
            'max_retries': 3
        }
        
        response = client.post('/api/schedules',
                             data=json.dumps(schedule_data),
                             content_type='application/json')
        assert response.status_code == 201
        
        data = json.loads(response.data)
        assert data['id'] == 1
        assert data['cron_expression'] == '0 9 * * *'
    
    def test_validate_cron_expression_valid(self, client):
        """Test cron expression validation with valid expression."""
        cron_data = {'cron_expression': '0 9 * * 1-5'}
        
        response = client.post('/api/schedules/validate-cron',
                             data=json.dumps(cron_data),
                             content_type='application/json')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['valid'] is True
        assert 'next_run_time' in data
        assert 'description' in data
    
    def test_validate_cron_expression_invalid(self, client):
        """Test cron expression validation with invalid expression."""
        cron_data = {'cron_expression': 'invalid cron'}
        
        response = client.post('/api/schedules/validate-cron',
                             data=json.dumps(cron_data),
                             content_type='application/json')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert data['valid'] is False
        assert 'error' in data


class TestSystemMonitoringAPI:
    """Test system monitoring API endpoints."""
    
    @patch('psutil.disk_usage')
    @patch('psutil.virtual_memory')
    def test_system_status(self, mock_memory, mock_disk, client):
        """Test system status endpoint."""
        # Mock system metrics
        mock_disk.return_value = MagicMock(
            total=1000000000,  # 1GB
            used=500000000,    # 500MB
            free=500000000     # 500MB
        )
        mock_memory.return_value = MagicMock(percent=50.0)
        
        response = client.get('/api/system/status')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'status' in data
        assert 'disk_usage_percent' in data
        assert 'memory_usage_percent' in data
        assert 'last_updated' in data
    
    def test_system_logs(self, client):
        """Test system logs endpoint."""
        response = client.get('/api/system/logs')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'logs' in data
        assert 'total_count' in data
        assert 'page' in data
        assert 'per_page' in data
    
    def test_system_logs_with_filters(self, client):
        """Test system logs endpoint with filters."""
        response = client.get('/api/system/logs?level=ERROR&limit=50')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'logs' in data
        assert data['per_page'] == 50


class TestFileUpload:
    """Test file upload functionality."""
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_artwork_upload_valid_file(self, mock_repo_class, client):
        """Test uploading valid artwork file."""
        mock_repo = MagicMock()
        mock_stream = MagicMock()
        mock_stream.id = 1
        mock_repo.get_by_id.return_value = mock_stream
        mock_repo.update.return_value = mock_stream
        mock_repo_class.return_value = mock_repo
        
        # Create a temporary image file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            tmp_file.write(b'fake image data')
            tmp_file_path = tmp_file.name
        
        try:
            with open(tmp_file_path, 'rb') as test_file:
                response = client.post('/api/streams/1/artwork',
                                     data={'artwork': (test_file, 'test.png')},
                                     content_type='multipart/form-data')
            
            assert response.status_code == 200
            
            data = json.loads(response.data)
            assert 'artwork_path' in data
            assert 'filename' in data
            assert data['stream_id'] == 1
        finally:
            # Clean up
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_artwork_upload_no_file(self, mock_repo_class, client):
        """Test artwork upload without file."""
        mock_repo = MagicMock()
        mock_stream = MagicMock()
        mock_repo.get_by_id.return_value = mock_stream
        mock_repo_class.return_value = mock_repo
        
        response = client.post('/api/streams/1/artwork',
                             data={},
                             content_type='multipart/form-data')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
    
    @patch('src.models.repositories.ConfigurationRepository')
    def test_artwork_upload_stream_not_found(self, mock_repo_class, client):
        """Test artwork upload for non-existent stream."""
        mock_repo = MagicMock()
        mock_repo.get_by_id.return_value = None
        mock_repo_class.return_value = mock_repo
        
        with tempfile.NamedTemporaryFile(suffix='.png') as tmp_file:
            tmp_file.write(b'fake image data')
            tmp_file.seek(0)
            
            response = client.post('/api/streams/999/artwork',
                                 data={'artwork': (tmp_file, 'test.png')},
                                 content_type='multipart/form-data')
        
        assert response.status_code == 404
        
        data = json.loads(response.data)
        assert 'error' in data


class TestErrorHandling:
    """Test error handling in web interface."""
    
    def test_api_validation_error(self, client):
        """Test API validation error handling."""
        invalid_data = {'invalid': 'data'}
        
        response = client.post('/api/streams',
                             data=json.dumps(invalid_data),
                             content_type='application/json')
        assert response.status_code == 400
        
        data = json.loads(response.data)
        assert 'error' in data
        assert 'message' in data
        assert 'status_code' in data
    
    def test_api_not_found_error(self, client):
        """Test API not found error handling."""
        response = client.get('/api/nonexistent-endpoint')
        assert response.status_code == 404
    
    def test_api_method_not_allowed(self, client):
        """Test API method not allowed error."""
        response = client.patch('/api/health')  # PATCH not allowed on health endpoint
        assert response.status_code == 405


class TestConfigurationExportImport:
    """Test configuration export/import functionality."""
    
    @patch('src.models.repositories.ConfigurationRepository')
    @patch('src.models.repositories.ScheduleRepository')
    def test_export_configuration(self, mock_schedule_repo_class, mock_config_repo_class, client):
        """Test configuration export."""
        # Mock repositories
        mock_config_repo = MagicMock()
        mock_config_repo.get_all.return_value = []
        mock_config_repo_class.return_value = mock_config_repo
        
        mock_schedule_repo = MagicMock()
        mock_schedule_repo.get_all.return_value = []
        mock_schedule_repo_class.return_value = mock_schedule_repo
        
        response = client.get('/api/streams/export')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'streams' in data
        assert 'schedules' in data
        assert 'exported_at' in data
        assert 'version' in data
    
    @patch('src.models.repositories.ConfigurationRepository')
    @patch('src.models.repositories.ScheduleRepository')
    def test_import_configuration(self, mock_schedule_repo_class, mock_config_repo_class, client):
        """Test configuration import."""
        # Mock repositories
        mock_config_repo = MagicMock()
        mock_stream = MagicMock()
        mock_stream.id = 1
        mock_config_repo.create.return_value = mock_stream
        mock_config_repo_class.return_value = mock_config_repo
        
        mock_schedule_repo = MagicMock()
        mock_schedule_repo_class.return_value = mock_schedule_repo
        
        import_data = {
            'streams': [{
                'name': 'Test Stream',
                'stream_url': 'http://example.com/stream',
                'artist': 'Test Artist',
                'album': 'Test Album',
                'album_artist': 'Test Album Artist',
                'output_filename_pattern': '{date}_{name}.mp3',
                'scp_destination': 'user@host:/path/'
            }],
            'schedules': [],
            'version': '1.0'
        }
        
        response = client.post('/api/streams/import',
                             data=json.dumps(import_data),
                             content_type='application/json')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert 'imported_streams' in data
        assert 'imported_schedules' in data
        assert 'errors' in data


if __name__ == '__main__':
    pytest.main([__file__])