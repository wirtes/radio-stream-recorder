"""
Unit tests for data models.
"""

import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from src.models.database import RecordingStatus, TransferStatus
from src.models.stream_configuration import StreamConfiguration, StreamConfigurationCreate
from src.models.recording_schedule import RecordingSchedule, RecordingScheduleCreate
from src.models.recording_session import RecordingSession, RecordingSessionCreate


class TestStreamConfiguration:
    """Test StreamConfiguration model."""
    
    def test_create_valid_stream_config(self, temp_db):
        """Test creating a valid stream configuration."""
        with temp_db.get_session() as session:
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.commit()
            
            assert config.id is not None
            assert config.name == "Test Stream"
            assert config.created_at is not None
            assert config.updated_at is not None
    
    def test_stream_url_validation(self, temp_db):
        """Test stream URL validation."""
        with temp_db.get_session() as session:
            # Test invalid URL
            with pytest.raises(ValueError, match="Invalid stream URL format"):
                config = StreamConfiguration(
                    name="Test Stream",
                    stream_url="invalid-url",
                    artist="Test Artist",
                    album="Test Album",
                    album_artist="Test Album Artist",
                    scp_destination="user@host:/path"
                )
                session.add(config)
                session.flush()
    
    def test_name_validation(self, temp_db):
        """Test name validation."""
        with temp_db.get_session() as session:
            # Test empty name
            with pytest.raises(ValueError, match="Stream name cannot be empty"):
                config = StreamConfiguration(
                    name="",
                    stream_url="https://example.com/stream.mp3",
                    artist="Test Artist",
                    album="Test Album",
                    album_artist="Test Album Artist",
                    scp_destination="user@host:/path"
                )
                session.add(config)
                session.flush()
    
    def test_scp_destination_validation(self, temp_db):
        """Test SCP destination validation."""
        with temp_db.get_session() as session:
            # Test invalid SCP destination
            with pytest.raises(ValueError, match="SCP destination must be in format"):
                config = StreamConfiguration(
                    name="Test Stream",
                    stream_url="https://example.com/stream.mp3",
                    artist="Test Artist",
                    album="Test Album",
                    album_artist="Test Album Artist",
                    scp_destination="invalid-destination"
                )
                session.add(config)
                session.flush()
    
    def test_unique_name_constraint(self, temp_db):
        """Test unique name constraint."""
        with temp_db.get_session() as session:
            # Create first config
            config1 = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream1.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path1"
            )
            session.add(config1)
            session.commit()
            
            # Try to create second config with same name
            config2 = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream2.mp3",
                artist="Test Artist 2",
                album="Test Album 2",
                album_artist="Test Album Artist 2",
                scp_destination="user@host:/path2"
            )
            session.add(config2)
            
            with pytest.raises(IntegrityError):
                session.commit()


class TestRecordingSchedule:
    """Test RecordingSchedule model."""
    
    def test_create_valid_schedule(self, temp_db):
        """Test creating a valid recording schedule."""
        with temp_db.get_session() as session:
            # First create a stream config
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            schedule = RecordingSchedule(
                stream_config_id=config.id,
                cron_expression="0 1 * * *",
                duration_minutes=60
            )
            session.add(schedule)
            session.commit()
            
            assert schedule.id is not None
            assert schedule.cron_expression == "0 1 * * *"
            assert schedule.duration_minutes == 60
            assert schedule.is_active is True
            assert schedule.retry_count == 0
            assert schedule.max_retries == 3
    
    def test_cron_expression_validation(self, temp_db):
        """Test cron expression validation."""
        with temp_db.get_session() as session:
            # Create stream config first
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            # Test invalid cron expression
            with pytest.raises(ValueError, match="Cron expression must have exactly 5 fields"):
                schedule = RecordingSchedule(
                    stream_config_id=config.id,
                    cron_expression="0 1 *",  # Only 3 fields
                    duration_minutes=60
                )
                session.add(schedule)
                session.flush()
    
    def test_duration_validation(self, temp_db):
        """Test duration validation."""
        with temp_db.get_session() as session:
            # Create stream config first
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            # Test invalid duration
            with pytest.raises(ValueError, match="Duration must be a positive integer"):
                schedule = RecordingSchedule(
                    stream_config_id=config.id,
                    cron_expression="0 1 * * *",
                    duration_minutes=0
                )
                session.add(schedule)
                session.flush()
    
    def test_calculate_next_run_time(self, temp_db):
        """Test next run time calculation."""
        with temp_db.get_session() as session:
            # Create stream config first
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            schedule = RecordingSchedule(
                stream_config_id=config.id,
                cron_expression="0 1 * * *",  # Daily at 1 AM
                duration_minutes=60
            )
            
            base_time = datetime(2023, 1, 1, 0, 0, 0)  # Midnight
            next_run = schedule.calculate_next_run_time(base_time)
            
            # Should be 1 AM on the same day
            expected = datetime(2023, 1, 1, 1, 0, 0)
            assert next_run == expected


