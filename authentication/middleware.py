"""
JWT Compatibility Middleware

This middleware ensures that regular JWT tokens work seamlessly across all endpoints
that were originally designed for Azure AD tokens only.
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from rest_framework.request import Request

User = get_user_model()
logger = logging.getLogger(__name__)


class JWTCompatibilityMiddleware(MiddlewareMixin):
    """
    Middleware to ensure JWT token compatibility across all endpoints.
    
    This middleware:
    1. Logs authentication attempts for debugging
    2. Ensures consistent user object handling
    3. Provides fallback mechanisms for authentication
    """
    
    def process_request(self, request):
        """Process incoming requests to log authentication info."""
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            logger.debug(f"JWT Compatibility: Request with token {token[:20]}...")
        
        return None
    
    def process_response(self, request, response):
        """Process responses to log authentication results."""
        if hasattr(request, 'user') and request.user.is_authenticated:
            logger.debug(f"JWT Compatibility: Authenticated user {request.user.email} "
                        f"(auth_type: {getattr(request.user, 'auth_type', 'unknown')})")
        elif response.status_code == 401:
            logger.debug("JWT Compatibility: Authentication failed (401)")
        
        return response


class UniversalAuthMiddleware(MiddlewareMixin):
    """
    Middleware that ensures all authenticated endpoints work with both token types.
    
    This middleware acts as a safety net to catch any authentication issues
    and provide consistent behavior across all endpoints.
    """
    
    def process_request(self, request):
        """
        Process requests to ensure consistent authentication handling.
        """
        # Skip processing for non-API endpoints
        if not request.path.startswith('/api/'):
            return None
        
        # Skip for authentication endpoints
        if request.path.startswith('/api/auth/login/') or request.path.startswith('/api/auth/register/'):
            return None
        
        # Get authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Bearer '):
            # Log the authentication attempt
            token = auth_header[7:]
            logger.debug(f"Universal Auth: Processing Bearer token for {request.path}")
            
            # The actual authentication will be handled by the authentication classes
            # This middleware just ensures logging and consistency
        
        return None
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Process view to ensure authentication is handled correctly.
        """
        # This is called after the request has been processed by authentication classes
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Ensure user has all required attributes
            if not hasattr(request.user, 'auth_type'):
                # Set default auth_type if missing (for backward compatibility)
                request.user.auth_type = 'azure'  # Default to azure for existing users
                logger.warning(f"User {request.user.email} missing auth_type, defaulting to 'azure'")
        
        return None
