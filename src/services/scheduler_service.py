"""
SchedulerService using APScheduler for managing recording schedules.
Handles cron expression parsing, job scheduling, and persistence across container restarts.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from croniter import croniter

from ..models.recording_schedule import RecordingSchedule
from ..models.recording_session import RecordingSession, RecordingStatus
from ..models.stream_configuration import StreamConfiguration
from ..models.repositories import ScheduleRepository, SessionRepository, ConfigurationRepository
from ..config import config


class SchedulerService:
    """
    Service for managing recording schedules using APScheduler.
    Provides cron expression parsing, job scheduling, and persistence.
    """
    
    def __init__(self, database_url: Optional[str] = None, db_manager=None):
        """
        Initialize SchedulerService.
        
        Args:
            database_url: Database URL for job persistence (defaults to config.DATABASE_URL)
            db_manager: Database manager instance for repositories
        """
        self.database_url = database_url or config.DATABASE_URL
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Get database manager if not provided
        if db_manager is None:
            from src.models.database import get_db_manager
            db_manager = get_db_manager()
        
        # Repositories
        self.schedule_repo = ScheduleRepository(db_manager)
        self.session_repo = SessionRepository(db_manager)
        self.config_repo = ConfigurationRepository(db_manager)
        
        # Active recording sessions tracking
        self.active_sessions: Dict[int, Any] = {}  # session_id -> RecordingSessionManager
        self._sessions_lock = threading.Lock()
        
        # Callbacks
        self.recording_start_callback: Optional[Callable[[int, RecordingSchedule, StreamConfiguration], Any]] = None
        self.job_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.session_completion_callback: Optional[Callable[[int], None]] = None
        
        # APScheduler configuration
        self.scheduler: Optional[BackgroundScheduler] = None
        self._setup_scheduler()
        
        self.logger.info("SchedulerService initialized")
    
    def _setup_scheduler(self) -> None:
        """Set up APScheduler with persistence and thread pool."""
        try:
            # Configure job store for persistence
            jobstores = {
                'default': SQLAlchemyJobStore(url=self.database_url, tablename='apscheduler_jobs')
            }
            
            # Configure thread pool executor with concurrent recording limits
            executors = {
                'default': ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_RECORDINGS)
            }
            
            # Job defaults
            job_defaults = {
                'coalesce': True,  # Combine multiple pending executions into one
                'max_instances': 1,  # Only one instance of each job at a time
                'misfire_grace_time': 300  # 5 minutes grace time for missed jobs
            }
            
            # Create scheduler
            self.scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='UTC'
            )
            
            # Add event listeners
            self.scheduler.add_listener(self._job_executed_listener, EVENT_JOB_EXECUTED)
            self.scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR)
            self.scheduler.add_listener(self._job_missed_listener, EVENT_JOB_MISSED)
            
            self.logger.info("APScheduler configured successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup scheduler: {e}")
            raise
    
    def start(self) -> bool:
        """
        Start the scheduler service.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            if self.scheduler and not self.scheduler.running:
                self.scheduler.start()
                self.logger.info("SchedulerService started")
                
                # Load and schedule existing active schedules
                self._load_existing_schedules()
                
                return True
            else:
                self.logger.warning("Scheduler already running or not initialized")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {e}")
            return False
    
    def stop(self) -> bool:
        """
        Stop the scheduler service.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            if self.scheduler and self.scheduler.running:
                # Stop all active recording sessions
                self._stop_all_active_sessions()
                
                # Shutdown scheduler
                self.scheduler.shutdown(wait=True)
                self.logger.info("SchedulerService stopped")
                return True
            else:
                self.logger.warning("Scheduler not running")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to stop scheduler: {e}")
            return False
    
    def is_running(self) -> bool:
        """
        Check if the scheduler service is running.
        
        Returns:
            True if scheduler is running, False otherwise
        """
        return self.scheduler is not None and self.scheduler.running
    
    def _load_existing_schedules(self) -> None:
        """Load and schedule existing active schedules from database."""
        try:
            active_schedules = self.schedule_repo.get_active_schedules()
            
            for schedule in active_schedules:
                self._schedule_recording_job(schedule)
            
            self.logger.info(f"Loaded {len(active_schedules)} existing schedules")
            
        except Exception as e:
            self.logger.error(f"Failed to load existing schedules: {e}")
    
    def validate_cron_expression(self, cron_expression: str) -> bool:
        """
        Validate cron expression format and syntax.
        
        Args:
            cron_expression: Cron expression to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if not cron_expression or not cron_expression.strip():
                return False
            
            cron_expression = cron_expression.strip()
            
            # Check basic format (5 fields)
            parts = cron_expression.split()
            if len(parts) != 5:
                return False
            
            # Test with croniter
            croniter(cron_expression)
            
            # Test with APScheduler CronTrigger
            CronTrigger.from_crontab(cron_expression)
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Invalid cron expression '{cron_expression}': {e}")
            return False
    
    def calculate_next_run_time(self, cron_expression: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
        """
        Calculate next run time for cron expression.
        
        Args:
            cron_expression: Cron expression
            base_time: Base time for calculation (defaults to now)
            
        Returns:
            Next run time or None if invalid expression
        """
        try:
            if not self.validate_cron_expression(cron_expression):
                return None
            
            base_time = base_time or datetime.now()
            cron = croniter(cron_expression, base_time)
            return cron.get_next(datetime)
            
        except Exception as e:
            self.logger.error(f"Failed to calculate next run time: {e}")
            return None
    
    def add_schedule(self, schedule: RecordingSchedule) -> bool:
        """
        Add a new recording schedule.
        
        Args:
            schedule: RecordingSchedule object
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            if not self.validate_cron_expression(schedule.cron_expression):
                self.logger.error(f"Invalid cron expression: {schedule.cron_expression}")
                return False
            
            # Update next run time
            schedule.update_next_run_time()
            
            # Schedule the job if active
            if schedule.is_active:
                success = self._schedule_recording_job(schedule)
                if not success:
                    return False
            
            self.logger.info(f"Added schedule {schedule.id}: {schedule.cron_expression}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add schedule: {e}")
            return False
    
    def update_schedule(self, schedule: RecordingSchedule) -> bool:
        """
        Update an existing recording schedule.
        
        Args:
            schedule: Updated RecordingSchedule object
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            if not self.validate_cron_expression(schedule.cron_expression):
                self.logger.error(f"Invalid cron expression: {schedule.cron_expression}")
                return False
            
            # Remove existing job
            self._remove_recording_job(schedule.id)
            
            # Update next run time
            schedule.update_next_run_time()
            
            # Schedule new job if active
            if schedule.is_active:
                success = self._schedule_recording_job(schedule)
                if not success:
                    return False
            
            self.logger.info(f"Updated schedule {schedule.id}: {schedule.cron_expression}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update schedule: {e}")
            return False
    
    def remove_schedule(self, schedule_id: int) -> bool:
        """
        Remove a recording schedule.
        
        Args:
            schedule_id: Schedule ID to remove
            
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            # Remove scheduled job
            success = self._remove_recording_job(schedule_id)
            
            self.logger.info(f"Removed schedule {schedule_id}")
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to remove schedule: {e}")
            return False
    
    def _schedule_recording_job(self, schedule: RecordingSchedule) -> bool:
        """
        Schedule a recording job using APScheduler.
        
        Args:
            schedule: RecordingSchedule object
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            if not self.scheduler or not self.scheduler.running:
                self.logger.error("Scheduler not running")
                return False
            
            job_id = f"recording_schedule_{schedule.id}"
            
            # Create cron trigger
            trigger = CronTrigger.from_crontab(schedule.cron_expression, timezone='UTC')
            
            # Schedule job
            self.scheduler.add_job(
                func=self._execute_recording_job,
                trigger=trigger,
                args=[schedule.id],
                id=job_id,
                name=f"Recording: {schedule.stream_config.name if schedule.stream_config else 'Unknown'}",
                replace_existing=True
            )
            
            self.logger.info(f"Scheduled job {job_id} with cron: {schedule.cron_expression}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to schedule recording job: {e}")
            return False
    
    def _remove_recording_job(self, schedule_id: int) -> bool:
        """
        Remove a scheduled recording job.
        
        Args:
            schedule_id: Schedule ID
            
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            if not self.scheduler:
                return True
            
            job_id = f"recording_schedule_{schedule_id}"
            
            try:
                self.scheduler.remove_job(job_id)
                self.logger.info(f"Removed scheduled job {job_id}")
            except Exception:
                # Job might not exist, which is fine
                pass
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove recording job: {e}")
            return False
    
    def _execute_recording_job(self, schedule_id: int) -> None:
        """
        Execute a recording job.
        
        Args:
            schedule_id: Schedule ID to execute
        """
        try:
            self.logger.info(f"Executing recording job for schedule {schedule_id}")
            
            # Get schedule and stream configuration
            schedule = self.schedule_repo.get_by_id(schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {schedule_id} not found")
                return
            
            if not schedule.is_active:
                self.logger.info(f"Schedule {schedule_id} is not active, skipping")
                return
            
            stream_config = self.config_repo.get_by_id(schedule.stream_config_id)
            if not stream_config:
                self.logger.error(f"Stream configuration {schedule.stream_config_id} not found")
                return
            
            # Check concurrent recording limits
            if not self._can_start_recording():
                self.logger.warning(f"Maximum concurrent recordings reached, skipping schedule {schedule_id}")
                return
            
            # Create recording session
            session = RecordingSession(
                schedule_id=schedule_id,
                start_time=datetime.now(),
                status=RecordingStatus.SCHEDULED
            )
            
            # Save session to database
            session = self.session_repo.create(session)
            
            # Update schedule's last run time and next run time
            schedule.last_run_time = datetime.now()
            schedule.update_next_run_time()
            self.schedule_repo.update(schedule)
            
            # Start recording using callback
            if self.recording_start_callback:
                try:
                    recording_manager = self.recording_start_callback(session.id, schedule, stream_config)
                    
                    # Track active session
                    with self._sessions_lock:
                        self.active_sessions[session.id] = recording_manager
                    
                    self.logger.info(f"Started recording session {session.id} for schedule {schedule_id}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to start recording via callback: {e}")
                    # Update session status to failed
                    session.status = RecordingStatus.FAILED
                    session.error_message = str(e)
                    self.session_repo.update(session)
            else:
                self.logger.error("No recording start callback configured")
                session.status = RecordingStatus.FAILED
                session.error_message = "No recording start callback configured"
                self.session_repo.update(session)
            
        except Exception as e:
            self.logger.error(f"Error executing recording job for schedule {schedule_id}: {e}")
    
    def _can_start_recording(self) -> bool:
        """
        Check if a new recording can be started based on concurrent limits.
        
        Returns:
            True if recording can be started, False otherwise
        """
        with self._sessions_lock:
            active_count = len([
                session for session in self.active_sessions.values()
                if session and hasattr(session, 'current_stage') and 
                session.current_stage.value in ['recording', 'processing', 'transferring']
            ])
            
            return active_count < config.MAX_CONCURRENT_RECORDINGS
    
    def _stop_all_active_sessions(self) -> None:
        """Stop all active recording sessions."""
        with self._sessions_lock:
            for session_id, session_manager in list(self.active_sessions.items()):
                try:
                    if session_manager and hasattr(session_manager, 'stop_recording'):
                        session_manager.stop_recording()
                        self.logger.info(f"Stopped active recording session {session_id}")
                except Exception as e:
                    self.logger.error(f"Error stopping session {session_id}: {e}")
            
            self.active_sessions.clear()
    
    def remove_completed_session(self, session_id: int) -> None:
        """
        Remove a completed recording session from active tracking.
        
        Args:
            session_id: Session ID to remove
        """
        with self._sessions_lock:
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                self.logger.debug(f"Removed completed session {session_id} from active tracking")
    
    def get_active_sessions(self) -> Dict[int, Any]:
        """
        Get currently active recording sessions.
        
        Returns:
            Dictionary of session_id -> RecordingSessionManager
        """
        with self._sessions_lock:
            return dict(self.active_sessions)
    
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """
        Get list of currently scheduled jobs.
        
        Returns:
            List of job information dictionaries
        """
        if not self.scheduler:
            return []
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return jobs
    
    def set_recording_start_callback(self, callback: Callable[[int, RecordingSchedule, StreamConfiguration], Any]) -> None:
        """
        Set callback function for starting recordings.
        
        Args:
            callback: Function that takes (session_id, schedule, stream_config) and returns RecordingSessionManager
        """
        self.recording_start_callback = callback
        self.logger.info("Recording start callback configured")
    
    def set_job_event_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Set callback function for job events.
        
        Args:
            callback: Function that takes (event_type, event_data)
        """
        self.job_event_callback = callback
        self.logger.info("Job event callback configured")
    
    def set_session_completion_callback(self, callback: Callable[[int], None]) -> None:
        """
        Set callback function for session completion.
        
        Args:
            callback: Function that takes (session_id) for completion handling
        """
        self.session_completion_callback = callback
        self.logger.info("Session completion callback configured")
    
    def _job_executed_listener(self, event) -> None:
        """Handle job executed events."""
        try:
            self.logger.info(f"Job executed: {event.job_id}")
            
            if self.job_event_callback:
                self.job_event_callback('job_executed', {
                    'job_id': event.job_id,
                    'scheduled_run_time': event.scheduled_run_time.isoformat() if event.scheduled_run_time else None,
                    'retval': str(event.retval) if event.retval else None
                })
                
        except Exception as e:
            self.logger.error(f"Error in job executed listener: {e}")
    
    def _job_error_listener(self, event) -> None:
        """Handle job error events."""
        try:
            self.logger.error(f"Job error: {event.job_id} - {event.exception}")
            
            if self.job_event_callback:
                self.job_event_callback('job_error', {
                    'job_id': event.job_id,
                    'scheduled_run_time': event.scheduled_run_time.isoformat() if event.scheduled_run_time else None,
                    'exception': str(event.exception),
                    'traceback': event.traceback
                })
                
        except Exception as e:
            self.logger.error(f"Error in job error listener: {e}")
    
    def _job_missed_listener(self, event) -> None:
        """Handle job missed events."""
        try:
            self.logger.warning(f"Job missed: {event.job_id}")
            
            if self.job_event_callback:
                self.job_event_callback('job_missed', {
                    'job_id': event.job_id,
                    'scheduled_run_time': event.scheduled_run_time.isoformat() if event.scheduled_run_time else None
                })
                
        except Exception as e:
            self.logger.error(f"Error in job missed listener: {e}")
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        Get scheduler service status information.
        
        Returns:
            Dictionary with service status
        """
        return {
            'running': self.scheduler.running if self.scheduler else False,
            'active_sessions_count': len(self.active_sessions),
            'max_concurrent_recordings': config.MAX_CONCURRENT_RECORDINGS,
            'scheduled_jobs_count': len(self.scheduler.get_jobs()) if self.scheduler else 0,
            'database_url': self.database_url
        }