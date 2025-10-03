"""
RecordingSession model for tracking individual recording sessions.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import validates, relationship
from pydantic import BaseModel, validator
from typing import Optional
import os

from .database import Base, RecordingStatus, TransferStatus


class RecordingSession(Base):
    """SQLAlchemy model for recording sessions."""
    
    __tablename__ = "recording_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("recording_schedules.id"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLEnum(RecordingStatus), default=RecordingStatus.SCHEDULED, nullable=False)
    output_file_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    transfer_status = Column(SQLEnum(TransferStatus), default=TransferStatus.PENDING, nullable=False)
    transfer_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship to recording schedule
    schedule = relationship("RecordingSchedule", backref="sessions")
    
    @validates('output_file_path')
    def validate_output_file_path(self, key, file_path):
        """Validate output file path."""
        if file_path is not None:
            if not file_path.strip():
                raise ValueError("Output file path cannot be empty string")
            
            # Check if path has valid extension
            valid_extensions = ['.mp3', '.wav', '.flac', '.aac']
            if not any(file_path.lower().endswith(ext) for ext in valid_extensions):
                raise ValueError("Output file must have a valid audio extension (.mp3, .wav, .flac, .aac)")
            
            return file_path.strip()
        return file_path
    
    @validates('file_size_bytes')
    def validate_file_size(self, key, size):
        """Validate file size."""
        if size is not None and size < 0:
            raise ValueError("File size cannot be negative")
        return size
    
    @validates('start_time', 'end_time')
    def validate_times(self, key, time_value):
        """Validate start and end times."""
        if time_value is not None and key == 'end_time':
            if self.start_time and time_value <= self.start_time:
                raise ValueError("End time must be after start time")
        return time_value
    
    def get_duration_minutes(self) -> Optional[int]:
        """Calculate recording duration in minutes."""
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            return int(duration.total_seconds() / 60)
        return None
    
    def get_file_size_mb(self) -> Optional[float]:
        """Get file size in megabytes."""
        if self.file_size_bytes:
            return round(self.file_size_bytes / (1024 * 1024), 2)
        return None
    
    def is_completed(self) -> bool:
        """Check if recording session is completed."""
        return self.status == RecordingStatus.COMPLETED
    
    def is_failed(self) -> bool:
        """Check if recording session failed."""
        return self.status == RecordingStatus.FAILED
    
    def is_in_progress(self) -> bool:
        """Check if recording session is in progress."""
        return self.status in [RecordingStatus.RECORDING, RecordingStatus.PROCESSING]
    
    def update_file_info(self, file_path: str):
        """Update file path and calculate file size."""
        self.output_file_path = file_path
        if os.path.exists(file_path):
            self.file_size_bytes = os.path.getsize(file_path)
    
    def __repr__(self):
        return f"<RecordingSession(id={self.id}, status={self.status.value}, start={self.start_time})>"


class RecordingSessionCreate(BaseModel):
    """Pydantic model for creating recording sessions."""
    
    schedule_id: int
    start_time: datetime
    status: RecordingStatus = RecordingStatus.SCHEDULED
    
    @validator('start_time')
    def validate_start_time(cls, v):
        if v is None:
            raise ValueError("Start time is required")
        return v


class RecordingSessionUpdate(BaseModel):
    """Pydantic model for updating recording sessions."""
    
    end_time: Optional[datetime] = None
    status: Optional[RecordingStatus] = None
    output_file_path: Optional[str] = None
    error_message: Optional[str] = None
    file_size_bytes: Optional[int] = None
    transfer_status: Optional[TransferStatus] = None
    transfer_error_message: Optional[str] = None
    
    @validator('file_size_bytes')
    def validate_file_size(cls, v):
        if v is not None and v < 0:
            raise ValueError("File size cannot be negative")
        return v
    
    @validator('output_file_path')
    def validate_output_file_path(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("Output file path cannot be empty string")
            
            valid_extensions = ['.mp3', '.wav', '.flac', '.aac']
            if not any(v.lower().endswith(ext) for ext in valid_extensions):
                raise ValueError("Output file must have a valid audio extension")
        
        return v


class RecordingSessionResponse(BaseModel):
    """Pydantic model for recording session responses."""
    
    id: int
    schedule_id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: RecordingStatus
    output_file_path: Optional[str]
    error_message: Optional[str]
    file_size_bytes: Optional[int]
    transfer_status: TransferStatus
    transfer_error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    duration_minutes: Optional[int] = None
    file_size_mb: Optional[float] = None
    
    class Config:
        from_attributes = True
        
    @validator('duration_minutes', always=True)
    def calculate_duration(cls, v, values):
        start_time = values.get('start_time')
        end_time = values.get('end_time')
        if start_time and end_time:
            duration = end_time - start_time
            return int(duration.total_seconds() / 60)
        return None
    
    @validator('file_size_mb', always=True)
    def calculate_file_size_mb(cls, v, values):
        file_size_bytes = values.get('file_size_bytes')
        if file_size_bytes:
            return round(file_size_bytes / (1024 * 1024), 2)
        return None