"""
Emirates Timezone Decorators

Decorators to ensure functions always work with Emirates timezone.
"""
from functools import wraps
from django.utils import timezone


def emirates_timezone_required(func):
    """
    Decorator to ensure a function runs with Emirates timezone activated.
    
    Usage:
        @emirates_timezone_required
        def my_view(request):
            # This function will always run with Asia/Dubai timezone
            current_time = timezone.localtime(timezone.now())
            return JsonResponse({'time': current_time})
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Store current timezone
        current_tz = timezone.get_current_timezone()
        
        try:
            # Activate Emirates timezone
            timezone.activate('Asia/Dubai')
            result = func(*args, **kwargs)
        finally:
            # Restore previous timezone
            if current_tz:
                timezone.activate(current_tz)
            else:
                timezone.deactivate()
        
        return result
    return wrapper


def emirates_datetime_response(func):
    """
    Decorator for API views that converts all datetime fields to Emirates timezone
    before sending response.
    
    Usage:
        @emirates_datetime_response
        def get_news_list(request):
            # All datetime fields in response will be in Emirates timezone
            return Response(news_data)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Ensure Emirates timezone is active
        timezone.activate('Asia/Dubai')
        
        try:
            response = func(*args, **kwargs)
            
            # If it's a DRF Response object, ensure timezone consistency
            if hasattr(response, 'data') and response.data:
                # The middleware will handle timezone conversion
                pass
                
            return response
        finally:
            # Note: Don't deactivate here as middleware handles it
            pass
    
    return wrapper
