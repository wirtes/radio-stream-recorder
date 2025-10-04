"""
Repository layer for database CRUD operations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_, desc, asc

from .database import DatabaseManager
from .stream_configuration import StreamConfiguration, StreamConfigurationCreate, StreamConfigurationUpdate
from .recording_schedule import RecordingSchedule, RecordingScheduleCreate, RecordingScheduleUpdate
from .recording_session import RecordingSession, RecordingSessionCreate, RecordingSessionUpdate
from .database import RecordingStatus, TransferStatus


class BaseRepository:
    """Base repository class with common database operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def get_session(self) -> Session:
        """Get a database session."""
        return self.db_manager.get_session()


class ConfigurationRepository(BaseRepository):
    """Repository for stream configuration management."""
    
    def create(self, config_data: StreamConfigurationCreate) -> StreamConfiguration:
        """Create a new stream configuration."""
        with self.get_session() as session:
            try:
                # Use Pydantic's json serialization to properly convert types
                data_dict = config_data.dict()
                # Ensure stream_url is converted to string
                data_dict['stream_url'] = str(config_data.stream_url)
                
                db_config = StreamConfiguration(**data_dict)
                session.add(db_config)
                session.commit()
                session.refresh(db_config)
                return db_config
            except IntegrityError as e:
                session.rollback()
                if "UNIQUE constraint failed" in str(e):
                    raise ValueError(f"Stream configuration with name '{config_data.name}' already exists")
                raise ValueError(f"Database error: {str(e)}")
    
    def get_by_id(self, config_id: int) -> Optional[StreamConfiguration]:
        """Get stream configuration by ID."""
        with self.get_session() as session:
            return session.query(StreamConfiguration).filter(StreamConfiguration.id == config_id).first()
    
    def get_by_name(self, name: str) -> Optional[StreamConfiguration]:
        """Get stream configuration by name."""
        with self.get_session() as session:
            return session.query(StreamConfiguration).filter(StreamConfiguration.name == name).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[StreamConfiguration]:
        """Get all stream configurations with pagination."""
        with self.get_session() as session:
            return session.query(StreamConfiguration)\
                         .order_by(StreamConfiguration.created_at.desc())\
                         .offset(skip)\
                         .limit(limit)\
                         .all()
    
    def update(self, config_id: int, config_data: StreamConfigurationUpdate) -> Optional[StreamConfiguration]:
        """Update stream configuration."""
        with self.get_session() as session:
            try:
                db_config = session.query(StreamConfiguration).filter(StreamConfiguration.id == config_id).first()
                if not db_config:
                    return None
                
                update_data = config_data.dict(exclude_unset=True)
                # Handle URL conversion for updates
                if 'stream_url' in update_data and hasattr(config_data, 'stream_url') and config_data.stream_url is not None:
                    update_data['stream_url'] = str(config_data.stream_url)
                
                for field, value in update_data.items():
                    setattr(db_config, field, value)
                
                from ..utils.timezone_utils import get_local_now
                db_config.updated_at = get_local_now()
                session.commit()
                session.refresh(db_config)
                return db_config
            except IntegrityError as e:
                session.rollback()
                if "UNIQUE constraint failed" in str(e):
                    raise ValueError(f"Stream configuration with name '{config_data.name}' already exists")
                raise ValueError(f"Database error: {str(e)}")
    
    def delete(self, config_id: int) -> bool:
        """Delete stream configuration."""
        with self.get_session() as session:
            db_config = session.query(StreamConfiguration).filter(StreamConfiguration.id == config_id).first()
            if not db_config:
                return False
            
            # Check if configuration has active schedules
            active_schedules = session.query(RecordingSchedule)\
                                    .filter(and_(
                                        RecordingSchedule.stream_config_id == config_id,
                                        RecordingSchedule.is_active == True
                                    )).count()
            
            if active_schedules > 0:
                raise ValueError("Cannot delete stream configuration with active schedules")
            
            session.delete(db_config)
            session.commit()
            return True
    
    def search(self, query: str, skip: int = 0, limit: int = 100) -> List[StreamConfiguration]:
        """Search stream configurations by name, artist, or album."""
        with self.get_session() as session:
            search_filter = or_(
                StreamConfiguration.name.ilike(f"%{query}%"),
                StreamConfiguration.artist.ilike(f"%{query}%"),
                StreamConfiguration.album.ilike(f"%{query}%")
            )
            
            return session.query(StreamConfiguration)\
                         .filter(search_filter)\
                         .order_by(StreamConfiguration.created_at.desc())\
                         .offset(skip)\
                         .limit(limit)\
                         .all()


