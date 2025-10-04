"""
Comprehensive logging infrastructure for the audio stream recorder system.

This module provides structured logging with timestamps, operation types,
log rotation, retention policies, and persistence to host-mounted volumes.
"""

import logging
import logging.handlers
import os
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from enum import Enum


class OperationType(Enum):
    """Enumeration of system operation types for structured logging."""
    RECORDING = "recording"
    PROCESSING = "processing"
    TRANSFER = "transfer"
    SCHEDULING = "scheduling"
    WEB_REQUEST = "web_request"
    SYSTEM = "system"
    DATABASE = "database"
    CONFIGURATION = "configuration"
    ERROR = "error"


class LogLevel(Enum):
    """Log level enumeration."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add operation type if present
        if hasattr(record, 'operation_type'):
            log_entry['operation_type'] = record.operation_type
            
        # Add session ID if present
        if hasattr(record, 'session_id'):
            log_entry['session_id'] = record.session_id
            
        # Add stream ID if present
        if hasattr(record, 'stream_id'):
            log_entry['stream_id'] = record.stream_id
            
        # Add additional context if present
        if hasattr(record, 'context'):
            log_entry['context'] = record.context
            
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry, ensure_ascii=False)


class LoggingService:
    """
    Comprehensive logging service with structured logging, rotation, and persistence.
    
    Features:
    - Structured JSON logging with timestamps and operation types
    - Log rotation and retention policies
    - Multiple log levels for different system operations
    - Persistence to host-mounted volumes
    - Context-aware logging with session and stream IDs
    """
    
    def __init__(self, 
                 log_dir: str = "/app/logs",
                 log_level: str = "INFO",
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5,
                 retention_days: int = 30):
        """
        Initialize the logging service.
        
        Args:
            log_dir: Directory for log files (should be host-mounted volume)
            log_level: Default log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_file_size: Maximum size of each log file in bytes
            backup_count: Number of backup files to keep
            retention_days: Number of days to retain log files
        """
        self.log_dir = Path(log_dir)
        self.log_level = getattr(logging, log_level.upper())
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.retention_days = retention_days
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize loggers
        self._setup_loggers()
        
    def _setup_loggers(self):
        """Set up structured loggers with rotation and formatting."""
        # Create formatters
        structured_formatter = StructuredFormatter()
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Main application logger
        self.app_logger = self._create_logger(
            'audio_recorder',
            'application.log',
            structured_formatter,
            console_formatter
        )
        
        # Operation-specific loggers
        self.recording_logger = self._create_logger(
            'audio_recorder.recording',
            'recording.log',
            structured_formatter
        )
        
        self.processing_logger = self._create_logger(
            'audio_recorder.processing',
            'processing.log',
            structured_formatter
        )
        
        self.transfer_logger = self._create_logger(
            'audio_recorder.transfer',
            'transfer.log',
            structured_formatter
        )
        
        self.scheduler_logger = self._create_logger(
            'audio_recorder.scheduler',
            'scheduler.log',
            structured_formatter
        )
        
        self.web_logger = self._create_logger(
            'audio_recorder.web',
            'web.log',
            structured_formatter
        )
        
        self.system_logger = self._create_logger(
            'audio_recorder.system',
            'system.log',
            structured_formatter
        )
        
        # Error logger for all errors
        self.error_logger = self._create_logger(
            'audio_recorder.errors',
            'errors.log',
            structured_formatter,
            min_level=logging.ERROR
        )
        
    def _create_logger(self, 
                      name: str, 
                      filename: str, 
                      file_formatter: logging.Formatter,
                      console_formatter: Optional[logging.Formatter] = None,
                      min_level: Optional[int] = None) -> logging.Logger:
        """Create a logger with file and console handlers."""
        logger = logging.getLogger(name)
        logger.setLevel(min_level or self.log_level)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # File handler with rotation
        file_path = self.log_dir / filename
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(min_level or self.log_level)
        logger.addHandler(file_handler)
        
        # Console handler (only for main app logger or if console formatter provided)
        if console_formatter or name == 'audio_recorder':
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter or file_formatter)
            console_handler.setLevel(logging.INFO)  # Less verbose on console
            logger.addHandler(console_handler)
            
        # Prevent propagation to avoid duplicate logs
        logger.propagate = False
        
        return logger
        
    def log_operation(self, 
                     operation_type: OperationType,
                     message: str,
                     level: LogLevel = LogLevel.INFO,
                     session_id: Optional[str] = None,
                     stream_id: Optional[int] = None,
                     context: Optional[Dict[str, Any]] = None,
                     exc_info: Optional[bool] = None):
        """
        Log a structured operation with context.
        
        Args:
            operation_type: Type of operation being logged
            message: Log message
            level: Log level
            session_id: Recording session ID if applicable
            stream_id: Stream configuration ID if applicable
            context: Additional context dictionary
            exc_info: Include exception information
        """
        # Select appropriate logger based on operation type
        logger_map = {
            OperationType.RECORDING: self.recording_logger,
            OperationType.PROCESSING: self.processing_logger,
            OperationType.TRANSFER: self.transfer_logger,
            OperationType.SCHEDULING: self.scheduler_logger,
            OperationType.WEB_REQUEST: self.web_logger,
            OperationType.SYSTEM: self.system_logger,
            OperationType.DATABASE: self.app_logger,
            OperationType.CONFIGURATION: self.app_logger,
            OperationType.ERROR: self.error_logger
        }
        
        logger = logger_map.get(operation_type, self.app_logger)
        
        # Create log record with extra context
        extra = {
            'operation_type': operation_type.value,
        }
        
        if session_id:
            extra['session_id'] = session_id
            
        if stream_id:
            extra['stream_id'] = stream_id
            
        if context:
            extra['context'] = context
            
        # Log the message
        logger.log(level.value, message, extra=extra, exc_info=exc_info)
        
        # Also log errors to the error logger if not already an error logger
        if level in [LogLevel.ERROR, LogLevel.CRITICAL] and logger != self.error_logger:
            self.error_logger.log(level.value, message, extra=extra, exc_info=exc_info)
            
    def log_recording_start(self, session_id: str, stream_id: int, stream_url: str):
        """Log the start of a recording session."""
        self.log_operation(
            OperationType.RECORDING,
            f"Recording session started",
            LogLevel.INFO,
            session_id=session_id,
            stream_id=stream_id,
            context={'stream_url': stream_url, 'action': 'start'}
        )
        
    def log_recording_end(self, session_id: str, stream_id: int, 
                         duration_seconds: float, file_size_bytes: int):
        """Log the end of a recording session."""
        self.log_operation(
            OperationType.RECORDING,
            f"Recording session completed",
            LogLevel.INFO,
            session_id=session_id,
            stream_id=stream_id,
            context={
                'action': 'complete',
                'duration_seconds': duration_seconds,
                'file_size_bytes': file_size_bytes
            }
        )
        
    def log_recording_error(self, session_id: str, stream_id: int, error: str):
        """Log a recording error."""
        self.log_operation(
            OperationType.RECORDING,
            f"Recording session failed: {error}",
            LogLevel.ERROR,
            session_id=session_id,
            stream_id=stream_id,
            context={'action': 'error', 'error': error},
            exc_info=True
        )
        
    def log_processing_start(self, session_id: str, input_file: str):
        """Log the start of audio processing."""
        self.log_operation(
            OperationType.PROCESSING,
            f"Audio processing started",
            LogLevel.INFO,
            session_id=session_id,
            context={'input_file': input_file, 'action': 'start'}
        )
        
    def log_processing_end(self, session_id: str, output_file: str, 
                          processing_time_seconds: float):
        """Log the end of audio processing."""
        self.log_operation(
            OperationType.PROCESSING,
            f"Audio processing completed",
            LogLevel.INFO,
            session_id=session_id,
            context={
                'output_file': output_file,
                'action': 'complete',
                'processing_time_seconds': processing_time_seconds
            }
        )
        
    def log_transfer_start(self, session_id: str, file_path: str, destination: str):
        """Log the start of file transfer."""
        self.log_operation(
            OperationType.TRANSFER,
            f"File transfer started",
            LogLevel.INFO,
            session_id=session_id,
            context={
                'file_path': file_path,
                'destination': destination,
                'action': 'start'
            }
        )
        
    def log_transfer_success(self, session_id: str, file_path: str, 
                           destination: str, transfer_time_seconds: float):
        """Log successful file transfer."""
        self.log_operation(
            OperationType.TRANSFER,
            f"File transfer completed successfully",
            LogLevel.INFO,
            session_id=session_id,
            context={
                'file_path': file_path,
                'destination': destination,
                'action': 'success',
                'transfer_time_seconds': transfer_time_seconds
            }
        )
        
    def log_schedule_created(self, schedule_id: int, cron_expression: str, stream_id: int):
        """Log creation of a new recording schedule."""
        self.log_operation(
            OperationType.SCHEDULING,
            f"Recording schedule created",
            LogLevel.INFO,
            stream_id=stream_id,
            context={
                'schedule_id': schedule_id,
                'cron_expression': cron_expression,
                'action': 'create'
            }
        )
        
    def log_web_request(self, method: str, path: str, status_code: int, 
                       response_time_ms: float, user_ip: str = None):
        """Log web request."""
        self.log_operation(
            OperationType.WEB_REQUEST,
            f"{method} {path} - {status_code}",
            LogLevel.INFO,
            context={
                'method': method,
                'path': path,
                'status_code': status_code,
                'response_time_ms': response_time_ms,
                'user_ip': user_ip
            }
        )
        
    def log_system_startup(self):
        """Log system startup."""
        self.log_operation(
            OperationType.SYSTEM,
            "Audio Stream Recorder system started",
            LogLevel.INFO,
            context={'action': 'startup'}
        )
        
    def log_system_shutdown(self):
        """Log system shutdown."""
        self.log_operation(
            OperationType.SYSTEM,
            "Audio Stream Recorder system shutting down",
            LogLevel.INFO,
            context={'action': 'shutdown'}
        )
        
    def cleanup_old_logs(self):
        """Clean up log files older than retention period."""
        try:
            import time
            current_time = time.time()
            retention_seconds = self.retention_days * 24 * 60 * 60
            
            for log_file in self.log_dir.glob("*.log*"):
                if log_file.stat().st_mtime < (current_time - retention_seconds):
                    log_file.unlink()
                    self.log_operation(
                        OperationType.SYSTEM,
                        f"Cleaned up old log file: {log_file.name}",
                        LogLevel.INFO,
                        context={'action': 'cleanup', 'file': str(log_file)}
                    )
        except Exception as e:
            self.log_operation(
                OperationType.SYSTEM,
                f"Error during log cleanup: {str(e)}",
                LogLevel.ERROR,
                context={'action': 'cleanup_error'},
                exc_info=True
            )
            
    def get_recent_logs(self, operation_type: Optional[OperationType] = None, 
                       limit: int = 100) -> list:
        """
        Get recent log entries, optionally filtered by operation type.
        
        Args:
            operation_type: Filter by operation type (None for all)
            limit: Maximum number of log entries to return
            
        Returns:
            List of log entries as dictionaries
        """
        logs = []
        
        # Determine which log files to read
        if operation_type:
            log_files = {
                OperationType.RECORDING: ['recording.log'],
                OperationType.PROCESSING: ['processing.log'],
                OperationType.TRANSFER: ['transfer.log'],
                OperationType.SCHEDULING: ['scheduler.log'],
                OperationType.WEB_REQUEST: ['web.log'],
                OperationType.SYSTEM: ['system.log'],
                OperationType.ERROR: ['errors.log']
            }.get(operation_type, ['application.log'])
        else:
            log_files = ['application.log', 'recording.log', 'processing.log', 
                        'transfer.log', 'scheduler.log', 'web.log', 'system.log']
            
        # Read log entries from files
        for log_file in log_files:
            file_path = self.log_dir / log_file
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        # Get the last 'limit' lines from this file
                        for line in lines[-limit:]:
                            line = line.strip()
                            if line:
                                try:
                                    log_entry = json.loads(line)
                                    logs.append(log_entry)
                                except json.JSONDecodeError:
                                    # Skip malformed log entries
                                    continue
                except Exception as e:
                    self.log_operation(
                        OperationType.SYSTEM,
                        f"Error reading log file {log_file}: {str(e)}",
                        LogLevel.ERROR,
                        exc_info=True
                    )
                    
        # Sort by timestamp and limit results
        logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return logs[:limit]


# Global logging service instance
_logging_service: Optional[LoggingService] = None


def get_logging_service() -> LoggingService:
    """Get the global logging service instance."""
    global _logging_service
    if _logging_service is None:
        # Initialize with environment variables or defaults
        log_dir = os.getenv('LOG_DIR', '/app/logs')
        log_level = os.getenv('LOG_LEVEL', 'INFO')
        _logging_service = LoggingService(log_dir=log_dir, log_level=log_level)
    return _logging_service


def init_logging_service(log_dir: str = "/app/logs", 
                        log_level: str = "INFO") -> LoggingService:
    """Initialize the global logging service."""
    global _logging_service
    _logging_service = LoggingService(log_dir=log_dir, log_level=log_level)
    return _logging_service