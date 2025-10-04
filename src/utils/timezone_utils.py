"""
Timezone utilities for consistent local timezone handling.
"""

import os
from datetime import datetime
from typing import Optional
import pytz


def get_local_timezone():
    """Get the local timezone from environment or default."""
    tz_name = os.environ.get('TZ', 'US/Mountain')
    return pytz.timezone(tz_name)


def get_local_now() -> datetime:
    """Get current datetime in local timezone."""
    local_tz = get_local_timezone()
    return datetime.now(local_tz)


def localize_datetime(dt: datetime) -> datetime:
    """Convert naive datetime to local timezone."""
    if dt.tzinfo is None:
        local_tz = get_local_timezone()
        return local_tz.localize(dt)
    return dt


def to_local_timezone(dt: datetime) -> datetime:
    """Convert any datetime to local timezone."""
    if dt.tzinfo is None:
        # Assume naive datetime is already in local timezone
        return localize_datetime(dt)
    else:
        # Convert from other timezone to local
        local_tz = get_local_timezone()
        return dt.astimezone(local_tz)


def format_local_datetime(dt: Optional[datetime], format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime in local timezone."""
    if dt is None:
        return ""
    
    local_dt = to_local_timezone(dt)
    return local_dt.strftime(format_str)


def get_local_date_string() -> str:
    """Get current date string in local timezone (YYYY-MM-DD format)."""
    return get_local_now().strftime("%Y-%m-%d")


def get_local_timestamp_string() -> str:
    """Get current timestamp string in local timezone (YYYYMMDD_HHMMSS format)."""
    return get_local_now().strftime("%Y%m%d_%H%M%S")