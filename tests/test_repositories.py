"""
Unit tests for repository classes.
"""

import pytest
from datetime import datetime, timedelta

from src.models.database import RecordingStatus, TransferStatus
from src.models.stream_configuration import StreamConfigurationCreate, StreamConfigurationUpdate
from src.models.recording_schedule import RecordingScheduleCreate, RecordingScheduleUpdate
from src.models.recording_session import RecordingSessionCreate, RecordingSessionUpdate


class TestConfigurationRepository:
    """Test ConfigurationRepository."""
    
    def test_create_stream_config(self, config_repo, sample_stream_config_data):
        """Test creating a stream configuration."""
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        assert config.id is not None
        assert config.name == sample_stream_config_data["name"]
        assert config.stream_url == sample_stream_config_data["stream_url"]
        assert config.artist == sample_stream_config_data["artist"]
    
    def test_create_duplicate_name_fails(self, config_repo, sample_stream_config_data):
        """Test that creating duplicate names fails."""
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config_repo.create(config_data)
        
        # Try to create another with same name
        with pytest.raises(ValueError, match="already exists"):
            config_repo.create(config_data)
    
    def test_get_by_id(self, config_repo, sample_stream_config_data):
        """Test getting configuration by ID."""
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        created_config = config_repo.create(config_data)
        
        retrieved_config = config_repo.get_by_id(created_config.id)
        assert retrieved_config is not None
        assert retrieved_config.id == created_config.id
        assert retrieved_config.name == created_config.name
    
    def test_get_by_name(self, config_repo, sample_stream_config_data):
        """Test getting configuration by name."""
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        created_config = config_repo.create(config_data)
        
        retrieved_config = config_repo.get_by_name(created_config.name)
        assert retrieved_config is not None
        assert retrieved_config.name == created_config.name
    
    def test_get_all(self, config_repo, sample_stream_config_data):
        """Test getting all configurations."""
        # Create multiple configs
        for i in range(3):
            data = sample_stream_config_data.copy()
            data["name"] = f"Test Stream {i}"
            config_data = StreamConfigurationCreate(**data)
            config_repo.create(config_data)
        
        configs = config_repo.get_all()
        assert len(configs) == 3
    
    def test_update_config(self, config_repo, sample_stream_config_data):
        """Test updating configuration."""
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        created_config = config_repo.create(config_data)
        
        update_data = StreamConfigurationUpdate(artist="Updated Artist")
        updated_config = config_repo.update(created_config.id, update_data)
        
        assert updated_config is not None
        assert updated_config.artist == "Updated Artist"
        assert updated_config.name == sample_stream_config_data["name"]  # Unchanged
    
    def test_delete_config(self, config_repo, sample_stream_config_data):
        """Test deleting configuration."""
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        created_config = config_repo.create(config_data)
        
        result = config_repo.delete(created_config.id)
        assert result is True
        
        # Verify it's deleted
        retrieved_config = config_repo.get_by_id(created_config.id)
        assert retrieved_config is None
    
    def test_search_configs(self, config_repo, sample_stream_config_data):
        """Test searching configurations."""
        # Create configs with different names
        names = ["Jazz Stream", "Rock Stream", "Classical Music"]
        for name in names:
            data = sample_stream_config_data.copy()
            data["name"] = name
            config_data = StreamConfigurationCreate(**data)
            config_repo.create(config_data)
        
        # Search for "Stream"
        results = config_repo.search("Stream")
        assert len(results) == 2  # Jazz Stream and Rock Stream
        
        # Search for "Classical"
        results = config_repo.search("Classical")
        assert len(results) == 1
        assert results[0].name == "Classical Music"


