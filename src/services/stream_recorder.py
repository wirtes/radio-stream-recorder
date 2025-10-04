"""
StreamRecorder class for audio stream capture using FFmpeg.
Supports multiple streaming protocols and provides validation and connection testing.
"""

import subprocess
import threading
import time
import logging
import os
import signal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from enum import Enum
import requests
from urllib.parse import urlparse

from ..config import config


class RecordingStatus(Enum):
    """Recording status enumeration."""
    IDLE = "idle"
    CONNECTING = "connecting"
    RECORDING = "recording"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"


class StreamRecorder:
    """
    FFmpeg-based stream recorder with support for multiple protocols.
    Handles stream validation, connection testing, and duration limits.
    """
    
    def __init__(self, stream_url: str, output_path: str, duration_minutes: Optional[int] = None):
        """
        Initialize StreamRecorder.
        
        Args:
            stream_url: URL of the audio stream to record
            output_path: Path where the recorded file will be saved
            duration_minutes: Maximum recording duration in minutes (None for unlimited)
        """
        self.stream_url = stream_url
        self.output_path = output_path
        self.duration_minutes = duration_minutes
        self.status = RecordingStatus.IDLE
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.process: Optional[subprocess.Popen] = None
        self.recording_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.error_message: Optional[str] = None
        self.bytes_recorded: int = 0
        
        # Callbacks for status updates
        self.status_callback: Optional[Callable[[RecordingStatus, Dict[str, Any]], None]] = None
        
        # Logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    def set_status_callback(self, callback: Callable[[RecordingStatus, Dict[str, Any]], None]) -> None:
        """Set callback function for status updates."""
        self.status_callback = callback
    
    def _update_status(self, status: RecordingStatus, extra_data: Optional[Dict[str, Any]] = None) -> None:
        """Update recording status and notify callback."""
        self.status = status
        self.logger.info(f"Recording status changed to: {status.value}")
        
        if self.status_callback:
            data = {
                'status': status.value,
                'stream_url': self.stream_url,
                'output_path': self.output_path,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'error_message': self.error_message,
                'bytes_recorded': self.bytes_recorded
            }
            if extra_data:
                data.update(extra_data)
            
            try:
                self.status_callback(status, data)
            except Exception as e:
                self.logger.error(f"Error in status callback: {e}")
    
    def validate_stream_url(self) -> bool:
        """
        Validate stream URL format and basic connectivity.
        
        Returns:
            True if URL is valid and accessible, False otherwise
        """
        try:
            parsed_url = urlparse(self.stream_url)
            
            # Check protocol support
            supported_protocols = ['http', 'https', 'rtmp', 'rtmps']
            if parsed_url.scheme.lower() not in supported_protocols:
                self.error_message = f"Unsupported protocol: {parsed_url.scheme}"
                return False
            
            # For HTTP/HTTPS streams, test connectivity
            if parsed_url.scheme.lower() in ['http', 'https']:
                return self._test_http_stream()
            
            # For RTMP streams, we'll rely on FFmpeg to validate
            elif parsed_url.scheme.lower() in ['rtmp', 'rtmps']:
                return self._test_rtmp_stream()
            
            return True
            
        except Exception as e:
            self.error_message = f"URL validation error: {str(e)}"
            self.logger.error(self.error_message)
            return False
    
    def _test_http_stream(self) -> bool:
        """Test HTTP/HTTPS stream connectivity."""
        try:
            # Send HEAD request to test connectivity
            response = requests.head(
                self.stream_url,
                timeout=10,
                allow_redirects=True,
                headers={'User-Agent': 'AudioStreamRecorder/1.0'}
            )
            
            if response.status_code == 200:
                # Check if it's an audio stream
                content_type = response.headers.get('content-type', '').lower()
                audio_types = ['audio/', 'application/ogg', 'video/mp2t']
                
                if any(audio_type in content_type for audio_type in audio_types):
                    return True
                else:
                    self.logger.warning(f"Content type may not be audio: {content_type}")
                    return True  # Still allow, FFmpeg might handle it
            else:
                self.error_message = f"HTTP error: {response.status_code}"
                return False
                
        except requests.exceptions.RequestException as e:
            self.error_message = f"Connection test failed: {str(e)}"
            self.logger.error(self.error_message)
            return False
    
    def _test_rtmp_stream(self) -> bool:
        """Test RTMP stream connectivity using FFmpeg probe."""
        try:
            # Use FFprobe to test RTMP stream
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_streams',
                '-analyzeduration', '5000000',  # 5 seconds
                '-probesize', '5000000',
                self.stream_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                return True
            else:
                self.error_message = f"RTMP stream test failed: {result.stderr}"
                return False
                
        except subprocess.TimeoutExpired:
            self.error_message = "RTMP stream test timed out"
            return False
        except Exception as e:
            self.error_message = f"RTMP test error: {str(e)}"
            return False
    
    def test_stream_connection(self, stream_url: str) -> dict:
        """
        Test a stream URL connection without creating a full recorder instance.
        
        Args:
            stream_url: The stream URL to test
            
        Returns:
            Dictionary with test results
        """
        try:
            # Temporarily set the stream URL for testing
            original_url = self.stream_url
            self.stream_url = stream_url
            
            # Run validation
            is_valid = self.validate_stream_url()
            
            # Restore original URL
            self.stream_url = original_url
            
            if is_valid:
                return {
                    'success': True,
                    'message': 'Stream URL is valid and accessible'
                }
            else:
                return {
                    'success': False,
                    'message': self.error_message or 'Stream URL validation failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Test failed: {str(e)}'
            }
    
    def start_recording(self) -> bool:
        """
        Start recording the audio stream.
        
        Returns:
            True if recording started successfully, False otherwise
        """
        if self.status != RecordingStatus.IDLE:
            self.error_message = f"Cannot start recording, current status: {self.status.value}"
            return False
        
        # Validate stream before starting
        self._update_status(RecordingStatus.CONNECTING)
        
        if not self.validate_stream_url():
            self._update_status(RecordingStatus.FAILED)
            return False
        
        # Start recording in a separate thread
        self.recording_thread = threading.Thread(target=self._record_stream)
        self.recording_thread.daemon = True
        self.recording_thread.start()
        
        return True
    
    def _record_stream(self) -> None:
        """Internal method to handle the recording process."""
        try:
            self.start_time = datetime.now()
            self._update_status(RecordingStatus.RECORDING)
            
            # Build FFmpeg command
            cmd = self._build_ffmpeg_command()
            self.logger.info(f"Starting FFmpeg with command: {' '.join(cmd)}")
            
            # Start FFmpeg process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid  # Create new process group for clean termination
            )
            
            # Monitor the recording process
            self._monitor_recording()
            
        except Exception as e:
            self.error_message = f"Recording error: {str(e)}"
            self.logger.error(self.error_message)
            self._update_status(RecordingStatus.FAILED)
    
    def _build_ffmpeg_command(self) -> list:
        """Build FFmpeg command for recording."""
        cmd = [
            config.FFMPEG_PATH,
            '-y',  # Overwrite output file
            '-i', self.stream_url,
            '-acodec', 'libmp3lame',  # Use MP3 encoder for audio
            '-ab', '128k',  # Audio bitrate
            '-f', 'mp3',   # Force MP3 output format
        ]
        
        # Add duration limit if specified
        if self.duration_minutes:
            duration_seconds = self.duration_minutes * 60
            cmd.extend(['-t', str(duration_seconds)])
        
        # Add output file
        cmd.append(self.output_path)
        
        return cmd
    
    def _monitor_recording(self) -> None:
        """Monitor the recording process and handle duration limits."""
        if not self.process:
            return
        
        # Calculate end time if duration is specified
        end_time = None
        if self.duration_minutes:
            end_time = self.start_time + timedelta(minutes=self.duration_minutes)
        
        # Monitor process
        while self.process.poll() is None:
            # Check if we should stop
            if self.stop_event.is_set():
                self.logger.info("Stop event received, terminating recording")
                self._terminate_process()
                break
            
            # Check duration limit
            if end_time and datetime.now() >= end_time:
                self.logger.info("Duration limit reached, stopping recording")
                self._terminate_process()
                break
            
            # Update file size if file exists
            if os.path.exists(self.output_path):
                try:
                    self.bytes_recorded = os.path.getsize(self.output_path)
                except OSError:
                    pass
            
            # Sleep briefly before next check
            time.sleep(1)
        
        # Process has finished
        return_code = self.process.returncode
        stderr_output = self.process.stderr.read() if self.process.stderr else ""
        
        self.end_time = datetime.now()
        
        if return_code == 0:
            self.logger.info("Recording completed successfully")
            self._update_status(RecordingStatus.COMPLETED)
        else:
            self.error_message = f"FFmpeg failed with return code {return_code}: {stderr_output}"
            self.logger.error(self.error_message)
            self._update_status(RecordingStatus.FAILED)
    
    def _terminate_process(self) -> None:
        """Terminate the FFmpeg process gracefully."""
        if self.process and self.process.poll() is None:
            try:
                # Send SIGTERM to the process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Wait for graceful termination
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.logger.warning("FFmpeg didn't terminate gracefully, force killing")
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                    
            except Exception as e:
                self.logger.error(f"Error terminating FFmpeg process: {e}")
    
    def stop_recording(self) -> bool:
        """
        Stop the recording process.
        
        Returns:
            True if stop was initiated successfully, False otherwise
        """
        if self.status not in [RecordingStatus.CONNECTING, RecordingStatus.RECORDING]:
            self.error_message = f"Cannot stop recording, current status: {self.status.value}"
            return False
        
        self._update_status(RecordingStatus.STOPPING)
        self.stop_event.set()
        
        # Wait for recording thread to finish
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=10)
            
            if self.recording_thread.is_alive():
                self.logger.warning("Recording thread didn't finish within timeout")
        
        return True
    
    def get_recording_info(self) -> Dict[str, Any]:
        """
        Get current recording information.
        
        Returns:
            Dictionary with recording status and metadata
        """
        duration = None
        if self.start_time:
            end = self.end_time or datetime.now()
            duration = (end - self.start_time).total_seconds()
        
        return {
            'status': self.status.value,
            'stream_url': self.stream_url,
            'output_path': self.output_path,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': duration,
            'duration_minutes_limit': self.duration_minutes,
            'bytes_recorded': self.bytes_recorded,
            'error_message': self.error_message
        }
    
    def cleanup(self) -> None:
        """Clean up resources and stop recording if active."""
        if self.status in [RecordingStatus.CONNECTING, RecordingStatus.RECORDING]:
            self.stop_recording()
        
        # Clean up process
        if self.process:
            try:
                if self.process.poll() is None:
                    self._terminate_process()
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
            finally:
                self.process = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()