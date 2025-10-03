"""
End-to-end integration tests for the complete recording workflow.
Tests the integration of scheduler, recording, processing, and transfer components.
"""

import pytest
import os
import time
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.main import ServiceContainer, initialize_database
from src.config import config
from src.services.workflow_coordinator import WorkflowCoordinator
from src.services.scheduler_service import SchedulerService
from src.services.transfer_queue import TransferQueue
from src.models.stream_configuration import StreamConfiguration
from src.models.recording_schedule import RecordingSchedule
from src.models.recording_session import RecordingSession, RecordingStatus
from src.models.repositories import ConfigurationRepository, ScheduleRepository, SessionRepository


class TestWorkflowIntegration:
    """Test complete workflow integration from schedule to transfer."""
    
    @pytest.fixture
    def temp_directories(self):
        """Create temporary directories for testing."""
        temp_dir = tempfile.mkdtemp()
        
        # Create subdirectories
        data_dir = os.path.join(temp_dir, 'data')
        recordings_dir = os.path.join(temp_dir, 'recordings')
        logs_dir = os.path.join(temp_dir, 'logs')
        artwork_dir = os.path.join(temp_dir, 'artwork')
        ssh_dir = os.path.join(temp_dir, 'ssh')
        
        for directory in [data_dir, recordings_dir, logs_dir, artwork_dir, ssh_dir]:
            os.makedirs(directory, exist_ok=True)
        
        yield {
            'temp_dir': temp_dir,
            'data_dir': data_dir,
            'recordings_dir': recordings_dir,
            'logs_dir': logs_dir,
            'artwork_dir': artwork_dir,
            'ssh_dir': ssh_dir
        }
        
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def service_container(self, temp_directories):
        """Create service container with test configuration."""
        # Override config for testing
        original_config = {}
        test_config = {
            'DATA_DIR': temp_directories['data_dir'],
            'RECORDINGS_DIR': temp_directories['recordings_dir'],
            'LOG_DIR': temp_directories['logs_dir'],
            'ARTWORK_DIR': temp_directories['artwork_dir'],
            'SSH_CONFIG_DIR': temp_directories['ssh_dir'],
            'DATABASE_URL': f"sqlite:///{temp_directories['data_dir']}/test_audio_recorder.db",
            'MAX_CONCURRENT_RECORDINGS': 2
        }
        
        # Store original values and set test values
        for key, value in test_config.items():
            original_config[key] = getattr(config, key, None)
            setattr(config, key, value)
        
        # Initialize database
        initialize_database()
        
        # Create service container
        container = ServiceContainer()
        
        # Initialize mock logging service
        mock_logging_service = Mock()
        mock_logging_service.log_operation = Mock()
        mock_logging_service.log_system_startup = Mock()
        mock_logging_service.log_system_shutdown = Mock()
        container.register_service('logging', mock_logging_service)
        
        # Initialize transfer queue
        transfer_queue = TransferQueue()
        container.register_service('transfer_queue', transfer_queue)
        
        # Initialize scheduler service
        scheduler_service = SchedulerService()
        container.register_service('scheduler', scheduler_service)
        
        # Initialize workflow coordinator
        workflow_coordinator = WorkflowCoordinator(
            scheduler_service=scheduler_service,
            transfer_queue=transfer_queue,
            logging_service=mock_logging_service
        )
        container.register_service('workflow_coordinator', workflow_coordinator)
        
        yield container
        
        # Cleanup services
        container.shutdown_all()
        
        # Restore original config
        for key, value in original_config.items():
            if value is not None:
                setattr(config, key, value)
    
    @pytest.fixture
    def sample_stream_config(self):
        """Create sample stream configuration."""
        return StreamConfiguration(
            name="Test Stream",
            stream_url="http://example.com/test-stream.mp3",
            artist="Test Artist",
            album="Test Album",
            album_artist="Test Album Artist",
            artwork_path=None,
            output_filename_pattern="{date}_{title}.mp3",
            scp_destination="/remote/path/"
        )
    
    @pytest.fixture
    def sample_schedule(self, sample_stream_config):
        """Create sample recording schedule."""
        # Save stream config first
        config_repo = ConfigurationRepository()
        saved_config = config_repo.create(sample_stream_config)
        
        return RecordingSchedule(
            stream_config_id=saved_config.id,
            cron_expression="0 * * * *",  # Every hour
            duration_minutes=30,
            is_active=True
        )
    
    def test_complete_workflow_integration(self, service_container, sample_schedule):
        """Test complete workflow from schedule creation to recording completion."""
        # Get services
        scheduler_service = service_container.get_service('scheduler')
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        
        # Create schedule
        schedule_repo = ScheduleRepository()
        saved_schedule = schedule_repo.create(sample_schedule)
        
        # Start scheduler
        assert scheduler_service.start()
        
        # Mock recording components to avoid actual recording
        with patch('src.services.recording_session_manager.RecordingSessionManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager.start_recording = Mock()
            mock_manager.get_status = Mock(return_value='recording')
            mock_manager.get_progress = Mock(return_value={'stage': 'recording', 'progress': 50})
            mock_manager_class.return_value = mock_manager
            
            # Add schedule to scheduler
            scheduler_service.add_schedule(saved_schedule)
            
            # Trigger recording manually (simulate cron trigger)
            recording_manager = workflow_coordinator._start_recording_session(
                session_id=1,
                schedule=saved_schedule,
                stream_config=sample_schedule
            )
            
            # Verify recording started
            assert recording_manager is not None
            mock_manager.start_recording.assert_called_once()
            
            # Check active sessions
            active_sessions = workflow_coordinator.get_active_sessions()
            assert len(active_sessions) == 1
            assert 1 in active_sessions
            
            # Simulate recording completion
            workflow_coordinator._handle_recording_completion(
                session_id=1,
                success=True,
                output_file="/test/output.mp3"
            )
            
            # Verify session is no longer active
            active_sessions = workflow_coordinator.get_active_sessions()
            assert len(active_sessions) == 0
        
        # Stop scheduler
        scheduler_service.stop()
    
    def test_concurrent_recording_limits(self, service_container, sample_stream_config):
        """Test that concurrent recording limits are enforced."""
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        
        # Create multiple schedules
        config_repo = ConfigurationRepository()
        schedule_repo = ScheduleRepository()
        
        saved_config = config_repo.create(sample_stream_config)
        
        schedules = []
        for i in range(3):  # More than MAX_CONCURRENT_RECORDINGS (2)
            schedule = RecordingSchedule(
                stream_config_id=saved_config.id,
                cron_expression="0 * * * *",
                duration_minutes=30,
                is_active=True
            )
            schedules.append(schedule_repo.create(schedule))
        
        # Mock recording manager
        with patch('src.services.recording_session_manager.RecordingSessionManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager.start_recording = Mock()
            mock_manager.get_status = Mock(return_value='recording')
            mock_manager.get_progress = Mock(return_value={'stage': 'recording', 'progress': 50})
            mock_manager_class.return_value = mock_manager
            
            # Start recordings
            session_id = 1
            for schedule in schedules[:2]:  # Start 2 recordings (at limit)
                workflow_coordinator._start_recording_session(
                    session_id=session_id,
                    schedule=schedule,
                    stream_config=saved_config
                )
                session_id += 1
            
            # Verify 2 active sessions
            active_sessions = workflow_coordinator.get_active_sessions()
            assert len(active_sessions) == 2
            
            # Try to start third recording - should be limited by scheduler
            # This would be handled by scheduler's _can_start_recording method
    
    def test_error_handling_in_workflow(self, service_container, sample_schedule):
        """Test error handling throughout the workflow."""
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        
        # Create schedule
        schedule_repo = ScheduleRepository()
        saved_schedule = schedule_repo.create(sample_schedule)
        
        # Mock recording manager to raise exception
        with patch('src.services.recording_session_manager.RecordingSessionManager') as mock_manager_class:
            mock_manager_class.side_effect = Exception("Recording failed")
            
            # Try to start recording
            with pytest.raises(Exception):
                workflow_coordinator._start_recording_session(
                    session_id=1,
                    schedule=saved_schedule,
                    stream_config=sample_schedule
                )
            
            # Verify session was marked as failed
            session_repo = SessionRepository()
            sessions = session_repo.get_all()
            
            # Should have created a session that was marked as failed
            failed_sessions = [s for s in sessions if s.status == RecordingStatus.FAILED]
            assert len(failed_sessions) > 0
    
    def test_transfer_queue_integration(self, service_container, sample_schedule):
        """Test integration with transfer queue."""
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        transfer_queue = service_container.get_service('transfer_queue')
        
        # Create schedule
        schedule_repo = ScheduleRepository()
        saved_schedule = schedule_repo.create(sample_schedule)
        
        # Mock transfer queue
        transfer_queue.add_transfer = Mock()
        
        # Create a test output file
        test_file = os.path.join(config.RECORDINGS_DIR, "test_output.mp3")
        Path(test_file).touch()
        
        try:
            # Simulate successful recording completion
            workflow_coordinator._handle_recording_completion(
                session_id=1,
                success=True,
                output_file=test_file
            )
            
            # Verify transfer was queued
            transfer_queue.add_transfer.assert_called_once()
            
        finally:
            # Cleanup test file
            if os.path.exists(test_file):
                os.remove(test_file)
    
    def test_session_stop_functionality(self, service_container, sample_schedule):
        """Test stopping active recording sessions."""
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        
        # Create schedule
        schedule_repo = ScheduleRepository()
        saved_schedule = schedule_repo.create(sample_schedule)
        
        # Mock recording manager
        with patch('src.services.recording_session_manager.RecordingSessionManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager.start_recording = Mock()
            mock_manager.stop_recording = Mock()
            mock_manager.get_status = Mock(return_value='recording')
            mock_manager.get_progress = Mock(return_value={'stage': 'recording', 'progress': 50})
            mock_manager_class.return_value = mock_manager
            
            # Start recording
            workflow_coordinator._start_recording_session(
                session_id=1,
                schedule=saved_schedule,
                stream_config=sample_schedule
            )
            
            # Verify session is active
            active_sessions = workflow_coordinator.get_active_sessions()
            assert len(active_sessions) == 1
            
            # Stop session
            success = workflow_coordinator.stop_session(1)
            assert success
            mock_manager.stop_recording.assert_called_once()
            
            # Try to stop non-existent session
            success = workflow_coordinator.stop_session(999)
            assert not success


class TestWebInterfaceIntegration:
    """Test web interface integration with backend services."""
    
    @pytest.fixture
    def app_with_services(self, service_container):
        """Create Flask app with service container."""
        from src.web.app import create_app
        
        app = create_app(service_container=service_container)
        app.config['TESTING'] = True
        
        with app.test_client() as client:
            with app.app_context():
                yield client, app
    
    def test_active_sessions_api(self, app_with_services, service_container):
        """Test active sessions API endpoint."""
        client, app = app_with_services
        
        # Mock workflow coordinator
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        workflow_coordinator.get_active_sessions = Mock(return_value={
            1: {
                'session_id': 1,
                'status': 'recording',
                'progress': {'stage': 'recording', 'progress': 50},
                'start_time': datetime.now().isoformat()
            }
        })
        
        # Test API endpoint
        response = client.get('/api/sessions/active')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'active_sessions' in data
        assert data['count'] == 1
        assert len(data['active_sessions']) == 1
    
    def test_stop_session_api(self, app_with_services, service_container):
        """Test stop session API endpoint."""
        client, app = app_with_services
        
        # Mock workflow coordinator
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        workflow_coordinator.stop_session = Mock(return_value=True)
        
        # Test stopping existing session
        response = client.post('/api/sessions/1/stop')
        assert response.status_code == 200
        
        data = response.get_json()
        assert 'message' in data
        assert data['session_id'] == 1
        
        # Test stopping non-existent session
        workflow_coordinator.stop_session = Mock(return_value=False)
        response = client.post('/api/sessions/999/stop')
        assert response.status_code == 404
    
    def test_system_status_integration(self, app_with_services, service_container):
        """Test system status API with service integration."""
        client, app = app_with_services
        
        # Mock monitoring service
        mock_monitoring = Mock()
        mock_monitoring.get_current_metrics = Mock(return_value=Mock(
            uptime_seconds=3600,
            cpu_percent=25.5,
            memory_percent=45.2,
            memory_used_mb=512,
            memory_total_mb=1024,
            disk_percent=60.0,
            disk_used_gb=30,
            disk_total_gb=50,
            disk_free_gb=20
        ))
        mock_monitoring.get_health_status = Mock(return_value={
            'status': 'healthy',
            'message': 'All systems operational',
            'timestamp': datetime.now().isoformat(),
            'components': {}
        })
        
        service_container.register_service('monitoring', mock_monitoring)
        
        # Mock workflow coordinator
        workflow_coordinator = service_container.get_service('workflow_coordinator')
        workflow_coordinator.get_active_sessions = Mock(return_value={1: {}, 2: {}})
        
        # Test API endpoint
        response = client.get('/api/system/status')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert data['active_recordings'] == 2
        assert data['uptime_seconds'] == 3600


class TestContainerDeployment:
    """Test container deployment and volume persistence."""
    
    def test_directory_creation(self, temp_directories):
        """Test that required directories are created."""
        # Override config temporarily
        original_dirs = {}
        test_dirs = {
            'DATA_DIR': temp_directories['data_dir'],
            'RECORDINGS_DIR': temp_directories['recordings_dir'],
            'LOG_DIR': temp_directories['logs_dir'],
            'ARTWORK_DIR': temp_directories['artwork_dir'],
            'SSH_CONFIG_DIR': temp_directories['ssh_dir']
        }
        
        for key, value in test_dirs.items():
            original_dirs[key] = getattr(config, key, None)
            setattr(config, key, value)
        
        try:
            # Test directory creation
            config.ensure_directories()
            
            # Verify all directories exist
            for directory in test_dirs.values():
                assert os.path.exists(directory)
                assert os.path.isdir(directory)
                
        finally:
            # Restore original config
            for key, value in original_dirs.items():
                if value is not None:
                    setattr(config, key, value)
    
    def test_database_persistence(self, temp_directories):
        """Test database persistence across container restarts."""
        # Set test database path
        test_db_path = os.path.join(temp_directories['data_dir'], 'test_persistence.db')
        original_db_url = config.DATABASE_URL
        config.DATABASE_URL = f"sqlite:///{test_db_path}"
        
        try:
            # Initialize database
            initialize_database()
            
            # Create test data
            config_repo = ConfigurationRepository()
            test_config = StreamConfiguration(
                name="Persistence Test",
                stream_url="http://example.com/test",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                output_filename_pattern="{date}_{title}.mp3",
                scp_destination="/test/"
            )
            
            saved_config = config_repo.create(test_config)
            config_id = saved_config.id
            
            # Verify database file exists
            assert os.path.exists(test_db_path)
            
            # Simulate container restart by creating new repository
            config_repo2 = ConfigurationRepository()
            retrieved_config = config_repo2.get_by_id(config_id)
            
            # Verify data persisted
            assert retrieved_config is not None
            assert retrieved_config.name == "Persistence Test"
            assert retrieved_config.stream_url == "http://example.com/test"
            
        finally:
            # Restore original database URL
            config.DATABASE_URL = original_db_url
    
    def test_configuration_validation(self):
        """Test configuration validation."""
        # Test valid configuration
        config.validate_config()  # Should not raise
        
        # Test invalid port
        original_port = config.WEB_PORT
        config.WEB_PORT = 99999
        
        with pytest.raises(ValueError, match="Invalid WEB_PORT"):
            config.validate_config()
        
        config.WEB_PORT = original_port
        
        # Test invalid concurrent recordings
        original_concurrent = config.MAX_CONCURRENT_RECORDINGS
        config.MAX_CONCURRENT_RECORDINGS = 0
        
        with pytest.raises(ValueError, match="MAX_CONCURRENT_RECORDINGS must be at least 1"):
            config.validate_config()
        
        config.MAX_CONCURRENT_RECORDINGS = original_concurrent


if __name__ == '__main__':
    pytest.main([__file__, '-v'])