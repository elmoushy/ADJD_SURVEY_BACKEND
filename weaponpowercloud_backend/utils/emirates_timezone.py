"""
Emirates Timezone Utilities

Helper functions for working with Emirates (UAE) timezone in Django.
"""
from django.utils import timezone
import pytz


def get_emirates_timezone():
    """Get the Emirates timezone object."""
    return pytz.timezone('Asia/Dubai')


def now_emirates():
    """Get current datetime in Emirates timezone."""
    return timezone.localtime(timezone.now())


def convert_to_emirates(dt):
    """
    Convert a datetime object to Emirates timezone.
    
    Args:
        dt: A datetime object (timezone-aware or naive)
        
    Returns:
        datetime: The datetime converted to Emirates timezone
    """
    if dt.tzinfo is None:
        # Naive datetime - assume it's in UTC
        dt = timezone.make_aware(dt, timezone.utc)
    
    emirates_tz = get_emirates_timezone()
    return dt.astimezone(emirates_tz)


def format_emirates_datetime(dt, format_string='%Y-%m-%d %H:%M:%S %Z'):
    """
    Format a datetime object in Emirates timezone.
    
    Args:
        dt: A datetime object
        format_string: strftime format string
        
    Returns:
        str: Formatted datetime string in Emirates timezone
    """
    emirates_dt = convert_to_emirates(dt)
    return emirates_dt.strftime(format_string)


def get_emirates_date():
    """Get current date in Emirates timezone."""
    return now_emirates().date()


def get_emirates_time():
    """Get current time in Emirates timezone."""
    return now_emirates().time()
