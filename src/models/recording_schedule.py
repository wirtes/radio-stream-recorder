"""
RecordingSchedule model for managing recording schedules with cron expressions.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import validates, relationship
from pydantic import BaseModel, validator
from typing import Optional
from croniter import croniter
import re

from .database import Base


class RecordingSchedule(Base):
    """SQLAlchemy model for recording schedules."""
    
    __tablename__ = "recording_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    stream_config_id = Column(Integer, ForeignKey("stream_configurations.id"), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    next_run_time = Column(DateTime(timezone=True), nullable=True)
    last_run_time = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship to stream configuration
    stream_config = relationship("StreamConfiguration", backref="schedules")
    
    @validates('cron_expression')
    def validate_cron_expression(self, key, cron_expr):
        """Validate cron expression format and syntax."""
        if not cron_expr or not cron_expr.strip():
            raise ValueError("Cron expression cannot be empty")
        
        cron_expr = cron_expr.strip()
        
        # Basic cron format validation (5 fields: minute hour day month weekday)
        cron_parts = cron_expr.split()
        if len(cron_parts) != 5:
            raise ValueError("Cron expression must have exactly 5 fields: minute hour day month weekday")
        
        # Validate each field using regex patterns
        patterns = [
            r'^(\*|([0-5]?\d)(,([0-5]?\d))*|([0-5]?\d)-([0-5]?\d)|\*/([0-5]?\d))$',  # minute (0-59)
            r'^(\*|(1?\d|2[0-3])(,(1?\d|2[0-3]))*|(1?\d|2[0-3])-(1?\d|2[0-3])|\*/(1?\d|2[0-3]))$',  # hour (0-23)
            r'^(\*|([1-2]?\d|3[01])(,([1-2]?\d|3[01]))*|([1-2]?\d|3[01])-([1-2]?\d|3[01])|\*/([1-2]?\d|3[01]))$',  # day (1-31)
            r'^(\*|(1[0-2]|[1-9])(,(1[0-2]|[1-9]))*|(1[0-2]|[1-9])-(1[0-2]|[1-9])|\*/(1[0-2]|[1-9]))$',  # month (1-12)
            r'^(\*|[0-6](,[0-6])*|[0-6]-[0-6]|\*/[0-6])$'  # weekday (0-6, 0=Sunday)
        ]
        
        field_names = ['minute', 'hour', 'day', 'month', 'weekday']
        
        for i, (part, pattern, name) in enumerate(zip(cron_parts, patterns, field_names)):
            if not re.match(pattern, part):
                raise ValueError(f"Invalid {name} field in cron expression: {part}")
        
        # Test with croniter to ensure it's a valid cron expression
        try:
            croniter(cron_expr)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {str(e)}")
        
        return cron_expr
    
    @validates('duration_minutes')
    def validate_duration(self, key, duration):
        """Validate recording duration."""
        if duration is None or duration <= 0:
            raise ValueError("Duration must be a positive integer")
        if duration > 1440:  # 24 hours
            raise ValueError("Duration cannot exceed 1440 minutes (24 hours)")
        return duration
    
    @validates('max_retries')
    def validate_max_retries(self, key, max_retries):
        """Validate maximum retry count."""
        if max_retries is None or max_retries < 0:
            raise ValueError("Max retries must be a non-negative integer")
        if max_retries > 10:
            raise ValueError("Max retries cannot exceed 10")
        return max_retries
    
    def calculate_next_run_time(self, base_time: Optional[datetime] = None) -> datetime:
        """Calculate the next run time based on cron expression."""
        if base_time is None:
            base_time = datetime.now()
        
        cron = croniter(self.cron_expression, base_time)
        return cron.get_next(datetime)
    
    def update_next_run_time(self):
        """Update the next_run_time field based on current time."""
        self.next_run_time = self.calculate_next_run_time()
    
    def __repr__(self):
        return f"<RecordingSchedule(id={self.id}, cron='{self.cron_expression}', duration={self.duration_minutes}min)>"


class RecordingScheduleCreate(BaseModel):
    """Pydantic model for creating recording schedules."""
    
    stream_config_id: int
    cron_expression: str
    duration_minutes: int
    is_active: bool = True
    max_retries: int = 3
    
    @validator('cron_expression')
    def validate_cron_expression(cls, v):
        if not v or not v.strip():
            raise ValueError("Cron expression cannot be empty")
        
        v = v.strip()
        cron_parts = v.split()
        if len(cron_parts) != 5:
            raise ValueError("Cron expression must have exactly 5 fields")
        
        # Test with croniter
        try:
            croniter(v)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {str(e)}")
        
        return v
    
    @validator('duration_minutes')
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be a positive integer")
        if v > 1440:
            raise ValueError("Duration cannot exceed 1440 minutes (24 hours)")
        return v
    
    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0:
            raise ValueError("Max retries must be non-negative")
        if v > 10:
            raise ValueError("Max retries cannot exceed 10")
        return v


class RecordingScheduleUpdate(BaseModel):
    """Pydantic model for updating recording schedules."""
    
    cron_expression: Optional[str] = None
    duration_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    max_retries: Optional[int] = None
    
    @validator('cron_expression')
    def validate_cron_expression(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Cron expression cannot be empty")
            
            v = v.strip()
            cron_parts = v.split()
            if len(cron_parts) != 5:
                raise ValueError("Cron expression must have exactly 5 fields")
            
            try:
                croniter(v)
            except Exception as e:
                raise ValueError(f"Invalid cron expression: {str(e)}")
        
        return v
    
    @validator('duration_minutes')
    def validate_duration(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError("Duration must be a positive integer")
            if v > 1440:
                raise ValueError("Duration cannot exceed 1440 minutes (24 hours)")
        return v