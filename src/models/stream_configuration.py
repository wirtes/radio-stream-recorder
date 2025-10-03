"""
StreamConfiguration model for managing audio stream settings.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import validates
from pydantic import BaseModel, HttpUrl, validator
from typing import Optional
import re

from .database import Base


class StreamConfiguration(Base):
    """SQLAlchemy model for stream configuration."""
    
    __tablename__ = "stream_configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    stream_url = Column(Text, nullable=False)
    artist = Column(String(255), nullable=False)
    album = Column(String(255), nullable=False)
    album_artist = Column(String(255), nullable=False)
    artwork_path = Column(String(500), nullable=True)
    output_filename_pattern = Column(String(500), nullable=False, default="{date}_{name}.mp3")
    scp_destination = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    @validates('stream_url')
    def validate_stream_url(self, key, stream_url):
        """Validate that stream URL is properly formatted."""
        if not stream_url:
            raise ValueError("Stream URL cannot be empty")
        
        # Basic URL validation - should start with http/https/rtmp
        url_pattern = re.compile(
            r'^(https?|rtmp|rtmps)://'  # protocol
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(stream_url):
            raise ValueError("Invalid stream URL format")
        
        return stream_url
    
    @validates('name')
    def validate_name(self, key, name):
        """Validate stream name."""
        if not name or not name.strip():
            raise ValueError("Stream name cannot be empty")
        if len(name.strip()) > 255:
            raise ValueError("Stream name cannot exceed 255 characters")
        return name.strip()
    
    @validates('artist', 'album', 'album_artist')
    def validate_metadata_fields(self, key, value):
        """Validate metadata fields."""
        if not value or not value.strip():
            raise ValueError(f"{key} cannot be empty")
        if len(value.strip()) > 255:
            raise ValueError(f"{key} cannot exceed 255 characters")
        return value.strip()
    
    @validates('output_filename_pattern')
    def validate_filename_pattern(self, key, pattern):
        """Validate output filename pattern."""
        if not pattern or not pattern.strip():
            raise ValueError("Output filename pattern cannot be empty")
        
        # Check for required placeholders
        if '{date}' not in pattern:
            raise ValueError("Output filename pattern must contain {date} placeholder")
        
        # Check for invalid characters in filename
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            if char in pattern:
                raise ValueError(f"Output filename pattern cannot contain '{char}'")
        
        return pattern.strip()
    
    @validates('scp_destination')
    def validate_scp_destination(self, key, destination):
        """Validate SCP destination format."""
        if not destination or not destination.strip():
            raise ValueError("SCP destination cannot be empty")
        
        # Basic SCP destination validation: user@host:/path
        scp_pattern = re.compile(r'^[a-zA-Z0-9_-]+@[a-zA-Z0-9.-]+:[/~].*$')
        if not scp_pattern.match(destination.strip()):
            raise ValueError("SCP destination must be in format: user@host:/path")
        
        return destination.strip()
    
    def __repr__(self):
        return f"<StreamConfiguration(id={self.id}, name='{self.name}', url='{self.stream_url[:50]}...')>"


class StreamConfigurationCreate(BaseModel):
    """Pydantic model for creating stream configurations."""
    
    name: str
    stream_url: str
    artist: str
    album: str
    album_artist: str
    artwork_path: Optional[str] = None
    output_filename_pattern: str = "{date}_{name}.mp3"
    scp_destination: str
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Stream name cannot be empty")
        if len(v.strip()) > 255:
            raise ValueError("Stream name cannot exceed 255 characters")
        return v.strip()
    
    @validator('stream_url')
    def validate_stream_url(cls, v):
        if not v:
            raise ValueError("Stream URL cannot be empty")
        
        url_pattern = re.compile(
            r'^(https?|rtmp|rtmps)://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(v):
            raise ValueError("Invalid stream URL format")
        
        return v
    
    @validator('artist', 'album', 'album_artist')
    def validate_metadata_fields(cls, v):
        if not v or not v.strip():
            raise ValueError("Metadata fields cannot be empty")
        if len(v.strip()) > 255:
            raise ValueError("Metadata fields cannot exceed 255 characters")
        return v.strip()


class StreamConfigurationUpdate(BaseModel):
    """Pydantic model for updating stream configurations."""
    
    name: Optional[str] = None
    stream_url: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    artwork_path: Optional[str] = None
    output_filename_pattern: Optional[str] = None
    scp_destination: Optional[str] = None
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Stream name cannot be empty")
            if len(v.strip()) > 255:
                raise ValueError("Stream name cannot exceed 255 characters")
            return v.strip()
        return v
    
    @validator('stream_url')
    def validate_stream_url(cls, v):
        if v is not None:
            if not v:
                raise ValueError("Stream URL cannot be empty")
            
            url_pattern = re.compile(
                r'^(https?|rtmp|rtmps)://'
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
                r'localhost|'
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
                r'(?::\d+)?'
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            
            if not url_pattern.match(v):
                raise ValueError("Invalid stream URL format")
        
        return v