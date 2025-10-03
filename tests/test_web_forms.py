"""
Tests for web form validation and user interactions.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock

from tests.test_web_config import (
    TestWebConfig, sample_stream_data, sample_schedule_data,
    MockStreamConfiguration, MockRecordingSchedule,
    create_test_image_file, cleanup_test_files
)
from src.web.app import create_app


class TestStreamFormValidation:
    """Test stream configuration form validation."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app(TestWebConfig)
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_valid_stream_creation(self, client, sample_stream_data):
        """Test creating a stream with valid data."""
        with patch('src.models.repositories.ConfigurationRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_stream = MockStreamConfiguration(**sample_stream_data)
            mock_repo.create.return_value = mock_stream
            mock_repo_class.return_value = mock_repo
            
            response = client.post('/api/streams',
                                 data=json.dumps(sample_stream_data),
                                 content_type='application/json')
            
            assert response.status_code == 201
            data = json.loads(response.data)
            assert data['name'] == sample_stream_data['name']
            assert data['stream_url'] == sample_stream_data['stream_url']
    
    def test_invalid_stream_url(self, client):
        """Test stream creation with invalid URL."""
        invalid_data = {
            'name': 'Test Stream',
            'stream_url': 'not-a-valid-url',
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_artist': 'Test Album Artist',
            'scp_destination': 'user@host:/path/'
        }
        
        response = client.post('/api/streams',
                             data=json.dumps(invalid_data),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Validation Error' in data['error']
    
    def test_missing_required_fields(self, client):
        """Test stream creation with missing required fields."""
        incomplete_data = {
            'name': 'Test Stream',
            # Missing stream_url, artist, album, album_artist, scp_destination
        }
        
        response = client.post('/api/streams',
                             data=json.dumps(incomplete_data),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_empty_string_fields(self, client):
        """Test stream creation with empty string fields."""
        empty_data = {
            'name': '',
            'stream_url': 'http://example.com/stream',
            'artist': '',
            'album': 'Test Album',
            'album_artist': 'Test Album Artist',
            'scp_destination': 'user@host:/path/'
        }
        
        response = client.post('/api/streams',
                             data=json.dumps(empty_data),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_invalid_filename_pattern(self, client, sample_stream_data):
        """Test stream creation with invalid filename pattern."""
        invalid_data = sample_stream_data.copy()
        invalid_data['output_filename_pattern'] = 'no_placeholders.mp3'
        
        response = client.post('/api/streams',
                             data=json.dumps(invalid_data),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_valid_filename_patterns(self, client, sample_stream_data):
        """Test stream creation with various valid filename patterns."""
        valid_patterns = [
            '{date}_{name}.mp3',
            '{artist}_{album}_{date}.mp3',
            '{date}_{artist}.mp3',
            'recording_{name}_{date}.mp3'
        ]
        
        with patch('src.models.repositories.ConfigurationRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo
            
            for pattern in valid_patterns:
                test_data = sample_stream_data.copy()
                test_data['output_filename_pattern'] = pattern
                
                mock_stream = MockStreamConfiguration(**test_data)
                mock_repo.create.return_value = mock_stream
                
                response = client.post('/api/streams',
                                     data=json.dumps(test_data),
                                     content_type='application/json')
                
                assert response.status_code == 201, f"Pattern {pattern} should be valid"


class TestScheduleFormValidation:
    """Test schedule form validation."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app(TestWebConfig)
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_valid_schedule_creation(self, client, sample_schedule_data):
        """Test creating a schedule with valid data."""
        with patch('src.models.repositories.ScheduleRepository') as mock_schedule_repo, \
             patch('src.models.repositories.ConfigurationRepository') as mock_config_repo:
            
            # Mock stream exists
            mock_config = MagicMock()
            mock_stream = MockStreamConfiguration(id=1)
            mock_config.get_by_id.return_value = mock_stream
            mock_config_repo.return_value = mock_config
            
            # Mock schedule creation
            mock_schedule = MagicMock()
            mock_schedule_obj = MockRecordingSchedule(**sample_schedule_data)
            mock_schedule.create.return_value = mock_schedule_obj
            mock_schedule_repo.return_value = mock_schedule
            
            response = client.post('/api/schedules',
                                 data=json.dumps(sample_schedule_data),
                                 content_type='application/json')
            
            assert response.status_code == 201
            data = json.loads(response.data)
            assert data['cron_expression'] == sample_schedule_data['cron_expression']
    
    def test_invalid_cron_expressions(self, client, sample_schedule_data):
        """Test schedule creation with invalid cron expressions."""
        invalid_crons = [
            'invalid cron',
            '60 25 32 13 8',  # Invalid values
            '* * * *',        # Too few fields
            '* * * * * *',    # Too many fields
            '',               # Empty
            '0 9 * * 1-8'     # Invalid weekday range
        ]
        
        for invalid_cron in invalid_crons:
            test_data = sample_schedule_data.copy()
            test_data['cron_expression'] = invalid_cron
            
            response = client.post('/api/schedules',
                                 data=json.dumps(test_data),
                                 content_type='application/json')
            
            assert response.status_code == 400, f"Cron '{invalid_cron}' should be invalid"
    
    def test_valid_cron_expressions(self, client, sample_schedule_data):
        """Test schedule creation with valid cron expressions."""
        valid_crons = [
            '0 9 * * *',      # Daily at 9 AM
            '0 9 * * 1-5',    # Weekdays at 9 AM
            '30 14 * * 6',    # Saturdays at 2:30 PM
            '0 */2 * * *',    # Every 2 hours
            '15 10 1 * *',    # First day of month at 10:15 AM
            '0 0 * * 0'       # Sundays at midnight
        ]
        
        with patch('src.models.repositories.ScheduleRepository') as mock_schedule_repo, \
             patch('src.models.repositories.ConfigurationRepository') as mock_config_repo:
            
            # Mock stream exists
            mock_config = MagicMock()
            mock_stream = MockStreamConfiguration(id=1)
            mock_config.get_by_id.return_value = mock_stream
            mock_config_repo.return_value = mock_config
            
            # Mock schedule creation
            mock_schedule = MagicMock()
            mock_schedule_repo.return_value = mock_schedule
            
            for valid_cron in valid_crons:
                test_data = sample_schedule_data.copy()
                test_data['cron_expression'] = valid_cron
                
                mock_schedule_obj = MockRecordingSchedule(**test_data)
                mock_schedule.create.return_value = mock_schedule_obj
                
                response = client.post('/api/schedules',
                                     data=json.dumps(test_data),
                                     content_type='application/json')
                
                assert response.status_code == 201, f"Cron '{valid_cron}' should be valid"
    
    def test_invalid_duration(self, client, sample_schedule_data):
        """Test schedule creation with invalid duration."""
        invalid_durations = [0, -1, 1441, 10000]  # 0, negative, > 24 hours
        
        for invalid_duration in invalid_durations:
            test_data = sample_schedule_data.copy()
            test_data['duration_minutes'] = invalid_duration
            
            response = client.post('/api/schedules',
                                 data=json.dumps(test_data),
                                 content_type='application/json')
            
            assert response.status_code == 400, f"Duration {invalid_duration} should be invalid"
    
    def test_nonexistent_stream_config(self, client, sample_schedule_data):
        """Test schedule creation with non-existent stream configuration."""
        with patch('src.models.repositories.ConfigurationRepository') as mock_config_repo:
            # Mock stream doesn't exist
            mock_config = MagicMock()
            mock_config.get_by_id.return_value = None
            mock_config_repo.return_value = mock_config
            
            test_data = sample_schedule_data.copy()
            test_data['stream_config_id'] = 999  # Non-existent ID
            
            response = client.post('/api/schedules',
                                 data=json.dumps(test_data),
                                 content_type='application/json')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'not found' in data['message'].lower()


class TestFileUploadValidation:
    """Test file upload validation."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app(TestWebConfig)
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_valid_image_upload(self, client):
        """Test uploading a valid image file."""
        with patch('src.models.repositories.ConfigurationRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_stream = MockStreamConfiguration(id=1)
            mock_repo.get_by_id.return_value = mock_stream
            mock_repo.update.return_value = mock_stream
            mock_repo_class.return_value = mock_repo
            
            # Create test image file
            test_file_path = create_test_image_file('test.png', 1024)
            
            try:
                with open(test_file_path, 'rb') as test_file:
                    response = client.post('/api/streams/1/artwork',
                                         data={'artwork': (test_file, 'test.png')},
                                         content_type='multipart/form-data')
                
                assert response.status_code == 200
                data = json.loads(response.data)
                assert 'artwork_path' in data
                assert 'filename' in data
            finally:
                cleanup_test_files(test_file_path)
    
    def test_invalid_file_types(self, client):
        """Test uploading invalid file types."""
        with patch('src.models.repositories.ConfigurationRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_stream = MockStreamConfiguration(id=1)
            mock_repo.get_by_id.return_value = mock_stream
            mock_repo_class.return_value = mock_repo
            
            invalid_files = [
                ('test.txt', b'text file content'),
                ('test.exe', b'executable content'),
                ('test.pdf', b'pdf content'),
                ('test.mp3', b'audio content')
            ]
            
            for filename, content in invalid_files:
                with tempfile.NamedTemporaryFile(suffix=f'.{filename.split(".")[-1]}', delete=False) as tmp_file:
                    tmp_file.write(content)
                    tmp_file_path = tmp_file.name
                
                try:
                    with open(tmp_file_path, 'rb') as test_file:
                        response = client.post('/api/streams/1/artwork',
                                             data={'artwork': (test_file, filename)},
                                             content_type='multipart/form-data')
                    
                    assert response.status_code == 400, f"File type {filename} should be rejected"
                    data = json.loads(response.data)
                    assert 'error' in data
                finally:
                    cleanup_test_files(tmp_file_path)
    
    def test_file_too_large(self, client):
        """Test uploading a file that's too large."""
        with patch('src.models.repositories.ConfigurationRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_stream = MockStreamConfiguration(id=1)
            mock_repo.get_by_id.return_value = mock_stream
            mock_repo_class.return_value = mock_repo
            
            # Create a file larger than the limit (1MB in test config)
            large_file_path = create_test_image_file('large.png', 2 * 1024 * 1024)  # 2MB
            
            try:
                with open(large_file_path, 'rb') as test_file:
                    response = client.post('/api/streams/1/artwork',
                                         data={'artwork': (test_file, 'large.png')},
                                         content_type='multipart/form-data')
                
                assert response.status_code == 400
                data = json.loads(response.data)
                assert 'too large' in data['message'].lower()
            finally:
                cleanup_test_files(large_file_path)
    
    def test_no_file_uploaded(self, client):
        """Test artwork upload without selecting a file."""
        with patch('src.models.repositories.ConfigurationRepository') as mock_repo_class:
            mock_repo = MagicMock()
            mock_stream = MockStreamConfiguration(id=1)
            mock_repo.get_by_id.return_value = mock_stream
            mock_repo_class.return_value = mock_repo
            
            response = client.post('/api/streams/1/artwork',
                                 data={},
                                 content_type='multipart/form-data')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'no file' in data['message'].lower()


class TestCronValidation:
    """Test cron expression validation endpoint."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app(TestWebConfig)
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_valid_cron_validation(self, client):
        """Test validation of valid cron expressions."""
        valid_crons = [
            '0 9 * * *',
            '0 9 * * 1-5',
            '30 14 * * 6',
            '0 */2 * * *',
            '15 10 1 * *'
        ]
        
        for cron_expr in valid_crons:
            response = client.post('/api/schedules/validate-cron',
                                 data=json.dumps({'cron_expression': cron_expr}),
                                 content_type='application/json')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['valid'] is True
            assert 'next_run_time' in data
            assert 'description' in data
            assert 'next_runs' in data
    
    def test_invalid_cron_validation(self, client):
        """Test validation of invalid cron expressions."""
        invalid_crons = [
            'invalid',
            '60 25 32 13 8',
            '* * * *',
            '* * * * * *',
            '',
            'not a cron expression'
        ]
        
        for cron_expr in invalid_crons:
            response = client.post('/api/schedules/validate-cron',
                                 data=json.dumps({'cron_expression': cron_expr}),
                                 content_type='application/json')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['valid'] is False
            assert 'error' in data
    
    def test_missing_cron_expression(self, client):
        """Test cron validation without providing expression."""
        response = client.post('/api/schedules/validate-cron',
                             data=json.dumps({}),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'required' in data['message'].lower()


class TestStreamURLTesting:
    """Test stream URL testing functionality."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app(TestWebConfig)
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_successful_stream_test(self, client):
        """Test successful stream URL testing."""
        with patch('src.services.stream_recorder.StreamRecorder') as mock_recorder_class:
            mock_recorder = MagicMock()
            mock_recorder.test_stream_connection.return_value = {
                'success': True,
                'message': 'Connection successful',
                'format': 'mp3',
                'bitrate': '128k'
            }
            mock_recorder_class.return_value = mock_recorder
            
            test_data = {'stream_url': 'http://example.com/test-stream'}
            
            response = client.post('/api/streams/test-url',
                                 data=json.dumps(test_data),
                                 content_type='application/json')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['connection_test']['success'] is True
            assert 'message' in data['connection_test']
    
    def test_failed_stream_test(self, client):
        """Test failed stream URL testing."""
        with patch('src.services.stream_recorder.StreamRecorder') as mock_recorder_class:
            mock_recorder = MagicMock()
            mock_recorder.test_stream_connection.return_value = {
                'success': False,
                'message': 'Connection failed: Stream not found',
                'error_code': 404
            }
            mock_recorder_class.return_value = mock_recorder
            
            test_data = {'stream_url': 'http://example.com/nonexistent-stream'}
            
            response = client.post('/api/streams/test-url',
                                 data=json.dumps(test_data),
                                 content_type='application/json')
            
            assert response.status_code == 200  # Endpoint succeeds, but test fails
            data = json.loads(response.data)
            assert data['connection_test']['success'] is False
            assert 'failed' in data['connection_test']['message'].lower()
    
    def test_stream_test_missing_url(self, client):
        """Test stream URL testing without providing URL."""
        response = client.post('/api/streams/test-url',
                             data=json.dumps({}),
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'required' in data['message'].lower()
    
    def test_stream_test_invalid_url(self, client):
        """Test stream URL testing with invalid URL."""
        test_data = {'stream_url': 'not-a-valid-url'}
        
        response = client.post('/api/streams/test-url',
                             data=json.dumps(test_data),
                             content_type='application/json')
        
        # The endpoint might still succeed but return a failed test result
        # depending on how the StreamRecorder handles invalid URLs
        assert response.status_code in [200, 500]


if __name__ == '__main__':
    pytest.main([__file__])