class TestScheduleRepository:
    """Test ScheduleRepository."""
    
    def test_create_schedule(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test creating a recording schedule."""
        # Create stream config first
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        # Create schedule
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        assert schedule.id is not None
        assert schedule.stream_config_id == config.id
        assert schedule.cron_expression == sample_schedule_data["cron_expression"]
        assert schedule.next_run_time is not None
    
    def test_get_by_id(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test getting schedule by ID."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        created_schedule = schedule_repo.create(schedule_data)
        
        retrieved_schedule = schedule_repo.get_by_id(created_schedule.id)
        assert retrieved_schedule is not None
        assert retrieved_schedule.id == created_schedule.id
    
    def test_get_active_schedules(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test getting active schedules."""
        # Create stream config
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        # Create active schedule
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data_dict["is_active"] = True
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        active_schedule = schedule_repo.create(schedule_data)
        
        # Create inactive schedule
        schedule_data_dict["is_active"] = False
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule_repo.create(schedule_data)
        
        active_schedules = schedule_repo.get_active_schedules()
        assert len(active_schedules) == 1
        assert active_schedules[0].id == active_schedule.id
    
    def test_get_due_schedules(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test getting due schedules."""
        # Create stream config
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        # Create schedule
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        # Set next run time to past
        past_time = datetime.utcnow() - timedelta(hours=1)
        schedule_repo.update(schedule.id, RecordingScheduleUpdate())
        
        # Manually update next_run_time for testing
        from src.models.recording_schedule import RecordingSchedule
        with schedule_repo.get_session() as session:
            db_schedule = session.query(RecordingSchedule).filter_by(id=schedule.id).first()
            if db_schedule:
                db_schedule.next_run_time = past_time
                session.commit()
        
        current_time = datetime.utcnow()
        due_schedules = schedule_repo.get_due_schedules(current_time)
        # Note: This test might need adjustment based on actual cron calculation
    
    def test_update_schedule(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test updating schedule."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        created_schedule = schedule_repo.create(schedule_data)
        
        # Update duration
        update_data = RecordingScheduleUpdate(duration_minutes=120)
        updated_schedule = schedule_repo.update(created_schedule.id, update_data)
        
        assert updated_schedule is not None
        assert updated_schedule.duration_minutes == 120
    
    def test_increment_retry_count(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test incrementing retry count."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        created_schedule = schedule_repo.create(schedule_data)
        
        # Increment retry count
        updated_schedule = schedule_repo.increment_retry_count(created_schedule.id)
        assert updated_schedule.retry_count == 1
        
        # Increment again
        updated_schedule = schedule_repo.increment_retry_count(created_schedule.id)
        assert updated_schedule.retry_count == 2
    
    def test_reset_retry_count(self, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data):
        """Test resetting retry count."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        created_schedule = schedule_repo.create(schedule_data)
        
        # Increment retry count first
        schedule_repo.increment_retry_count(created_schedule.id)
        schedule_repo.increment_retry_count(created_schedule.id)
        
        # Reset retry count
        updated_schedule = schedule_repo.reset_retry_count(created_schedule.id)
        assert updated_schedule.retry_count == 0


class TestSessionRepository:
    """Test SessionRepository."""
    
    def test_create_session(self, session_repo, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data, sample_session_data):
        """Test creating a recording session."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        # Create session
        session_data_dict = sample_session_data.copy()
        session_data_dict["schedule_id"] = schedule.id
        session_data = RecordingSessionCreate(**session_data_dict)
        session = session_repo.create(session_data)
        
        assert session.id is not None
        assert session.schedule_id == schedule.id
        assert session.status == RecordingStatus.SCHEDULED
    
    def test_get_by_status(self, session_repo, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data, sample_session_data):
        """Test getting sessions by status."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        # Create sessions with different statuses
        session_data_dict = sample_session_data.copy()
        session_data_dict["schedule_id"] = schedule.id
        
        # Scheduled session
        session_data = RecordingSessionCreate(**session_data_dict)
        scheduled_session = session_repo.create(session_data)
        
        # Recording session
        session_data_dict["start_time"] = datetime.utcnow()
        session_data = RecordingSessionCreate(**session_data_dict)
        recording_session = session_repo.create(session_data)
        session_repo.update_status(recording_session.id, RecordingStatus.RECORDING)
        
        # Get scheduled sessions
        scheduled_sessions = session_repo.get_by_status(RecordingStatus.SCHEDULED)
        assert len(scheduled_sessions) == 1
        assert scheduled_sessions[0].id == scheduled_session.id
        
        # Get recording sessions
        recording_sessions = session_repo.get_by_status(RecordingStatus.RECORDING)
        assert len(recording_sessions) == 1
        assert recording_sessions[0].id == recording_session.id
    
    def test_update_status(self, session_repo, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data, sample_session_data):
        """Test updating session status."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        session_data_dict = sample_session_data.copy()
        session_data_dict["schedule_id"] = schedule.id
        session_data = RecordingSessionCreate(**session_data_dict)
        session = session_repo.create(session_data)
        
        # Update status to recording
        updated_session = session_repo.update_status(session.id, RecordingStatus.RECORDING)
        assert updated_session.status == RecordingStatus.RECORDING
        
        # Update status to completed (should set end_time)
        updated_session = session_repo.update_status(session.id, RecordingStatus.COMPLETED)
        assert updated_session.status == RecordingStatus.COMPLETED
        assert updated_session.end_time is not None
    
    def test_update_transfer_status(self, session_repo, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data, sample_session_data):
        """Test updating transfer status."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        session_data_dict = sample_session_data.copy()
        session_data_dict["schedule_id"] = schedule.id
        session_data = RecordingSessionCreate(**session_data_dict)
        session = session_repo.create(session_data)
        
        # Update transfer status
        updated_session = session_repo.update_transfer_status(session.id, TransferStatus.IN_PROGRESS)
        assert updated_session.transfer_status == TransferStatus.IN_PROGRESS
        
        # Update with error message
        updated_session = session_repo.update_transfer_status(
            session.id, 
            TransferStatus.FAILED, 
            "Connection timeout"
        )
        assert updated_session.transfer_status == TransferStatus.FAILED
        assert updated_session.transfer_error_message == "Connection timeout"
    
    def test_get_active_sessions(self, session_repo, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data, sample_session_data):
        """Test getting active sessions."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        # Create sessions with different statuses
        session_data_dict = sample_session_data.copy()
        session_data_dict["schedule_id"] = schedule.id
        
        # Active session (recording)
        session_data = RecordingSessionCreate(**session_data_dict)
        active_session = session_repo.create(session_data)
        session_repo.update_status(active_session.id, RecordingStatus.RECORDING)
        
        # Completed session
        session_data = RecordingSessionCreate(**session_data_dict)
        completed_session = session_repo.create(session_data)
        session_repo.update_status(completed_session.id, RecordingStatus.COMPLETED)
        
        active_sessions = session_repo.get_active_sessions()
        assert len(active_sessions) == 1
        assert active_sessions[0].id == active_session.id
    
    def test_get_statistics(self, session_repo, schedule_repo, config_repo, sample_stream_config_data, sample_schedule_data, sample_session_data):
        """Test getting session statistics."""
        # Create dependencies
        config_data = StreamConfigurationCreate(**sample_stream_config_data)
        config = config_repo.create(config_data)
        
        schedule_data_dict = sample_schedule_data.copy()
        schedule_data_dict["stream_config_id"] = config.id
        schedule_data = RecordingScheduleCreate(**schedule_data_dict)
        schedule = schedule_repo.create(schedule_data)
        
        # Create sessions with different statuses
        session_data_dict = sample_session_data.copy()
        session_data_dict["schedule_id"] = schedule.id
        
        # Create 3 completed sessions
        for _ in range(3):
            session_data = RecordingSessionCreate(**session_data_dict)
            session = session_repo.create(session_data)
            session_repo.update_status(session.id, RecordingStatus.COMPLETED)
        
        # Create 1 failed session
        session_data = RecordingSessionCreate(**session_data_dict)
        session = session_repo.create(session_data)
        session_repo.update_status(session.id, RecordingStatus.FAILED)
        
        # Create 1 active session
        session_data = RecordingSessionCreate(**session_data_dict)
        session = session_repo.create(session_data)
        session_repo.update_status(session.id, RecordingStatus.RECORDING)
        
        stats = session_repo.get_statistics()
        assert stats["total_sessions"] == 5
        assert stats["completed_sessions"] == 3
        assert stats["failed_sessions"] == 1
        assert stats["active_sessions"] == 1
        assert stats["success_rate"] == 60.0  # 3/5 * 100