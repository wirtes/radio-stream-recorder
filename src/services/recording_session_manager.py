"""
RecordingSession manager for workflow orchestration.
Handles the complete recording workflow: capture → process → transfer.
"""

import os
import logging
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from enum import Enum
from pathlib import Path

from .stream_recorder import StreamRecorder, RecordingStatus as StreamRecordingStatus
from .audio_processor import AudioProcessor
from ..models.stream_configuration import StreamConfiguration
from ..models.recording_session import RecordingSession, RecordingStatus
from ..config import config


class WorkflowStage(Enum):
    """Workflow stage enumeration."""
    INITIALIZING = "initializing"
    RECORDING = "recording"
    PROCESSING = "processing"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecordingSessionManager:
    """
    Manager for complete recording workflow orchestration.
    Handles capture, processing, and transfer with error handling and retry logic.
    """
    
    def __init__(
        self,
        session_id: int,
        stream_config: StreamConfiguration,
        duration_minutes: int,
        output_directory: Optional[str] = None
    ):
        """
        Initialize RecordingSessionManager.
        
        Args:
            session_id: Database ID of the recording session
            stream_config: Stream configuration object
            duration_minutes: Recording duration in minutes
            output_directory: Custom output directory (defaults to config.RECORDINGS_DIR)
        """
        self.session_id = session_id
        self.stream_config = stream_config
        self.duration_minutes = duration_minutes
        self.output_directory = output_directory or config.RECORDINGS_DIR
        
        # Workflow state
        self.current_stage = WorkflowStage.INITIALIZING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.retry_count = 0
        self.max_retries = config.DEFAULT_MAX_RETRIES
        
        # File paths
        self.raw_recording_path: Optional[str] = None
        self.processed_mp3_path: Optional[str] = None
        
        # Components
        self.stream_recorder: Optional[StreamRecorder] = None
        self.audio_processor = AudioProcessor()
        
        # Threading
        self.workflow_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # Callbacks
        self.status_callback: Optional[Callable[[WorkflowStage, Dict[str, Any]], None]] = None
        self.progress_callback: Optional[Callable[[str, float], None]] = None
        
        # Logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Ensure output directory exists
        os.makedirs(self.output_directory, exist_ok=True)
    
    def set_status_callback(self, callback: Callable[[WorkflowStage, Dict[str, Any]], None]) -> None:
        """Set callback function for status updates."""
        self.status_callback = callback
    
    def set_progress_callback(self, callback: Callable[[str, float], None]) -> None:
        """Set callback function for progress updates."""
        self.progress_callback = callback
    
    def _update_status(self, stage: WorkflowStage, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Update workflow stage and notify callback."""
        with self._lock:
            self.current_stage = stage
            self.logger.info(f"Recording session {self.session_id} stage changed to: {stage.value}")
            
            if self.status_callback:
                data = {
                    'session_id': self.session_id,
                    'stage': stage.value,
                    'stream_name': self.stream_config.name,
                    'start_time': self.start_time,
                    'end_time': self.end_time,
                    'error_message': self.error_message,
                    'retry_count': self.retry_count,
                    'raw_recording_path': self.raw_recording_path,
                    'processed_mp3_path': self.processed_mp3_path
                }
                if extra_data:
                    data.update(extra_data)
                
                try:
                    self.status_callback(stage, data)
                except Exception as e:
                    self.logger.error(f"Error in status callback: {e}")
    
    def _update_progress(self, operation: str, progress: float) -> None:
        """Update progress and notify callback."""
        if self.progress_callback:
            try:
                self.progress_callback(operation, progress)
            except Exception as e:
                self.logger.error(f"Error in progress callback: {e}")
    
    def start_recording(self) -> bool:
        """
        Start the complete recording workflow.
        
        Returns:
            True if workflow started successfully, False otherwise
        """
        if self.current_stage != WorkflowStage.INITIALIZING:
            self.error_message = f"Cannot start recording, current stage: {self.current_stage.value}"
            return False
        
        # Generate file paths
        self._generate_file_paths()
        
        # Start workflow in separate thread
        self.workflow_thread = threading.Thread(target=self._run_workflow)
        self.workflow_thread.daemon = True
        self.workflow_thread.start()
        
        return True
    
    def _generate_file_paths(self) -> None:
        """Generate file paths for recording and processing."""
        from ..utils.timezone_utils import get_local_timestamp_string, get_local_date_string
        
        timestamp = get_local_timestamp_string()
        base_filename = f"{self.stream_config.name}_{timestamp}"
        
        # Raw recording path (temporary)
        self.raw_recording_path = os.path.join(
            self.output_directory,
            f"{base_filename}_raw.mp3"
        )
        
        # Final processed MP3 path
        filename_pattern = self.stream_config.output_filename_pattern
        final_filename = filename_pattern.format(
            date=get_local_date_string(),
            name=self.stream_config.name,
            timestamp=timestamp
        )
        
        self.processed_mp3_path = os.path.join(
            self.output_directory,
            final_filename
        )
    
    def _run_workflow(self) -> None:
        """Run the complete recording workflow."""
        try:
            from ..utils.timezone_utils import get_local_now
            self.start_time = get_local_now()
            
            # Stage 1: Recording
            if not self._execute_recording_stage():
                return
            
            # Check if cancelled
            if self.stop_event.is_set():
                self._update_status(WorkflowStage.CANCELLED)
                return
            
            # Stage 2: Processing
            if not self._execute_processing_stage():
                return
            
            # Check if cancelled
            if self.stop_event.is_set():
                self._update_status(WorkflowStage.CANCELLED)
                return
            
            # Stage 3: Transfer (placeholder - will be implemented in task 4)
            if not self._execute_transfer_stage():
                return
            
            # Workflow completed successfully
            from ..utils.timezone_utils import get_local_now
            self.end_time = get_local_now()
            self._update_status(WorkflowStage.COMPLETED)
            
            # Cleanup temporary files
            self._cleanup_temporary_files()
            
        except Exception as e:
            self.error_message = f"Workflow error: {str(e)}"
            self.logger.error(self.error_message, exc_info=True)
            self._update_status(WorkflowStage.FAILED)
    
    def _execute_recording_stage(self) -> bool:
        """Execute the recording stage."""
        self._update_status(WorkflowStage.RECORDING)
        self._update_progress("Recording audio stream", 0.0)
        
        try:
            # Create stream recorder
            self.stream_recorder = StreamRecorder(
                stream_url=self.stream_config.stream_url,
                output_path=self.raw_recording_path,
                duration_minutes=self.duration_minutes
            )
            
            # Set up recorder status callback
            def recorder_status_callback(status: StreamRecordingStatus, data: Dict[str, Any]):
                if status == StreamRecordingStatus.RECORDING:
                    # Update progress based on time elapsed
                    if self.duration_minutes and data.get('start_time'):
                        start_time_data = data['start_time']
                        if isinstance(start_time_data, str):
                            start_time = datetime.fromisoformat(start_time_data)
                        else:
                            start_time = start_time_data  # Already a datetime object
                        
                        from ..utils.timezone_utils import get_local_now
                        elapsed_minutes = (get_local_now() - start_time).total_seconds() / 60
                        progress = min(elapsed_minutes / self.duration_minutes, 1.0)
                        self._update_progress("Recording audio stream", progress * 100)
            
            self.stream_recorder.set_status_callback(recorder_status_callback)
            
            # Start recording
            if not self.stream_recorder.start_recording():
                self.error_message = f"Failed to start recording: {self.stream_recorder.error_message}"
                self._update_status(WorkflowStage.FAILED)
                return False
            
            # Wait for recording to complete
            while (self.stream_recorder.status in 
                   [StreamRecordingStatus.CONNECTING, StreamRecordingStatus.RECORDING]):
                
                if self.stop_event.is_set():
                    self.stream_recorder.stop_recording()
                    break
                
                time.sleep(1)
            
            # Check recording result
            if self.stream_recorder.status == StreamRecordingStatus.COMPLETED:
                self._update_progress("Recording audio stream", 100.0)
                self.logger.info(f"Recording completed successfully: {self.raw_recording_path}")
                return True
            else:
                self.error_message = f"Recording failed: {self.stream_recorder.error_message}"
                self._update_status(WorkflowStage.FAILED)
                return False
                
        except Exception as e:
            self.error_message = f"Recording stage error: {str(e)}"
            self.logger.error(self.error_message, exc_info=True)
            self._update_status(WorkflowStage.FAILED)
            return False
    
    def _execute_processing_stage(self) -> bool:
        """Execute the audio processing stage."""
        self._update_status(WorkflowStage.PROCESSING)
        self._update_progress("Processing audio file", 0.0)
        
        try:
            # Prepare metadata
            metadata = {
                'name': self.stream_config.name,
                'artist': self.stream_config.artist,
                'album': self.stream_config.album,
                'album_artist': self.stream_config.album_artist
            }
            
            # Process audio file
            self._update_progress("Processing audio file", 25.0)
            
            success = self.audio_processor.process_audio_file(
                input_path=self.raw_recording_path,
                output_path=self.processed_mp3_path,
                metadata=metadata,
                artwork_path=self.stream_config.artwork_path,
                recording_date=self.start_time
            )
            
            if success:
                self._update_progress("Processing audio file", 100.0)
                self.logger.info(f"Audio processing completed: {self.processed_mp3_path}")
                return True
            else:
                self.error_message = "Audio processing failed"
                self._update_status(WorkflowStage.FAILED)
                return False
                
        except Exception as e:
            self.error_message = f"Processing stage error: {str(e)}"
            self.logger.error(self.error_message, exc_info=True)
            self._update_status(WorkflowStage.FAILED)
            return False
    
    def _execute_transfer_stage(self) -> bool:
        """Execute the file transfer stage using SCP."""
        self._update_status(WorkflowStage.TRANSFERRING)
        self._update_progress("Transferring file", 0.0)
        
        try:
            self.logger.info(f"Transfer stage - file ready: {self.processed_mp3_path}")
            self.logger.info(f"SCP destination: {self.stream_config.scp_destination}")
            
            # Import SCP transfer service
            from .scp_transfer_service import SCPTransferService
            scp_service = SCPTransferService()
            
            # Progress callback for transfer updates
            def progress_callback(transferred: int, total: int):
                if total > 0:
                    progress = (transferred / total) * 100
                    self._update_progress("Transferring file", progress)
            
            # Perform SCP transfer
            result = scp_service.transfer_file(
                local_path=self.processed_mp3_path,
                scp_destination=self.stream_config.scp_destination,
                progress_callback=progress_callback
            )
            
            if result and result.success:
                self.logger.info(f"Transfer completed successfully to {self.stream_config.scp_destination}")
                self._update_progress("Transferring file", 100.0)
                return True
            else:
                error_msg = result.error_message if result else "Unknown transfer error"
                self.error_message = f"Transfer failed: {error_msg}"
                self.logger.error(self.error_message)
                return False
            
        except Exception as e:
            self.error_message = f"Transfer stage error: {str(e)}"
            self.logger.error(self.error_message, exc_info=True)
            self._update_status(WorkflowStage.FAILED)
            return False
    
    def _cleanup_temporary_files(self) -> None:
        """Clean up temporary files after successful workflow."""
        try:
            # Remove raw recording file if it exists and is different from processed file
            if (self.raw_recording_path and 
                os.path.exists(self.raw_recording_path) and 
                self.raw_recording_path != self.processed_mp3_path):
                
                os.remove(self.raw_recording_path)
                self.logger.info(f"Cleaned up temporary file: {self.raw_recording_path}")
                
        except Exception as e:
            self.logger.warning(f"Error cleaning up temporary files: {e}")
    
    def stop_recording(self) -> bool:
        """
        Stop the recording workflow.
        
        Returns:
            True if stop was initiated successfully, False otherwise
        """
        if self.current_stage in [WorkflowStage.COMPLETED, WorkflowStage.FAILED, WorkflowStage.CANCELLED]:
            return False
        
        self.logger.info(f"Stopping recording session {self.session_id}")
        self.stop_event.set()
        
        # Stop stream recorder if active
        if self.stream_recorder:
            self.stream_recorder.stop_recording()
        
        # Wait for workflow thread to finish
        if self.workflow_thread and self.workflow_thread.is_alive():
            self.workflow_thread.join(timeout=10)
            
            if self.workflow_thread.is_alive():
                self.logger.warning("Workflow thread didn't finish within timeout")
        
        return True
    
    def retry_workflow(self) -> bool:
        """
        Retry the workflow from the beginning.
        
        Returns:
            True if retry was initiated successfully, False otherwise
        """
        if self.retry_count >= self.max_retries:
            self.error_message = f"Maximum retries ({self.max_retries}) exceeded"
            return False
        
        if self.current_stage not in [WorkflowStage.FAILED]:
            self.error_message = f"Cannot retry, current stage: {self.current_stage.value}"
            return False
        
        self.retry_count += 1
        self.logger.info(f"Retrying recording session {self.session_id} (attempt {self.retry_count})")
        
        # Reset state
        self.current_stage = WorkflowStage.INITIALIZING
        self.error_message = None
        self.stop_event.clear()
        
        # Clean up previous attempt
        self._cleanup_failed_attempt()
        
        # Generate new file paths
        self._generate_file_paths()
        
        # Start workflow again
        return self.start_recording()
    
    def _cleanup_failed_attempt(self) -> None:
        """Clean up files from failed attempt."""
        try:
            files_to_clean = [self.raw_recording_path, self.processed_mp3_path]
            
            for file_path in files_to_clean:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    self.logger.info(f"Cleaned up failed attempt file: {file_path}")
                    
        except Exception as e:
            self.logger.warning(f"Error cleaning up failed attempt: {e}")
    
    def get_session_info(self) -> Dict[str, Any]:
        """
        Get current session information.
        
        Returns:
            Dictionary with session status and metadata
        """
        with self._lock:
            duration = None
            if self.start_time:
                end = self.end_time or datetime.now()
                duration = (end - self.start_time).total_seconds()
            
            # Get file sizes
            raw_file_size = 0
            processed_file_size = 0
            
            if self.raw_recording_path and os.path.exists(self.raw_recording_path):
                try:
                    raw_file_size = os.path.getsize(self.raw_recording_path)
                except OSError:
                    pass
            
            if self.processed_mp3_path and os.path.exists(self.processed_mp3_path):
                try:
                    processed_file_size = os.path.getsize(self.processed_mp3_path)
                except OSError:
                    pass
            
            return {
                'session_id': self.session_id,
                'stage': self.current_stage.value,
                'stream_name': self.stream_config.name,
                'stream_url': self.stream_config.stream_url,
                'duration_minutes': self.duration_minutes,
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat() if self.end_time else None,
                'duration_seconds': duration,
                'retry_count': self.retry_count,
                'max_retries': self.max_retries,
                'error_message': self.error_message,
                'raw_recording_path': self.raw_recording_path,
                'processed_mp3_path': self.processed_mp3_path,
                'raw_file_size_bytes': raw_file_size,
                'processed_file_size_bytes': processed_file_size
            }
    
    def cleanup(self) -> None:
        """Clean up resources and stop recording if active."""
        if self.current_stage in [WorkflowStage.RECORDING, WorkflowStage.PROCESSING, WorkflowStage.TRANSFERRING]:
            self.stop_recording()
        
        # Clean up stream recorder
        if self.stream_recorder:
            self.stream_recorder.cleanup()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()