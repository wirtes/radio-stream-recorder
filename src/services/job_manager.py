"""
JobManager for schedule lifecycle management.
Handles job creation, updating, deletion, and status tracking.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from ..models.recording_schedule import RecordingSchedule, RecordingScheduleCreate, RecordingScheduleUpdate
from ..models.recording_session import RecordingSession, RecordingStatus
from ..models.stream_configuration import StreamConfiguration
from ..models.repositories import ScheduleRepository, SessionRepository, ConfigurationRepository
from .scheduler_service import SchedulerService


class JobStatus(Enum):
    """Job status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class JobManager:
    """
    Manager for recording schedule lifecycle management.
    Provides high-level operations for job creation, updating, and monitoring.
    """
    
    def __init__(self, scheduler_service: SchedulerService):
        """
        Initialize JobManager.
        
        Args:
            scheduler_service: SchedulerService instance
        """
        self.scheduler_service = scheduler_service
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Repositories
        self.schedule_repo = ScheduleRepository()
        self.session_repo = SessionRepository()
        self.config_repo = ConfigurationRepository()
        
        self.logger.info("JobManager initialized")
    
    def create_job(self, job_data: RecordingScheduleCreate) -> Optional[RecordingSchedule]:
        """
        Create a new recording job.
        
        Args:
            job_data: Job creation data
            
        Returns:
            Created RecordingSchedule or None if failed
        """
        try:
            # Validate stream configuration exists
            stream_config = self.config_repo.get_by_id(job_data.stream_config_id)
            if not stream_config:
                self.logger.error(f"Stream configuration {job_data.stream_config_id} not found")
                return None
            
            # Validate cron expression
            if not self.scheduler_service.validate_cron_expression(job_data.cron_expression):
                self.logger.error(f"Invalid cron expression: {job_data.cron_expression}")
                return None
            
            # Create schedule object
            schedule = RecordingSchedule(
                stream_config_id=job_data.stream_config_id,
                cron_expression=job_data.cron_expression,
                duration_minutes=job_data.duration_minutes,
                is_active=job_data.is_active,
                max_retries=job_data.max_retries
            )
            
            # Calculate next run time
            schedule.update_next_run_time()
            
            # Save to database
            schedule = self.schedule_repo.create(schedule)
            
            # Add to scheduler if active
            if schedule.is_active:
                success = self.scheduler_service.add_schedule(schedule)
                if not success:
                    self.logger.error(f"Failed to add schedule {schedule.id} to scheduler")
                    # Don't delete from database, just mark as inactive
                    schedule.is_active = False
                    self.schedule_repo.update(schedule)
            
            self.logger.info(f"Created job {schedule.id} for stream '{stream_config.name}'")
            return schedule
            
        except Exception as e:
            self.logger.error(f"Failed to create job: {e}")
            return None
    
    def update_job(self, schedule_id: int, job_data: RecordingScheduleUpdate) -> Optional[RecordingSchedule]:
        """
        Update an existing recording job.
        
        Args:
            schedule_id: Schedule ID to update
            job_data: Job update data
            
        Returns:
            Updated RecordingSchedule or None if failed
        """
        try:
            # Get existing schedule
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {schedule_id} not found")
                return None
            
            # Validate cron expression if provided
            if job_data.cron_expression is not None:
                if not self.scheduler_service.validate_cron_expression(job_data.cron_expression):
                    self.logger.error(f"Invalid cron expression: {job_data.cron_expression}")
                    return None
                schedule.cron_expression = job_data.cron_expression
            
            # Update fields
            if job_data.duration_minutes is not None:
                schedule.duration_minutes = job_data.duration_minutes
            
            if job_data.max_retries is not None:
                schedule.max_retries = job_data.max_retries
            
            # Handle activation/deactivation
            old_active_state = schedule.is_active
            if job_data.is_active is not None:
                schedule.is_active = job_data.is_active
            
            # Update next run time if cron expression changed
            if job_data.cron_expression is not None:
                schedule.update_next_run_time()
            
            # Save to database
            schedule = self.schedule_repo.update(schedule)
            
            # Update scheduler
            if old_active_state or schedule.is_active:
                # If was active or now active, update scheduler
                success = self.scheduler_service.update_schedule(schedule)
                if not success and schedule.is_active:
                    self.logger.error(f"Failed to update schedule {schedule_id} in scheduler")
                    # Mark as inactive if scheduler update failed
                    schedule.is_active = False
                    self.schedule_repo.update(schedule)
            
            self.logger.info(f"Updated job {schedule_id}")
            return schedule
            
        except Exception as e:
            self.logger.error(f"Failed to update job {schedule_id}: {e}")
            return None
    
    def delete_job(self, schedule_id: int) -> bool:
        """
        Delete a recording job.
        
        Args:
            schedule_id: Schedule ID to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # Get schedule
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.warning(f"Schedule {schedule_id} not found for deletion")
                return True  # Already deleted
            
            # Remove from scheduler
            self.scheduler_service.remove_schedule(schedule_id)
            
            # Delete from database (this will cascade to sessions)
            success = self.schedule_repo.delete(schedule_id)
            
            if success:
                self.logger.info(f"Deleted job {schedule_id}")
            else:
                self.logger.error(f"Failed to delete job {schedule_id} from database")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to delete job {schedule_id}: {e}")
            return False
    
    def activate_job(self, schedule_id: int) -> bool:
        """
        Activate a recording job.
        
        Args:
            schedule_id: Schedule ID to activate
            
        Returns:
            True if activated successfully, False otherwise
        """
        try:
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {schedule_id} not found")
                return False
            
            if schedule.is_active:
                self.logger.info(f"Schedule {schedule_id} is already active")
                return True
            
            # Update database
            schedule.is_active = True
            schedule.update_next_run_time()
            schedule = self.schedule_repo.update(schedule)
            
            # Add to scheduler
            success = self.scheduler_service.add_schedule(schedule)
            if not success:
                # Revert database change
                schedule.is_active = False
                self.schedule_repo.update(schedule)
                return False
            
            self.logger.info(f"Activated job {schedule_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to activate job {schedule_id}: {e}")
            return False
    
    def deactivate_job(self, schedule_id: int) -> bool:
        """
        Deactivate a recording job.
        
        Args:
            schedule_id: Schedule ID to deactivate
            
        Returns:
            True if deactivated successfully, False otherwise
        """
        try:
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {schedule_id} not found")
                return False
            
            if not schedule.is_active:
                self.logger.info(f"Schedule {schedule_id} is already inactive")
                return True
            
            # Remove from scheduler
            self.scheduler_service.remove_schedule(schedule_id)
            
            # Update database
            schedule.is_active = False
            self.schedule_repo.update(schedule)
            
            self.logger.info(f"Deactivated job {schedule_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to deactivate job {schedule_id}: {e}")
            return False
    
    def get_job_status(self, schedule_id: int) -> Optional[JobStatus]:
        """
        Get current status of a recording job.
        
        Args:
            schedule_id: Schedule ID
            
        Returns:
            JobStatus or None if not found
        """
        try:
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                return None
            
            if not schedule.is_active:
                return JobStatus.INACTIVE
            
            # Check if currently running
            active_sessions = self.scheduler_service.get_active_sessions()
            for session_manager in active_sessions.values():
                if (hasattr(session_manager, 'session_id') and 
                    hasattr(session_manager, 'current_stage')):
                    
                    # Get session from database to check schedule_id
                    session = self.session_repo.get_by_id(session_manager.session_id)
                    if session and session.schedule_id == schedule_id:
                        stage = session_manager.current_stage.value
                        if stage in ['recording', 'processing', 'transferring']:
                            return JobStatus.RUNNING
            
            # Check recent sessions for failure status
            recent_sessions = self.session_repo.get_recent_sessions_for_schedule(
                schedule_id, limit=1
            )
            
            if recent_sessions:
                last_session = recent_sessions[0]
                if last_session.status == RecordingStatus.FAILED:
                    return JobStatus.FAILED
                elif last_session.status == RecordingStatus.COMPLETED:
                    return JobStatus.COMPLETED
            
            return JobStatus.SCHEDULED
            
        except Exception as e:
            self.logger.error(f"Failed to get job status for {schedule_id}: {e}")
            return None
    
    def get_next_execution_time(self, schedule_id: int) -> Optional[datetime]:
        """
        Get next execution time for a recording job.
        
        Args:
            schedule_id: Schedule ID
            
        Returns:
            Next execution datetime or None if not found/inactive
        """
        try:
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule or not schedule.is_active:
                return None
            
            return schedule.next_run_time
            
        except Exception as e:
            self.logger.error(f"Failed to get next execution time for {schedule_id}: {e}")
            return None
    
    def get_job_history(self, schedule_id: int, limit: int = 10) -> List[RecordingSession]:
        """
        Get execution history for a recording job.
        
        Args:
            schedule_id: Schedule ID
            limit: Maximum number of sessions to return
            
        Returns:
            List of RecordingSession objects
        """
        try:
            return self.session_repo.get_recent_sessions_for_schedule(schedule_id, limit)
            
        except Exception as e:
            self.logger.error(f"Failed to get job history for {schedule_id}: {e}")
            return []
    
    def get_job_statistics(self, schedule_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Get statistics for a recording job.
        
        Args:
            schedule_id: Schedule ID
            days: Number of days to look back
            
        Returns:
            Dictionary with job statistics
        """
        try:
            since_date = datetime.now() - timedelta(days=days)
            sessions = self.session_repo.get_sessions_since_date(schedule_id, since_date)
            
            total_sessions = len(sessions)
            successful_sessions = len([s for s in sessions if s.status == RecordingStatus.COMPLETED])
            failed_sessions = len([s for s in sessions if s.status == RecordingStatus.FAILED])
            
            # Calculate success rate
            success_rate = (successful_sessions / total_sessions * 100) if total_sessions > 0 else 0
            
            # Calculate total recording time
            total_duration_minutes = sum([
                s.get_duration_minutes() or 0 for s in sessions 
                if s.status == RecordingStatus.COMPLETED
            ])
            
            # Calculate total file size
            total_file_size_bytes = sum([
                s.file_size_bytes or 0 for s in sessions 
                if s.status == RecordingStatus.COMPLETED and s.file_size_bytes
            ])
            
            return {
                'schedule_id': schedule_id,
                'period_days': days,
                'total_sessions': total_sessions,
                'successful_sessions': successful_sessions,
                'failed_sessions': failed_sessions,
                'success_rate_percent': round(success_rate, 2),
                'total_duration_minutes': total_duration_minutes,
                'total_file_size_bytes': total_file_size_bytes,
                'total_file_size_mb': round(total_file_size_bytes / (1024 * 1024), 2) if total_file_size_bytes > 0 else 0,
                'average_file_size_mb': round(total_file_size_bytes / (1024 * 1024) / successful_sessions, 2) if successful_sessions > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get job statistics for {schedule_id}: {e}")
            return {}
    
    def get_all_jobs_summary(self) -> List[Dict[str, Any]]:
        """
        Get summary of all recording jobs.
        
        Returns:
            List of job summary dictionaries
        """
        try:
            schedules = self.schedule_repo.get_all()
            summaries = []
            
            for schedule in schedules:
                # Get stream configuration
                stream_config = self.config_repo.get_by_id(schedule.stream_config_id)
                
                # Get job status
                status = self.get_job_status(schedule.id)
                
                # Get recent session
                recent_sessions = self.session_repo.get_recent_sessions_for_schedule(schedule.id, limit=1)
                last_session = recent_sessions[0] if recent_sessions else None
                
                summary = {
                    'schedule_id': schedule.id,
                    'stream_name': stream_config.name if stream_config else 'Unknown',
                    'cron_expression': schedule.cron_expression,
                    'duration_minutes': schedule.duration_minutes,
                    'is_active': schedule.is_active,
                    'status': status.value if status else 'unknown',
                    'next_run_time': schedule.next_run_time.isoformat() if schedule.next_run_time else None,
                    'last_run_time': schedule.last_run_time.isoformat() if schedule.last_run_time else None,
                    'retry_count': schedule.retry_count,
                    'max_retries': schedule.max_retries,
                    'created_at': schedule.created_at.isoformat(),
                    'last_session_status': last_session.status.value if last_session else None,
                    'last_session_error': last_session.error_message if last_session else None
                }
                
                summaries.append(summary)
            
            return summaries
            
        except Exception as e:
            self.logger.error(f"Failed to get all jobs summary: {e}")
            return []
    
    def handle_job_failure(self, schedule_id: int, session_id: int, error_message: str) -> bool:
        """
        Handle job failure and implement retry logic.
        
        Args:
            schedule_id: Schedule ID
            session_id: Session ID that failed
            error_message: Error message
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {schedule_id} not found for failure handling")
                return False
            
            session = self.session_repo.get_by_id(session_id)
            if not session:
                self.logger.error(f"Session {session_id} not found for failure handling")
                return False
            
            # Update session status
            session.status = RecordingStatus.FAILED
            session.error_message = error_message
            session.end_time = datetime.now()
            self.session_repo.update(session)
            
            # Increment retry count
            schedule.retry_count += 1
            
            # Check if max retries exceeded
            if schedule.retry_count >= schedule.max_retries:
                self.logger.warning(f"Schedule {schedule_id} exceeded max retries ({schedule.max_retries})")
                
                # Optionally deactivate schedule after max retries
                # schedule.is_active = False
                # self.scheduler_service.remove_schedule(schedule_id)
            
            # Update schedule
            self.schedule_repo.update(schedule)
            
            self.logger.info(f"Handled failure for schedule {schedule_id}, retry count: {schedule.retry_count}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to handle job failure for schedule {schedule_id}: {e}")
            return False
    
    def reset_job_retry_count(self, schedule_id: int) -> bool:
        """
        Reset retry count for a recording job.
        
        Args:
            schedule_id: Schedule ID
            
        Returns:
            True if reset successfully, False otherwise
        """
        try:
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {schedule_id} not found")
                return False
            
            schedule.retry_count = 0
            self.schedule_repo.update(schedule)
            
            self.logger.info(f"Reset retry count for schedule {schedule_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reset retry count for {schedule_id}: {e}")
            return False
    
    def cleanup_old_sessions(self, days_to_keep: int = 30) -> int:
        """
        Clean up old recording sessions.
        
        Args:
            days_to_keep: Number of days of sessions to keep
            
        Returns:
            Number of sessions cleaned up
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            deleted_count = self.session_repo.delete_sessions_before_date(cutoff_date)
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old recording sessions")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old sessions: {e}")
            return 0