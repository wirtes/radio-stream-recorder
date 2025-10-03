"""
Workflow Coordinator for integrating all recording components.
Connects scheduler to recording components, audio processing, and file transfer.
"""

import logging
import threading
import time
from typing import Dict, Optional, Any, Callable
from datetime import datetime

from .recording_session_manager import RecordingSessionManager
from .scheduler_service import SchedulerService
from .transfer_queue import TransferQueue
from .backup_service import BackupService
from ..models.recording_schedule import RecordingSchedule
from ..models.recording_session import RecordingSession, RecordingStatus
from ..models.stream_configuration import StreamConfiguration
from ..models.repositories import SessionRepository, ConfigurationRepository
from ..models.database import DatabaseManager
from ..config import config


class WorkflowCoordinator:
    """
    Coordinates the complete recording workflow between all services.
    Handles the integration of scheduler, recording, processing, and transfer.
    """
    
    def __init__(
        self,
        scheduler_service: SchedulerService,
        transfer_queue: TransferQueue,
        logging_service: Optional[Any] = None
    ):
        """
        Initialize WorkflowCoordinator.
        
        Args:
            scheduler_service: Scheduler service instance
            transfer_queue: Transfer queue service instance
            logging_service: Logging service instance (optional)
        """
        self.scheduler_service = scheduler_service
        self.transfer_queue = transfer_queue
        self.logging_service = logging_service
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Repositories
        self.db_manager = DatabaseManager()
        self.session_repo = SessionRepository(self.db_manager)
        self.config_repo = ConfigurationRepository(self.db_manager)
        
        # Backup service
        self.backup_service = BackupService(self.db_manager)
        
        # Automatic backup tracking
        self._last_backup_time = None
        self._backup_interval_hours = 24  # Create backup every 24 hours
        
        # Active recording sessions
        self.active_sessions: Dict[int, RecordingSessionManager] = {}
        self._sessions_lock = threading.Lock()
        
        # Setup scheduler callback
        self._setup_scheduler_integration()
    
    def _setup_scheduler_integration(self):
        """Setup integration with scheduler service."""
        # Set the recording start callback in scheduler
        self.scheduler_service.set_recording_start_callback(self._start_recording_session)
        
        # Set session completion callback
        self.scheduler_service.set_session_completion_callback(self._handle_session_completion)
    
    def _start_recording_session(
        self, 
        session_id: int, 
        schedule: RecordingSchedule, 
        stream_config: StreamConfiguration
    ) -> RecordingSessionManager:
        """
        Start a new recording session.
        
        Args:
            session_id: Database ID of the recording session
            schedule: Recording schedule configuration
            stream_config: Stream configuration
            
        Returns:
            RecordingSessionManager instance
        """
        try:
            self.logger.info(f"Starting recording session {session_id}")
            
            # Log workflow start
            if self.logging_service:
                from .logging_service import OperationType, LogLevel
                self.logging_service.log_operation(
                    OperationType.RECORDING,
                    f"Starting recording workflow for session {session_id}",
                    LogLevel.INFO,
                    context={
                        'session_id': session_id,
                        'schedule_id': schedule.id,
                        'stream_url': stream_config.stream_url,
                        'duration_minutes': schedule.duration_minutes
                    }
                )
            
            # Create recording session manager
            recording_manager = RecordingSessionManager(
                session_id=session_id,
                stream_config=stream_config,
                duration_minutes=schedule.duration_minutes,
                output_directory=config.RECORDINGS_DIR
            )
            
            # Set completion callback
            recording_manager.set_completion_callback(
                lambda session_id, success, output_file: self._handle_recording_completion(
                    session_id, success, output_file
                )
            )
            
            # Set progress callback for real-time updates
            recording_manager.set_progress_callback(
                lambda session_id, stage, progress: self._handle_recording_progress(
                    session_id, stage, progress
                )
            )
            
            # Start the recording workflow
            recording_manager.start_recording()
            
            # Track active session
            with self._sessions_lock:
                self.active_sessions[session_id] = recording_manager
            
            return recording_manager
            
        except Exception as e:
            self.logger.error(f"Failed to start recording session {session_id}: {e}")
            
            # Update session status to failed
            try:
                session = self.session_repo.get_by_id(session_id)
                if session:
                    session.status = RecordingStatus.FAILED
                    session.error_message = str(e)
                    session.end_time = datetime.now()
                    self.session_repo.update(session)
            except Exception as update_error:
                self.logger.error(f"Failed to update session status: {update_error}")
            
            raise
    
    def _handle_recording_completion(
        self, 
        session_id: int, 
        success: bool, 
        output_file: Optional[str]
    ):
        """
        Handle completion of a recording session.
        
        Args:
            session_id: Session ID that completed
            success: Whether recording was successful
            output_file: Path to output file if successful
        """
        try:
            self.logger.info(f"Recording session {session_id} completed: success={success}")
            
            # Remove from active sessions
            with self._sessions_lock:
                self.active_sessions.pop(session_id, None)
            
            # Update session in database
            session = self.session_repo.get_by_id(session_id)
            if session:
                session.end_time = datetime.now()
                
                if success and output_file:
                    session.status = RecordingStatus.COMPLETED
                    session.output_file_path = output_file
                    
                    # Get file size
                    try:
                        import os
                        session.file_size_bytes = os.path.getsize(output_file)
                    except Exception:
                        pass
                    
                    # Queue for transfer
                    self._queue_for_transfer(session_id, output_file)
                    
                else:
                    session.status = RecordingStatus.FAILED
                    if hasattr(session, 'error_message') and not session.error_message:
                        session.error_message = "Recording failed without specific error"
                
                self.session_repo.update(session)
            
            # Log completion
            if self.logging_service:
                from .logging_service import OperationType, LogLevel
                log_level = LogLevel.INFO if success else LogLevel.ERROR
                self.logging_service.log_operation(
                    OperationType.RECORDING,
                    f"Recording session {session_id} completed",
                    log_level,
                    context={
                        'session_id': session_id,
                        'success': success,
                        'output_file': output_file,
                        'file_size_bytes': session.file_size_bytes if session else None
                    }
                )
            
        except Exception as e:
            self.logger.error(f"Error handling recording completion for session {session_id}: {e}")
    
    def _handle_recording_progress(self, session_id: int, stage: str, progress: Dict[str, Any]):
        """
        Handle recording progress updates.
        
        Args:
            session_id: Session ID
            stage: Current workflow stage
            progress: Progress information
        """
        try:
            # Log progress for monitoring
            if self.logging_service:
                from .logging_service import OperationType, LogLevel
                self.logging_service.log_operation(
                    OperationType.RECORDING,
                    f"Recording session {session_id} progress update",
                    LogLevel.DEBUG,
                    context={
                        'session_id': session_id,
                        'stage': stage,
                        'progress': progress
                    }
                )
            
        except Exception as e:
            self.logger.error(f"Error handling progress update for session {session_id}: {e}")
    
    def _queue_for_transfer(self, session_id: int, output_file: str):
        """
        Queue completed recording for file transfer.
        
        Args:
            session_id: Session ID
            output_file: Path to output file
        """
        try:
            # Get session and stream configuration for transfer details
            session = self.session_repo.get_by_id(session_id)
            if not session:
                self.logger.error(f"Session {session_id} not found for transfer")
                return
            
            # Get schedule to get stream configuration
            from ..models.repositories import ScheduleRepository
            schedule_repo = ScheduleRepository()
            schedule = schedule_repo.get_by_id(session.schedule_id)
            if not schedule:
                self.logger.error(f"Schedule {session.schedule_id} not found for transfer")
                return
            
            stream_config = self.config_repo.get_by_id(schedule.stream_config_id)
            if not stream_config:
                self.logger.error(f"Stream config {schedule.stream_config_id} not found for transfer")
                return
            
            # Queue for transfer
            self.transfer_queue.add_transfer(
                session_id=session_id,
                local_file_path=output_file,
                remote_destination=stream_config.scp_destination,
                stream_config=stream_config
            )
            
            self.logger.info(f"Queued session {session_id} for transfer")
            
        except Exception as e:
            self.logger.error(f"Failed to queue session {session_id} for transfer: {e}")
    
    def _handle_session_completion(self, session_id: int):
        """
        Handle session completion notification from scheduler.
        
        Args:
            session_id: Completed session ID
        """
        # This is called by scheduler when a session should be completed
        # (e.g., when duration is reached)
        try:
            with self._sessions_lock:
                recording_manager = self.active_sessions.get(session_id)
                if recording_manager:
                    recording_manager.stop_recording()
                    
        except Exception as e:
            self.logger.error(f"Error handling session completion for {session_id}: {e}")
    
    def get_active_sessions(self) -> Dict[int, Dict[str, Any]]:
        """
        Get information about active recording sessions.
        
        Returns:
            Dictionary of session info keyed by session ID
        """
        active_info = {}
        
        with self._sessions_lock:
            for session_id, manager in self.active_sessions.items():
                try:
                    active_info[session_id] = {
                        'session_id': session_id,
                        'status': manager.get_status(),
                        'progress': manager.get_progress(),
                        'start_time': manager.start_time if hasattr(manager, 'start_time') else None
                    }
                except Exception as e:
                    self.logger.error(f"Error getting info for session {session_id}: {e}")
                    active_info[session_id] = {
                        'session_id': session_id,
                        'status': 'error',
                        'error': str(e)
                    }
        
        return active_info
    
    def stop_session(self, session_id: int) -> bool:
        """
        Stop an active recording session.
        
        Args:
            session_id: Session ID to stop
            
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            with self._sessions_lock:
                recording_manager = self.active_sessions.get(session_id)
                if recording_manager:
                    recording_manager.stop_recording()
                    return True
                else:
                    self.logger.warning(f"Session {session_id} not found in active sessions")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error stopping session {session_id}: {e}")
            return False
    
    def stop_all_sessions(self):
        """Stop all active recording sessions."""
        try:
            with self._sessions_lock:
                session_ids = list(self.active_sessions.keys())
            
            for session_id in session_ids:
                self.stop_session(session_id)
                
            self.logger.info(f"Stopped {len(session_ids)} active sessions")
            
        except Exception as e:
            self.logger.error(f"Error stopping all sessions: {e}")
    
    def check_and_create_automatic_backup(self):
        """
        Check if automatic backup is needed and create one if necessary.
        Called periodically to maintain configuration backups.
        """
        try:
            current_time = datetime.utcnow()
            
            # Check if backup is needed
            if (self._last_backup_time is None or 
                (current_time - self._last_backup_time).total_seconds() > (self._backup_interval_hours * 3600)):
                
                self.logger.info("Creating automatic configuration backup")
                
                # Create automatic backup
                backup_result = self.backup_service.create_automatic_backup()
                
                if backup_result and backup_result.get('success'):
                    self._last_backup_time = current_time
                    self.logger.info(f"Automatic backup created: {backup_result.get('backup_filename')}")
                    
                    # Log backup creation
                    if self.logging_service:
                        from .logging_service import OperationType, LogLevel
                        self.logging_service.log_operation(
                            OperationType.SYSTEM,
                            f"Automatic configuration backup created: {backup_result.get('backup_filename')}",
                            LogLevel.INFO,
                            context={
                                'backup_filename': backup_result.get('backup_filename'),
                                'streams_count': backup_result.get('streams_count', 0),
                                'schedules_count': backup_result.get('schedules_count', 0),
                                'file_size_bytes': backup_result.get('file_size_bytes', 0)
                            }
                        )
                else:
                    self.logger.error(f"Failed to create automatic backup: {backup_result.get('error') if backup_result else 'Unknown error'}")
                    
        except Exception as e:
            self.logger.error(f"Error during automatic backup check: {e}")
    
    def create_manual_backup(self, backup_name: Optional[str] = None, include_artwork: bool = True) -> Dict[str, Any]:
        """
        Create a manual configuration backup.
        
        Args:
            backup_name: Optional custom name for the backup
            include_artwork: Whether to include artwork files
            
        Returns:
            Backup result dictionary
        """
        try:
            self.logger.info(f"Creating manual configuration backup: {backup_name or 'auto-named'}")
            
            backup_result = self.backup_service.create_backup(
                backup_name=backup_name,
                include_artwork=include_artwork
            )
            
            if backup_result.get('success'):
                # Log backup creation
                if self.logging_service:
                    from .logging_service import OperationType, LogLevel
                    self.logging_service.log_operation(
                        OperationType.SYSTEM,
                        f"Manual configuration backup created: {backup_result.get('backup_filename')}",
                        LogLevel.INFO,
                        context={
                            'backup_filename': backup_result.get('backup_filename'),
                            'backup_name': backup_name,
                            'include_artwork': include_artwork,
                            'streams_count': backup_result.get('streams_count', 0),
                            'schedules_count': backup_result.get('schedules_count', 0),
                            'file_size_bytes': backup_result.get('file_size_bytes', 0)
                        }
                    )
            
            return backup_result
            
        except Exception as e:
            self.logger.error(f"Error creating manual backup: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def restore_configuration_backup(self, backup_filename: str, overwrite_existing: bool = False) -> Dict[str, Any]:
        """
        Restore configuration from a backup file.
        
        Args:
            backup_filename: Name of the backup file to restore
            overwrite_existing: Whether to overwrite existing configurations
            
        Returns:
            Restore result dictionary
        """
        try:
            self.logger.info(f"Restoring configuration from backup: {backup_filename}")
            
            restore_result = self.backup_service.restore_backup(
                backup_filename=backup_filename,
                overwrite_existing=overwrite_existing
            )
            
            if restore_result.get('success'):
                # Log restore operation
                if self.logging_service:
                    from .logging_service import OperationType, LogLevel
                    self.logging_service.log_operation(
                        OperationType.SYSTEM,
                        f"Configuration restored from backup: {backup_filename}",
                        LogLevel.INFO,
                        context={
                            'backup_filename': backup_filename,
                            'overwrite_existing': overwrite_existing,
                            'streams_restored': restore_result.get('streams_restored', 0),
                            'schedules_restored': restore_result.get('schedules_restored', 0),
                            'streams_skipped': restore_result.get('streams_skipped', 0),
                            'schedules_skipped': restore_result.get('schedules_skipped', 0),
                            'errors': restore_result.get('errors', [])
                        }
                    )
                
                # Refresh scheduler with new configurations
                self.scheduler_service.refresh_schedules()
            
            return restore_result
            
        except Exception as e:
            self.logger.error(f"Error restoring backup: {e}")
            return {
                'success': False,
                'error': str(e)
            }