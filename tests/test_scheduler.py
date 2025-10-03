"""
Unit tests for scheduler components.
Tests SchedulerService and JobManager functionality.
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.services.scheduler_service import SchedulerService
from src.services.job_manager import JobManager, JobStatus
from src.models.recording_schedule import RecordingSchedule, RecordingScheduleCreate, RecordingScheduleUpdate
from src.models.recording_session import RecordingSession, RecordingStatus
from src.models.stream_configuration import StreamConfiguration, StreamConfigurationCreate
from src.config import config


class TestSchedulerService:
    """Test cases for SchedulerService."""
    
    @pytest.fixture
    def scheduler_service(self, temp_db):
        """Create SchedulerService with temporary database."""
        # Use in-memory SQLite for APScheduler job store
        service = SchedulerService(database_url="sqlite:///:memory:")
        yield service
        # Cleanup
        if service.scheduler and service.scheduler.running:
            service.stop()
    
    @pytest.fixture
    def sample_schedule(self, config_repo, sample_stream_config_data):
        """Create a sample recording schedule."""
        # Create stream configuration first
        stream_config = StreamConfiguration(**sample_stream_config_data)
        stream_config = config_repo.create(stream_config)
        
        # Create schedule
        schedule = RecordingSchedule(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60,
            is_active=True,
            max_retries=3
        )
        schedule.update_next_run_time()
        
        return schedule
    
    def test_scheduler_initialization(self, scheduler_service):
        """Test scheduler service initialization."""
        assert scheduler_service.scheduler is not None
        assert not scheduler_service.scheduler.running
        assert scheduler_service.database_url == "sqlite:///:memory:"
        assert len(scheduler_service.active_sessions) == 0
    
    def test_start_stop_scheduler(self, scheduler_service):
        """Test starting and stopping the scheduler."""
        # Test start
        assert scheduler_service.start()
        assert scheduler_service.scheduler.running
        
        # Test start when already running
        assert not scheduler_service.start()
        
        # Test stop
        assert scheduler_service.stop()
        assert not scheduler_service.scheduler.running
        
        # Test stop when not running
        assert not scheduler_service.stop()
    
    def test_validate_cron_expression(self, scheduler_service):
        """Test cron expression validation."""
        # Valid expressions
        valid_expressions = [
            "0 1 * * *",      # Daily at 1 AM
            "*/15 * * * *",   # Every 15 minutes
            "0 0 1 * *",      # First day of month
            "0 9-17 * * 1-5", # Weekdays 9-5
            "30 2 * * 0"      # Sundays at 2:30 AM
        ]
        
        for expr in valid_expressions:
            assert scheduler_service.validate_cron_expression(expr), f"Should be valid: {expr}"
        
        # Invalid expressions
        invalid_expressions = [
            "",               # Empty
            "0 1 * *",        # Too few fields
            "0 1 * * * *",    # Too many fields
            "60 1 * * *",     # Invalid minute
            "0 25 * * *",     # Invalid hour
            "0 1 32 * *",     # Invalid day
            "0 1 * 13 *",     # Invalid month
            "0 1 * * 8",      # Invalid weekday
            "invalid"         # Non-numeric
        ]
        
        for expr in invalid_expressions:
            assert not scheduler_service.validate_cron_expression(expr), f"Should be invalid: {expr}"
    
    def test_calculate_next_run_time(self, scheduler_service):
        """Test next run time calculation."""
        # Test daily at 1 AM
        base_time = datetime(2024, 1, 1, 0, 0, 0)  # Midnight
        next_time = scheduler_service.calculate_next_run_time("0 1 * * *", base_time)
        
        assert next_time is not None
        assert next_time.hour == 1
        assert next_time.minute == 0
        assert next_time.day == 1  # Same day since it's before 1 AM
        
        # Test with invalid expression
        next_time = scheduler_service.calculate_next_run_time("invalid")
        assert next_time is None
    
    def test_add_schedule(self, scheduler_service, sample_schedule):
        """Test adding a schedule."""
        scheduler_service.start()
        
        # Test adding valid schedule
        assert scheduler_service.add_schedule(sample_schedule)
        
        # Verify job was scheduled
        jobs = scheduler_service.get_scheduled_jobs()
        assert len(jobs) == 1
        assert jobs[0]['id'] == f"recording_schedule_{sample_schedule.id}"
    
    def test_update_schedule(self, scheduler_service, sample_schedule):
        """Test updating a schedule."""
        scheduler_service.start()
        
        # Add initial schedule
        scheduler_service.add_schedule(sample_schedule)
        
        # Update cron expression
        sample_schedule.cron_expression = "0 2 * * *"  # Change to 2 AM
        sample_schedule.update_next_run_time()
        
        assert scheduler_service.update_schedule(sample_schedule)
        
        # Verify job was updated
        jobs = scheduler_service.get_scheduled_jobs()
        assert len(jobs) == 1
        # Note: Detailed trigger verification would require APScheduler internals
    
    def test_remove_schedule(self, scheduler_service, sample_schedule):
        """Test removing a schedule."""
        scheduler_service.start()
        
        # Add schedule
        scheduler_service.add_schedule(sample_schedule)
        assert len(scheduler_service.get_scheduled_jobs()) == 1
        
        # Remove schedule
        assert scheduler_service.remove_schedule(sample_schedule.id)
        assert len(scheduler_service.get_scheduled_jobs()) == 0
    
    def test_concurrent_recording_limits(self, scheduler_service):
        """Test concurrent recording session limits."""
        # Mock active sessions at limit
        mock_sessions = {}
        for i in range(config.MAX_CONCURRENT_RECORDINGS):
            mock_session = Mock()
            mock_session.current_stage.value = 'recording'
            mock_sessions[i] = mock_session
        
        scheduler_service.active_sessions = mock_sessions
        
        # Should not be able to start new recording
        assert not scheduler_service._can_start_recording()
        
        # Remove one session
        del mock_sessions[0]
        scheduler_service.active_sessions = mock_sessions
        
        # Should now be able to start recording
        assert scheduler_service._can_start_recording()
    
    def test_job_execution_callback(self, scheduler_service, sample_schedule):
        """Test job execution with callback."""
        scheduler_service.start()
        
        # Mock callback
        callback_called = threading.Event()
        callback_args = {}
        
        def mock_callback(session_id, schedule, stream_config):
            callback_args['session_id'] = session_id
            callback_args['schedule'] = schedule
            callback_args['stream_config'] = stream_config
            callback_called.set()
            return Mock()  # Mock RecordingSessionManager
        
        scheduler_service.set_recording_start_callback(mock_callback)
        
        # Mock repositories to return test data
        with patch.object(scheduler_service.schedule_repo, 'get_by_id', return_value=sample_schedule), \
             patch.object(scheduler_service.config_repo, 'get_by_id', return_value=Mock()), \
             patch.object(scheduler_service.session_repo, 'create', return_value=Mock(id=123)):
            
            # Execute job directly
            scheduler_service._execute_recording_job(sample_schedule.id)
            
            # Wait for callback
            assert callback_called.wait(timeout=1.0)
            assert 'session_id' in callback_args
            assert callback_args['schedule'] == sample_schedule
    
    def test_service_status(self, scheduler_service):
        """Test getting service status."""
        status = scheduler_service.get_service_status()
        
        assert 'running' in status
        assert 'active_sessions_count' in status
        assert 'max_concurrent_recordings' in status
        assert 'scheduled_jobs_count' in status
        assert 'database_url' in status
        
        assert status['running'] == False  # Not started yet
        assert status['active_sessions_count'] == 0
        assert status['max_concurrent_recordings'] == config.MAX_CONCURRENT_RECORDINGS


class TestJobManager:
    """Test cases for JobManager."""
    
    @pytest.fixture
    def job_manager(self, temp_db):
        """Create JobManager with mocked SchedulerService."""
        mock_scheduler = Mock(spec=SchedulerService)
        mock_scheduler.validate_cron_expression.return_value = True
        mock_scheduler.add_schedule.return_value = True
        mock_scheduler.update_schedule.return_value = True
        mock_scheduler.remove_schedule.return_value = True
        mock_scheduler.get_active_sessions.return_value = {}
        
        manager = JobManager(mock_scheduler)
        
        # Use the temp_db repositories
        manager.schedule_repo = ScheduleRepository(temp_db)
        manager.session_repo = SessionRepository(temp_db)
        manager.config_repo = ConfigurationRepository(temp_db)
        
        return manager
    
    @pytest.fixture
    def stream_config(self, job_manager, sample_stream_config_data):
        """Create a stream configuration for testing."""
        stream_config = StreamConfiguration(**sample_stream_config_data)
        return job_manager.config_repo.create(stream_config)
    
    def test_create_job(self, job_manager, stream_config):
        """Test creating a new job."""
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60,
            is_active=True,
            max_retries=3
        )
        
        schedule = job_manager.create_job(job_data)
        
        assert schedule is not None
        assert schedule.id is not None
        assert schedule.stream_config_id == stream_config.id
        assert schedule.cron_expression == "0 1 * * *"
        assert schedule.duration_minutes == 60
        assert schedule.is_active == True
        assert schedule.next_run_time is not None
        
        # Verify scheduler was called
        job_manager.scheduler_service.add_schedule.assert_called_once()
    
    def test_create_job_invalid_stream_config(self, job_manager):
        """Test creating job with invalid stream config."""
        job_data = RecordingScheduleCreate(
            stream_config_id=999,  # Non-existent
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        
        schedule = job_manager.create_job(job_data)
        assert schedule is None
    
    def test_create_job_invalid_cron(self, job_manager, stream_config):
        """Test creating job with invalid cron expression."""
        job_manager.scheduler_service.validate_cron_expression.return_value = False
        
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="invalid",
            duration_minutes=60
        )
        
        schedule = job_manager.create_job(job_data)
        assert schedule is None
    
    def test_update_job(self, job_manager, stream_config):
        """Test updating an existing job."""
        # Create initial job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        schedule = job_manager.create_job(job_data)
        
        # Update job
        update_data = RecordingScheduleUpdate(
            cron_expression="0 2 * * *",
            duration_minutes=90,
            is_active=False
        )
        
        updated_schedule = job_manager.update_job(schedule.id, update_data)
        
        assert updated_schedule is not None
        assert updated_schedule.cron_expression == "0 2 * * *"
        assert updated_schedule.duration_minutes == 90
        assert updated_schedule.is_active == False
        
        # Verify scheduler was called
        job_manager.scheduler_service.update_schedule.assert_called()
    
    def test_delete_job(self, job_manager, stream_config):
        """Test deleting a job."""
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        schedule = job_manager.create_job(job_data)
        
        # Delete job
        assert job_manager.delete_job(schedule.id)
        
        # Verify job is deleted
        deleted_schedule = job_manager.schedule_repo.get_by_id(schedule.id)
        assert deleted_schedule is None
        
        # Verify scheduler was called
        job_manager.scheduler_service.remove_schedule.assert_called_with(schedule.id)
    
    def test_activate_deactivate_job(self, job_manager, stream_config):
        """Test activating and deactivating jobs."""
        # Create inactive job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60,
            is_active=False
        )
        schedule = job_manager.create_job(job_data)
        
        # Activate job
        assert job_manager.activate_job(schedule.id)
        
        updated_schedule = job_manager.schedule_repo.get_by_id(schedule.id)
        assert updated_schedule.is_active == True
        
        # Deactivate job
        assert job_manager.deactivate_job(schedule.id)
        
        updated_schedule = job_manager.schedule_repo.get_by_id(schedule.id)
        assert updated_schedule.is_active == False
    
    def test_get_job_status(self, job_manager, stream_config):
        """Test getting job status."""
        # Create active job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60,
            is_active=True
        )
        schedule = job_manager.create_job(job_data)
        
        # Test active job status
        status = job_manager.get_job_status(schedule.id)
        assert status == JobStatus.SCHEDULED
        
        # Test inactive job
        job_manager.deactivate_job(schedule.id)
        status = job_manager.get_job_status(schedule.id)
        assert status == JobStatus.INACTIVE
        
        # Test non-existent job
        status = job_manager.get_job_status(999)
        assert status is None
    
    def test_get_next_execution_time(self, job_manager, stream_config):
        """Test getting next execution time."""
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60,
            is_active=True
        )
        schedule = job_manager.create_job(job_data)
        
        # Get next execution time
        next_time = job_manager.get_next_execution_time(schedule.id)
        assert next_time is not None
        assert isinstance(next_time, datetime)
        
        # Test inactive job
        job_manager.deactivate_job(schedule.id)
        next_time = job_manager.get_next_execution_time(schedule.id)
        assert next_time is None
    
    def test_get_job_history(self, job_manager, stream_config):
        """Test getting job execution history."""
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        schedule = job_manager.create_job(job_data)
        
        # Create some sessions
        for i in range(3):
            session = RecordingSession(
                schedule_id=schedule.id,
                start_time=datetime.now() - timedelta(days=i),
                status=RecordingStatus.COMPLETED
            )
            job_manager.session_repo.create(session)
        
        # Get history
        history = job_manager.get_job_history(schedule.id, limit=2)
        assert len(history) == 2
        assert all(isinstance(session, RecordingSession) for session in history)
    
    def test_get_job_statistics(self, job_manager, stream_config):
        """Test getting job statistics."""
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        schedule = job_manager.create_job(job_data)
        
        # Create sessions with different statuses
        sessions_data = [
            (RecordingStatus.COMPLETED, None),
            (RecordingStatus.COMPLETED, None),
            (RecordingStatus.FAILED, "Test error"),
        ]
        
        for status, error in sessions_data:
            session = RecordingSession(
                schedule_id=schedule.id,
                start_time=datetime.now() - timedelta(hours=1),
                end_time=datetime.now(),
                status=status,
                error_message=error,
                file_size_bytes=1024 * 1024 if status == RecordingStatus.COMPLETED else None
            )
            job_manager.session_repo.create(session)
        
        # Get statistics
        stats = job_manager.get_job_statistics(schedule.id, days=30)
        
        assert stats['schedule_id'] == schedule.id
        assert stats['total_sessions'] == 3
        assert stats['successful_sessions'] == 2
        assert stats['failed_sessions'] == 1
        assert stats['success_rate_percent'] == 66.67
        assert stats['total_file_size_bytes'] == 2 * 1024 * 1024
    
    def test_get_all_jobs_summary(self, job_manager, stream_config):
        """Test getting summary of all jobs."""
        # Create multiple jobs
        for i in range(3):
            job_data = RecordingScheduleCreate(
                stream_config_id=stream_config.id,
                cron_expression=f"0 {i+1} * * *",
                duration_minutes=60,
                is_active=i % 2 == 0  # Alternate active/inactive
            )
            job_manager.create_job(job_data)
        
        # Get summary
        summary = job_manager.get_all_jobs_summary()
        
        assert len(summary) == 3
        for job_summary in summary:
            assert 'schedule_id' in job_summary
            assert 'stream_name' in job_summary
            assert 'cron_expression' in job_summary
            assert 'status' in job_summary
            assert 'is_active' in job_summary
    
    def test_handle_job_failure(self, job_manager, stream_config):
        """Test handling job failures."""
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60,
            max_retries=2
        )
        schedule = job_manager.create_job(job_data)
        
        # Create session
        session = RecordingSession(
            schedule_id=schedule.id,
            start_time=datetime.now(),
            status=RecordingStatus.RECORDING
        )
        session = job_manager.session_repo.create(session)
        
        # Handle failure
        assert job_manager.handle_job_failure(schedule.id, session.id, "Test error")
        
        # Verify session updated
        updated_session = job_manager.session_repo.get_by_id(session.id)
        assert updated_session.status == RecordingStatus.FAILED
        assert updated_session.error_message == "Test error"
        
        # Verify retry count incremented
        updated_schedule = job_manager.schedule_repo.get_by_id(schedule.id)
        assert updated_schedule.retry_count == 1
    
    def test_reset_retry_count(self, job_manager, stream_config):
        """Test resetting retry count."""
        # Create job with retry count
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        schedule = job_manager.create_job(job_data)
        
        # Manually set retry count
        schedule.retry_count = 5
        job_manager.schedule_repo.update(schedule)
        
        # Reset retry count
        assert job_manager.reset_job_retry_count(schedule.id)
        
        # Verify reset
        updated_schedule = job_manager.schedule_repo.get_by_id(schedule.id)
        assert updated_schedule.retry_count == 0
    
    def test_cleanup_old_sessions(self, job_manager, stream_config):
        """Test cleaning up old sessions."""
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="0 1 * * *",
            duration_minutes=60
        )
        schedule = job_manager.create_job(job_data)
        
        # Create old and new sessions
        old_session = RecordingSession(
            schedule_id=schedule.id,
            start_time=datetime.now() - timedelta(days=40),
            status=RecordingStatus.COMPLETED
        )
        new_session = RecordingSession(
            schedule_id=schedule.id,
            start_time=datetime.now() - timedelta(days=10),
            status=RecordingStatus.COMPLETED
        )
        
        job_manager.session_repo.create(old_session)
        job_manager.session_repo.create(new_session)
        
        # Cleanup sessions older than 30 days
        deleted_count = job_manager.cleanup_old_sessions(days_to_keep=30)
        
        # Should have deleted 1 session
        assert deleted_count == 1
        
        # Verify new session still exists
        remaining_sessions = job_manager.get_job_history(schedule.id, limit=10)
        assert len(remaining_sessions) == 1
        assert remaining_sessions[0].id == new_session.id


class TestSchedulerIntegration:
    """Integration tests for scheduler components."""
    
    @pytest.fixture
    def integrated_system(self, temp_db):
        """Create integrated scheduler system."""
        scheduler_service = SchedulerService(database_url="sqlite:///:memory:")
        job_manager = JobManager(scheduler_service)
        
        # Use temp_db repositories
        job_manager.schedule_repo = ScheduleRepository(temp_db)
        job_manager.session_repo = SessionRepository(temp_db)
        job_manager.config_repo = ConfigurationRepository(temp_db)
        
        # Update scheduler service repositories to use same database
        scheduler_service.schedule_repo = job_manager.schedule_repo
        scheduler_service.session_repo = job_manager.session_repo
        scheduler_service.config_repo = job_manager.config_repo
        
        yield scheduler_service, job_manager
        
        # Cleanup
        if scheduler_service.scheduler and scheduler_service.scheduler.running:
            scheduler_service.stop()
    
    def test_end_to_end_job_lifecycle(self, integrated_system, sample_stream_config_data):
        """Test complete job lifecycle from creation to execution."""
        scheduler_service, job_manager = integrated_system
        
        # Create stream configuration
        stream_config = StreamConfiguration(**sample_stream_config_data)
        stream_config = job_manager.config_repo.create(stream_config)
        
        # Start scheduler
        scheduler_service.start()
        
        # Create job
        job_data = RecordingScheduleCreate(
            stream_config_id=stream_config.id,
            cron_expression="* * * * *",  # Every minute for testing
            duration_minutes=1,
            is_active=True
        )
        
        schedule = job_manager.create_job(job_data)
        assert schedule is not None
        
        # Verify job is scheduled
        jobs = scheduler_service.get_scheduled_jobs()
        assert len(jobs) == 1
        
        # Test job status
        status = job_manager.get_job_status(schedule.id)
        assert status == JobStatus.SCHEDULED
        
        # Test deactivation
        assert job_manager.deactivate_job(schedule.id)
        jobs = scheduler_service.get_scheduled_jobs()
        assert len(jobs) == 0
        
        # Test reactivation
        assert job_manager.activate_job(schedule.id)
        jobs = scheduler_service.get_scheduled_jobs()
        assert len(jobs) == 1
        
        # Test deletion
        assert job_manager.delete_job(schedule.id)
        jobs = scheduler_service.get_scheduled_jobs()
        assert len(jobs) == 0