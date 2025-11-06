"""
Timezone utilities for surveys service.
Ensures all datetime operations maintain Asia/Dubai timezone consistently.
Includes Hijri to Gregorian date conversion for API responses.
"""

import pytz
from django.utils import timezone
from datetime import datetime

try:
    from hijri_converter import Hijri, Gregorian
    HIJRI_AVAILABLE = True
except ImportError:
    HIJRI_AVAILABLE = False


# UAE timezone constant
UAE_TIMEZONE = pytz.timezone('Asia/Dubai')


def ensure_uae_timezone(dt):
    """
    Ensure datetime is in UAE timezone.
    
    Args:
        dt: datetime object (can be naive or timezone-aware)
    
    Returns:
        datetime object in UAE timezone
    """
    if dt is None:
        return None
    
    if timezone.is_naive(dt):
        # If naive, assume it's already in UAE timezone and localize it
        return UAE_TIMEZONE.localize(dt)
    else:
        # If timezone-aware, convert to UAE timezone
        return dt.astimezone(UAE_TIMEZONE)


def format_uae_datetime(dt, format_string='%Y-%m-%d %H:%M'):
    """
    Format datetime in UAE timezone.
    
    Args:
        dt: datetime object
        format_string: strftime format string
    
    Returns:
        Formatted string in UAE timezone
    """
    if dt is None:
        return None
    
    uae_dt = ensure_uae_timezone(dt)
    return uae_dt.strftime(format_string)


def format_uae_date_only(dt, format_string='%Y-%m-%d'):
    """
    Format date only in UAE timezone.
    
    Args:
        dt: datetime object
        format_string: strftime format string
    
    Returns:
        Formatted date string in UAE timezone
    """
    if dt is None:
        return None
    
    uae_dt = ensure_uae_timezone(dt)
    return uae_dt.strftime(format_string)


def now_uae():
    """
    Get current datetime in UAE timezone.
    
    Returns:
        Current datetime in UAE timezone
    """
    return timezone.now().astimezone(UAE_TIMEZONE)


def is_currently_active_uae(survey):
    """
    Check if survey is currently active using UAE timezone for all comparisons.
    
    Args:
        survey: Survey instance
    
    Returns:
        bool: True if survey is currently active
    """
    if not survey.is_active or survey.deleted_at is not None:
        return False
    
    now_uae_time = now_uae()
    
    # Check start date
    if survey.start_date:
        start_uae = ensure_uae_timezone(survey.start_date)
        if now_uae_time < start_uae:
            return False
    
    # Check end date
    if survey.end_date:
        end_uae = ensure_uae_timezone(survey.end_date)
        if now_uae_time > end_uae:
            return False
    
    return True


def get_status_uae(survey):
    """
    Get survey status using UAE timezone for all comparisons.
    
    Args:
        survey: Survey instance
    
    Returns:
        str: Survey status ('active', 'scheduled', 'expired', 'inactive', 'deleted')
    """
    if survey.deleted_at is not None:
        return 'deleted'
    
    if not survey.is_active:
        return 'inactive'
    
    now_uae_time = now_uae()
    
    if survey.start_date:
        start_uae = ensure_uae_timezone(survey.start_date)
        if now_uae_time < start_uae:
            return 'scheduled'
    
    if survey.end_date:
        end_uae = ensure_uae_timezone(survey.end_date)
        if now_uae_time > end_uae:
            return 'expired'
    
    return 'active'


def serialize_datetime_uae(dt):
    """
    Serialize datetime to string in UAE timezone with timezone info.
    
    Args:
        dt: datetime object
    
    Returns:
        ISO formatted string with UAE timezone (+04:00)
    """
    if dt is None:
        return None
    
    uae_dt = ensure_uae_timezone(dt)
    return uae_dt.isoformat()


def hijri_to_gregorian_date(hijri_year, hijri_month, hijri_day):
    """
    Convert Hijri date to Gregorian date.
    
    Args:
        hijri_year: Hijri year (int)
        hijri_month: Hijri month (1-12)
        hijri_day: Hijri day (1-30)
    
    Returns:
        datetime object in Gregorian calendar with UAE timezone, or None if conversion fails
    """
    if not HIJRI_AVAILABLE:
        raise ImportError("hijri-converter library is not installed. Install with: pip install hijri-converter")
    
    try:
        hijri_date = Hijri(hijri_year, hijri_month, hijri_day)
        gregorian_date = hijri_date.to_gregorian()
        
        # Create datetime object and localize to UAE timezone
        dt = datetime(gregorian_date.year, gregorian_date.month, gregorian_date.day)
        return UAE_TIMEZONE.localize(dt)
    except Exception as e:
        # Log error and return None for invalid dates
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to convert Hijri date ({hijri_year}-{hijri_month}-{hijri_day}) to Gregorian: {e}")
        return None


