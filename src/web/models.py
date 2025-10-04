"""
Pydantic models for API request/response validation.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator, HttpUrl
from enum import Enum
import re


class RecordingStatus(str, Enum):
    """Recording session status enumeration."""
    SCHEDULED = "scheduled"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TransferStatus(str, Enum):
    """File transfer status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# Stream Configuration Models
class StreamConfigurationCreate(BaseModel):
    """Model for creating a new stream configuration."""
    name: str = Field(..., min_length=1, max_length=100)
    stream_url: HttpUrl
    artist: str = Field(..., min_length=1, max_length=100)
    album: str = Field(..., min_length=1, max_length=100)
    album_artist: str = Field(..., min_length=1, max_length=100)
    output_filename_pattern: str = Field(default="{date}_{name}.mp3")
    scp_destination: str = Field(..., min_length=1)
    
    @validator('output_filename_pattern')
    def validate_filename_pattern(cls, v):
        """Validate filename pattern contains valid placeholders."""
        allowed_placeholders = ['{date}', '{name}', '{artist}', '{album}']
        # Check if pattern contains at least one valid placeholder
        if not any(placeholder in v for placeholder in allowed_placeholders):
            raise ValueError('Filename pattern must contain at least one valid placeholder: {date}, {name}, {artist}, {album}')
        return v


class StreamConfigurationUpdate(BaseModel):
    """Model for updating an existing stream configuration."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    stream_url: Optional[HttpUrl] = None
    artist: Optional[str] = Field(None, min_length=1, max_length=100)
    album: Optional[str] = Field(None, min_length=1, max_length=100)
    album_artist: Optional[str] = Field(None, min_length=1, max_length=100)
    output_filename_pattern: Optional[str] = None
    scp_destination: Optional[str] = None
    
    @validator('output_filename_pattern')
    def validate_filename_pattern(cls, v):
        """Validate filename pattern contains valid placeholders."""
        if v is not None:
            allowed_placeholders = ['{date}', '{name}', '{artist}', '{album}']
            if not any(placeholder in v for placeholder in allowed_placeholders):
                raise ValueError('Filename pattern must contain at least one valid placeholder: {date}, {name}, {artist}, {album}')
        return v


class StreamConfigurationResponse(BaseModel):
    """Model for stream configuration API responses."""
    id: int
    name: str
    stream_url: str
    artist: str
    album: str
    album_artist: str
    artwork_path: Optional[str]
    output_filename_pattern: str
    scp_destination: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Recording Schedule Models
class RecordingScheduleCreate(BaseModel):
    """Model for creating a new recording schedule."""
    stream_config_id: int = Field(..., gt=0)
    cron_expression: str = Field(..., min_length=1)
    duration_minutes: int = Field(..., gt=0, le=1440)  # Max 24 hours
    max_retries: int = Field(default=3, ge=0, le=10)
    is_active: bool = Field(default=True)
    
    @validator('cron_expression')
    def validate_cron_expression(cls, v):
        """Validate cron expression format."""
        # Basic cron validation - 5 fields separated by spaces
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError('Cron expression must have exactly 5 fields: minute hour day month weekday')
        
        # Validate each field contains valid characters
        cron_pattern = re.compile(r'^[0-9\*\-\,\/]+$')
        for part in parts:
            if not cron_pattern.match(part):
                raise ValueError('Invalid characters in cron expression')
        
        return v


class RecordingScheduleUpdate(BaseModel):
    """Model for updating an existing recording schedule."""
    cron_expression: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, gt=0, le=1440)
    is_active: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    last_run_time: Optional[datetime] = None
    
    @validator('cron_expression')
    def validate_cron_expression(cls, v):
        """Validate cron expression format."""
        if v is not None:
            parts = v.strip().split()
            if len(parts) != 5:
                raise ValueError('Cron expression must have exactly 5 fields: minute hour day month weekday')
            
            cron_pattern = re.compile(r'^[0-9\*\-\,\/]+$')
            for part in parts:
                if not cron_pattern.match(part):
                    raise ValueError('Invalid characters in cron expression')
        
        return v


class RecordingScheduleResponse(BaseModel):
    """Model for recording schedule API responses."""
    id: int
    stream_config_id: int
    cron_expression: str
    duration_minutes: int
    is_active: bool
    next_run_time: Optional[datetime]
    last_run_time: Optional[datetime]
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Recording Session Models
class RecordingSessionResponse(BaseModel):
    """Model for recording session API responses."""
    id: int
    schedule_id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: RecordingStatus
    output_file_path: Optional[str]
    error_message: Optional[str]
    file_size_bytes: Optional[int]
    transfer_status: TransferStatus
    
    class Config:
        from_attributes = True


# System Status Models
class SystemStatusResponse(BaseModel):
    """Model for system status API responses."""
    status: str
    uptime_seconds: int
    active_recordings: int
    total_recordings: int
    disk_usage_percent: float
    memory_usage_percent: float
    last_updated: datetime


class LogEntry(BaseModel):
    """Model for log entry responses."""
    timestamp: datetime
    level: str
    logger: str
    message: str


class LogResponse(BaseModel):
    """Model for log API responses."""
    logs: List[LogEntry]
    total_count: int
    page: int
    per_page: int


# File Upload Models
class ArtworkUploadResponse(BaseModel):
    """Model for artwork upload responses."""
    filename: str
    file_path: str
    file_size: int
    uploaded_at: datetime


# Error Models
class ErrorResponse(BaseModel):
    """Model for API error responses."""
    error: str
    message: str
    status_code: int
    details: Optional[dict] = None


# Configuration Export/Import Models
class ConfigurationExport(BaseModel):
    """Model for configuration export."""
    streams: List[StreamConfigurationResponse]
    schedules: List[RecordingScheduleResponse]
    exported_at: datetime
    version: str = "1.0"


class ConfigurationImport(BaseModel):
    """Model for configuration import."""
    streams: List[StreamConfigurationCreate]
    schedules: List[dict]  # Will be validated separately due to foreign key dependencies
    version: str = "1.0"