class ScheduleRepository(BaseRepository):
    """Repository for recording schedule management."""
    
    def create(self, schedule_data: RecordingScheduleCreate) -> RecordingSchedule:
        """Create a new recording schedule."""
        with self.get_session() as session:
            try:
                db_schedule = RecordingSchedule(**schedule_data.dict())
                # Calculate initial next run time
                db_schedule.update_next_run_time()
                
                session.add(db_schedule)
                session.commit()
                session.refresh(db_schedule)
                return db_schedule
            except IntegrityError as e:
                session.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    def get_by_id(self, schedule_id: int) -> Optional[RecordingSchedule]:
        """Get recording schedule by ID."""
        with self.get_session() as session:
            return session.query(RecordingSchedule).filter(RecordingSchedule.id == schedule_id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[RecordingSchedule]:
        """Get all recording schedules with pagination."""
        with self.get_session() as session:
            return session.query(RecordingSchedule)\
                         .order_by(RecordingSchedule.created_at.desc())\
                         .offset(skip)\
                         .limit(limit)\
                         .all()
    
    def get_by_stream_config(self, stream_config_id: int) -> List[RecordingSchedule]:
        """Get all schedules for a specific stream configuration."""
        with self.get_session() as session:
            return session.query(RecordingSchedule)\
                         .filter(RecordingSchedule.stream_config_id == stream_config_id)\
                         .order_by(RecordingSchedule.created_at.desc())\
                         .all()
    
    def get_active_schedules(self) -> List[RecordingSchedule]:
        """Get all active recording schedules."""
        with self.get_session() as session:
            from sqlalchemy.orm import joinedload
            return session.query(RecordingSchedule)\
                         .options(joinedload(RecordingSchedule.stream_config))\
                         .filter(RecordingSchedule.is_active == True)\
                         .order_by(RecordingSchedule.next_run_time.asc())\
                         .all()
    
    def get_due_schedules(self, current_time: datetime) -> List[RecordingSchedule]:
        """Get schedules that are due for execution."""
        with self.get_session() as session:
            return session.query(RecordingSchedule)\
                         .filter(and_(
                             RecordingSchedule.is_active == True,
                             RecordingSchedule.next_run_time <= current_time
                         ))\
                         .order_by(RecordingSchedule.next_run_time.asc())\
                         .all()
    
    def update(self, schedule_id: int, schedule_data: RecordingScheduleUpdate) -> Optional[RecordingSchedule]:
        """Update recording schedule."""
        with self.get_session() as session:
            try:
                db_schedule = session.query(RecordingSchedule).filter(RecordingSchedule.id == schedule_id).first()
                if not db_schedule:
                    return None
                
                update_data = schedule_data.dict(exclude_unset=True)
                for field, value in update_data.items():
                    setattr(db_schedule, field, value)
                
                # Recalculate next run time if cron expression changed
                if 'cron_expression' in update_data:
                    db_schedule.update_next_run_time()
                
                db_schedule.updated_at = datetime.now()
                session.commit()
                session.refresh(db_schedule)
                return db_schedule
            except IntegrityError as e:
                session.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    def delete(self, schedule_id: int) -> bool:
        """Delete recording schedule."""
        with self.get_session() as session:
            db_schedule = session.query(RecordingSchedule).filter(RecordingSchedule.id == schedule_id).first()
            if not db_schedule:
                return False
            
            # Check if schedule has active recording sessions
            active_sessions = session.query(RecordingSession)\
                                   .filter(and_(
                                       RecordingSession.schedule_id == schedule_id,
                                       RecordingSession.status.in_([
                                           RecordingStatus.RECORDING,
                                           RecordingStatus.PROCESSING
                                       ])
                                   )).count()
            
            if active_sessions > 0:
                raise ValueError("Cannot delete schedule with active recording sessions")
            
            # Check if there are any completed/failed sessions that reference this schedule
            total_sessions = session.query(RecordingSession)\
                                  .filter(RecordingSession.schedule_id == schedule_id)\
                                  .count()
            
            if total_sessions > 0:
                raise ValueError(f"Cannot delete schedule: {total_sessions} recording sessions reference this schedule. Delete the sessions first or they will become orphaned.")
            
            session.delete(db_schedule)
            session.commit()
            return True
    
    def update_next_run_time(self, schedule_id: int) -> Optional[RecordingSchedule]:
        """Update the next run time for a schedule."""
        with self.get_session() as session:
            db_schedule = session.query(RecordingSchedule).filter(RecordingSchedule.id == schedule_id).first()
            if not db_schedule:
                return None
            
            db_schedule.update_next_run_time()
            from ..utils.timezone_utils import get_local_now
            db_schedule.updated_at = get_local_now()
            session.commit()
            session.refresh(db_schedule)
            return db_schedule
    
    def increment_retry_count(self, schedule_id: int) -> Optional[RecordingSchedule]:
        """Increment retry count for a schedule."""
        with self.get_session() as session:
            db_schedule = session.query(RecordingSchedule).filter(RecordingSchedule.id == schedule_id).first()
            if not db_schedule:
                return None
            
            db_schedule.retry_count += 1
            from ..utils.timezone_utils import get_local_now
            db_schedule.updated_at = get_local_now()
            session.commit()
            session.refresh(db_schedule)
            return db_schedule
    
    def reset_retry_count(self, schedule_id: int) -> Optional[RecordingSchedule]:
        """Reset retry count for a schedule."""
        with self.get_session() as session:
            db_schedule = session.query(RecordingSchedule).filter(RecordingSchedule.id == schedule_id).first()
            if not db_schedule:
                return None
            
            db_schedule.retry_count = 0
            from ..utils.timezone_utils import get_local_now
            db_schedule.updated_at = get_local_now()
            session.commit()
            session.refresh(db_schedule)
            return db_schedule


class SessionRepository(BaseRepository):
    """Repository for recording session tracking."""
    
    def create(self, session_data: RecordingSessionCreate) -> RecordingSession:
        """Create a new recording session."""
        with self.get_session() as session:
            try:
                db_session = RecordingSession(**session_data.dict())
                session.add(db_session)
                session.commit()
                session.refresh(db_session)
                return db_session
            except IntegrityError as e:
                session.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    def get_by_id(self, session_id: int) -> Optional[RecordingSession]:
        """Get recording session by ID."""
        with self.get_session() as session:
            return session.query(RecordingSession).filter(RecordingSession.id == session_id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[RecordingSession]:
        """Get all recording sessions with pagination."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .order_by(RecordingSession.created_at.desc())\
                         .offset(skip)\
                         .limit(limit)\
                         .all()
    
    def get_by_schedule(self, schedule_id: int, skip: int = 0, limit: int = 100) -> List[RecordingSession]:
        """Get all sessions for a specific schedule."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .filter(RecordingSession.schedule_id == schedule_id)\
                         .order_by(RecordingSession.created_at.desc())\
                         .offset(skip)\
                         .limit(limit)\
                         .all()
    
    def get_by_status(self, status: RecordingStatus) -> List[RecordingSession]:
        """Get all sessions with a specific status."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .filter(RecordingSession.status == status)\
                         .order_by(RecordingSession.created_at.desc())\
                         .all()
    
    def get_active_sessions(self) -> List[RecordingSession]:
        """Get all active recording sessions."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .filter(RecordingSession.status.in_([
                             RecordingStatus.RECORDING,
                             RecordingStatus.PROCESSING
                         ]))\
                         .order_by(RecordingSession.start_time.desc())\
                         .all()
    
    def get_failed_transfers(self) -> List[RecordingSession]:
        """Get sessions with failed transfers."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .filter(and_(
                             RecordingSession.status == RecordingStatus.COMPLETED,
                             RecordingSession.transfer_status == TransferStatus.FAILED
                         ))\
                         .order_by(RecordingSession.created_at.desc())\
                         .all()
    
    def update(self, session_id: int, session_data: RecordingSessionUpdate) -> Optional[RecordingSession]:
        """Update recording session."""
        with self.get_session() as session:
            try:
                db_session = session.query(RecordingSession).filter(RecordingSession.id == session_id).first()
                if not db_session:
                    return None
                
                update_data = session_data.dict(exclude_unset=True)
                for field, value in update_data.items():
                    setattr(db_session, field, value)
                
                from ..utils.timezone_utils import get_local_now
                db_session.updated_at = get_local_now()
                session.commit()
                session.refresh(db_session)
                return db_session
            except IntegrityError as e:
                session.rollback()
                raise ValueError(f"Database error: {str(e)}")
    
    def update_status(self, session_id: int, status: RecordingStatus, error_message: Optional[str] = None) -> Optional[RecordingSession]:
        """Update session status."""
        with self.get_session() as session:
            db_session = session.query(RecordingSession).filter(RecordingSession.id == session_id).first()
            if not db_session:
                return None
            
            db_session.status = status
            if error_message:
                db_session.error_message = error_message
            
            # Set end time if status is completed or failed
            from ..utils.timezone_utils import get_local_now
            if status in [RecordingStatus.COMPLETED, RecordingStatus.FAILED]:
                db_session.end_time = get_local_now()
            
            db_session.updated_at = get_local_now()
            session.commit()
            session.refresh(db_session)
            return db_session
    
    def update_transfer_status(self, session_id: int, transfer_status: TransferStatus, error_message: Optional[str] = None) -> Optional[RecordingSession]:
        """Update transfer status."""
        with self.get_session() as session:
            db_session = session.query(RecordingSession).filter(RecordingSession.id == session_id).first()
            if not db_session:
                return None
            
            db_session.transfer_status = transfer_status
            if error_message:
                db_session.transfer_error_message = error_message
            
            from ..utils.timezone_utils import get_local_now
            db_session.updated_at = get_local_now()
            session.commit()
            session.refresh(db_session)
            return db_session
    
    def update_file_info(self, session_id: int, file_path: str) -> Optional[RecordingSession]:
        """Update file path and size information."""
        with self.get_session() as session:
            db_session = session.query(RecordingSession).filter(RecordingSession.id == session_id).first()
            if not db_session:
                return None
            
            db_session.update_file_info(file_path)
            from ..utils.timezone_utils import get_local_now
            db_session.updated_at = get_local_now()
            session.commit()
            session.refresh(db_session)
            return db_session
    
    def delete(self, session_id: int) -> bool:
        """Delete recording session."""
        with self.get_session() as session:
            db_session = session.query(RecordingSession).filter(RecordingSession.id == session_id).first()
            if not db_session:
                return False
            
            # Don't allow deletion of active sessions
            if db_session.status in [RecordingStatus.RECORDING, RecordingStatus.PROCESSING]:
                raise ValueError("Cannot delete active recording session")
            
            session.delete(db_session)
            session.commit()
            return True
    
    def get_recent_sessions(self, days: int = 7, limit: int = 50) -> List[RecordingSession]:
        """Get recent recording sessions within specified days."""
        with self.get_session() as session:
            from ..utils.timezone_utils import get_local_now
            cutoff_date = get_local_now() - timedelta(days=days)
            return session.query(RecordingSession)\
                         .filter(RecordingSession.created_at >= cutoff_date)\
                         .order_by(RecordingSession.created_at.desc())\
                         .limit(limit)\
                         .all()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get recording session statistics."""
        with self.get_session() as session:
            total_sessions = session.query(RecordingSession).count()
            completed_sessions = session.query(RecordingSession)\
                                       .filter(RecordingSession.status == RecordingStatus.COMPLETED)\
                                       .count()
            failed_sessions = session.query(RecordingSession)\
                                    .filter(RecordingSession.status == RecordingStatus.FAILED)\
                                    .count()
            active_sessions = session.query(RecordingSession)\
                                    .filter(RecordingSession.status.in_([
                                        RecordingStatus.RECORDING,
                                        RecordingStatus.PROCESSING
                                    ]))\
                                    .count()
            
            return {
                "total_sessions": total_sessions,
                "completed_sessions": completed_sessions,
                "failed_sessions": failed_sessions,
                "active_sessions": active_sessions,
                "success_rate": round((completed_sessions / total_sessions * 100) if total_sessions > 0 else 0, 2)
            }

    def get_recent_sessions_for_schedule(self, schedule_id: int, limit: int = 10) -> List[RecordingSession]:
        """Get recent recording sessions for a specific schedule."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .filter(RecordingSession.schedule_id == schedule_id)\
                         .order_by(RecordingSession.created_at.desc())\
                         .limit(limit)\
                         .all()
    
    def get_sessions_since_date(self, schedule_id: int, since_date: datetime) -> List[RecordingSession]:
        """Get recording sessions for a schedule since a specific date."""
        with self.get_session() as session:
            return session.query(RecordingSession)\
                         .filter(and_(
                             RecordingSession.schedule_id == schedule_id,
                             RecordingSession.created_at >= since_date
                         ))\
                         .order_by(RecordingSession.created_at.desc())\
                         .all()
    
    def delete_sessions_before_date(self, cutoff_date: datetime) -> int:
        """Delete recording sessions created before the cutoff date."""
        with self.get_session() as session:
            # Only delete completed or failed sessions, not active ones
            deleted_count = session.query(RecordingSession)\
                                  .filter(and_(
                                      RecordingSession.created_at < cutoff_date,
                                      RecordingSession.status.in_([
                                          RecordingStatus.COMPLETED,
                                          RecordingStatus.FAILED,
                                          RecordingStatus.CANCELLED
                                      ])
                                  ))\
                                  .delete(synchronize_session=False)
            
            session.commit()
            return deleted_count