def hijri_datetime_to_gregorian(hijri_year, hijri_month, hijri_day, hour=0, minute=0, second=0):
    """
    Convert Hijri date with time to Gregorian datetime.
    
    Args:
        hijri_year: Hijri year (int)
        hijri_month: Hijri month (1-12)
        hijri_day: Hijri day (1-30)
        hour: Hour (0-23, default 0)
        minute: Minute (0-59, default 0)
        second: Second (0-59, default 0)
    
    Returns:
        datetime object in Gregorian calendar with UAE timezone, or None if conversion fails
    """
    if not HIJRI_AVAILABLE:
        raise ImportError("hijri-converter library is not installed. Install with: pip install hijri-converter")
    
    try:
        hijri_date = Hijri(hijri_year, hijri_month, hijri_day)
        gregorian_date = hijri_date.to_gregorian()
        
        # Create datetime object with time and localize to UAE timezone
        dt = datetime(gregorian_date.year, gregorian_date.month, gregorian_date.day, 
                     hour, minute, second)
        return UAE_TIMEZONE.localize(dt)
    except Exception as e:
        # Log error and return None for invalid dates
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to convert Hijri datetime ({hijri_year}-{hijri_month}-{hijri_day} {hour}:{minute}:{second}) to Gregorian: {e}")
        return None


def convert_hijri_string_to_gregorian(hijri_string, format='%Y-%m-%d'):
    """
    Convert Hijri date string to Gregorian datetime.
    
    Args:
        hijri_string: String in format 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' (Hijri)
        format: Expected format of the input string (default: '%Y-%m-%d')
    
    Returns:
        datetime object in Gregorian calendar with UAE timezone, or None if conversion fails
    """
    if not HIJRI_AVAILABLE:
        raise ImportError("hijri-converter library is not installed. Install with: pip install hijri-converter")
    
    try:
        # Parse the Hijri string
        if ' ' in hijri_string and ':' in hijri_string:
            # Has time component
            parts = hijri_string.split()
            date_part = parts[0]
            time_part = parts[1] if len(parts) > 1 else '00:00:00'
            
            date_components = date_part.split('-')
            time_components = time_part.split(':')
            
            year = int(date_components[0])
            month = int(date_components[1])
            day = int(date_components[2])
            hour = int(time_components[0]) if len(time_components) > 0 else 0
            minute = int(time_components[1]) if len(time_components) > 1 else 0
            second = int(time_components[2]) if len(time_components) > 2 else 0
            
            return hijri_datetime_to_gregorian(year, month, day, hour, minute, second)
        else:
            # Date only
            date_components = hijri_string.split('-')
            year = int(date_components[0])
            month = int(date_components[1])
            day = int(date_components[2])
            
            return hijri_to_gregorian_date(year, month, day)
    except Exception as e:
        # Log error and return None for invalid format
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to parse and convert Hijri string '{hijri_string}': {e}")
        return None


def ensure_gregorian_from_hijri(dt_or_hijri_dict):
    """
    Ensure datetime is in Gregorian calendar. Accepts either a datetime object 
    or a dictionary with Hijri date components.
    
    Args:
        dt_or_hijri_dict: Either a datetime object (returned as-is) or a dict with keys:
                         - 'year', 'month', 'day' (required)
                         - 'hour', 'minute', 'second' (optional)
                         - 'is_hijri': True (to indicate Hijri conversion needed)
    
    Returns:
        datetime object in UAE timezone (Gregorian)
    """
    if dt_or_hijri_dict is None:
        return None
    
    # If it's already a datetime object, just ensure UAE timezone
    if isinstance(dt_or_hijri_dict, datetime):
        return ensure_uae_timezone(dt_or_hijri_dict)
    
    # If it's a dictionary with Hijri date
    if isinstance(dt_or_hijri_dict, dict) and dt_or_hijri_dict.get('is_hijri'):
        year = dt_or_hijri_dict.get('year')
        month = dt_or_hijri_dict.get('month')
        day = dt_or_hijri_dict.get('day')
        hour = dt_or_hijri_dict.get('hour', 0)
        minute = dt_or_hijri_dict.get('minute', 0)
        second = dt_or_hijri_dict.get('second', 0)
        
        return hijri_datetime_to_gregorian(year, month, day, hour, minute, second)
    
    # Otherwise, return None
    return None
