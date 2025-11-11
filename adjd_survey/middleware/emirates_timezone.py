"""
Emirates Timezone Middleware
Forces all requests to use Asia/Dubai timezone regardless of client/server location.
"""
from django.utils import timezone


class EmiratesTimezoneMiddleware:
    """
    Middleware to enforce Emirates (UAE) timezone for all requests.
    
    This middleware ensures that all datetime operations within the request
    are performed using the Asia/Dubai timezone, regardless of the server's
    location or any timezone information sent by the client.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Activate Emirates timezone for this request
        timezone.activate('Asia/Dubai')
        
        try:
            response = self.get_response(request)
        finally:
            # Always deactivate timezone to prevent leaking to other requests
            timezone.deactivate()
        
        return response