class TestRecordingSession:
    """Test RecordingSession model."""
    
    def test_create_valid_session(self, temp_db):
        """Test creating a valid recording session."""
        with temp_db.get_session() as session:
            # Create stream config and schedule first
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            schedule = RecordingSchedule(
                stream_config_id=config.id,
                cron_expression="0 1 * * *",
                duration_minutes=60
            )
            session.add(schedule)
            session.flush()
            
            recording_session = RecordingSession(
                schedule_id=schedule.id,
                start_time=datetime.utcnow()
            )
            session.add(recording_session)
            session.commit()
            
            assert recording_session.id is not None
            assert recording_session.status == RecordingStatus.SCHEDULED
            assert recording_session.transfer_status == TransferStatus.PENDING
            assert recording_session.start_time is not None
    
    def test_file_path_validation(self, temp_db):
        """Test output file path validation."""
        with temp_db.get_session() as session:
            # Create dependencies
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            schedule = RecordingSchedule(
                stream_config_id=config.id,
                cron_expression="0 1 * * *",
                duration_minutes=60
            )
            session.add(schedule)
            session.flush()
            
            # Test invalid file extension
            with pytest.raises(ValueError, match="Output file must have a valid audio extension"):
                recording_session = RecordingSession(
                    schedule_id=schedule.id,
                    start_time=datetime.utcnow(),
                    output_file_path="/path/to/file.txt"
                )
                session.add(recording_session)
                session.flush()
    
    def test_duration_calculation(self, temp_db):
        """Test duration calculation."""
        with temp_db.get_session() as session:
            # Create dependencies
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            schedule = RecordingSchedule(
                stream_config_id=config.id,
                cron_expression="0 1 * * *",
                duration_minutes=60
            )
            session.add(schedule)
            session.flush()
            
            start_time = datetime(2023, 1, 1, 1, 0, 0)
            end_time = datetime(2023, 1, 1, 2, 30, 0)
            
            recording_session = RecordingSession(
                schedule_id=schedule.id,
                start_time=start_time,
                end_time=end_time
            )
            
            duration = recording_session.get_duration_minutes()
            assert duration == 90  # 1.5 hours = 90 minutes
    
    def test_status_checks(self, temp_db):
        """Test status check methods."""
        with temp_db.get_session() as session:
            # Create dependencies
            config = StreamConfiguration(
                name="Test Stream",
                stream_url="https://example.com/stream.mp3",
                artist="Test Artist",
                album="Test Album",
                album_artist="Test Album Artist",
                scp_destination="user@host:/path"
            )
            session.add(config)
            session.flush()
            
            schedule = RecordingSchedule(
                stream_config_id=config.id,
                cron_expression="0 1 * * *",
                duration_minutes=60
            )
            session.add(schedule)
            session.flush()
            
            recording_session = RecordingSession(
                schedule_id=schedule.id,
                start_time=datetime.utcnow(),
                status=RecordingStatus.RECORDING
            )
            
            assert recording_session.is_in_progress() is True
            assert recording_session.is_completed() is False
            assert recording_session.is_failed() is False
            
            recording_session.status = RecordingStatus.COMPLETED
            assert recording_session.is_completed() is True
            assert recording_session.is_in_progress() is False