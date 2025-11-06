"""
Brute force protection middleware for Django authentication.

This middleware implements rate limiting and account lockout mechanisms
to prevent brute force attacks on login endpoints.
"""

import time
import logging
from datetime import datetime, timedelta
from django.core.cache import cache
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from weaponpowercloud_backend.security_utils import log_security_event

logger = logging.getLogger(__name__)
User = get_user_model()

# Configuration
MAX_LOGIN_ATTEMPTS = getattr(settings, 'MAX_LOGIN_ATTEMPTS', 5)
LOCKOUT_DURATION = getattr(settings, 'LOCKOUT_DURATION_MINUTES', 15)
RATE_LIMIT_DURATION = getattr(settings, 'RATE_LIMIT_DURATION_MINUTES', 5)


class BruteForceProtectionMiddleware:
    """
    Middleware to protect against brute force attacks on authentication endpoints.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is a login request
        if self.is_login_request(request):
            # Check rate limiting before processing
            if self.is_rate_limited(request):
                return self.rate_limit_response(request)
        
        response = self.get_response(request)
        
        # Check for failed login after response
        if self.is_login_request(request) and hasattr(response, 'status_code'):
            if response.status_code == 401 or response.status_code == 400:
                self.handle_failed_login(request)
        
        return response

    def is_login_request(self, request):
        """Check if this is a login request."""
        login_paths = ['/api/auth/login/', '/auth/login/', '/api/auth/azure-login/']
        return request.method == 'POST' and request.path in login_paths

    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def get_cache_keys(self, request):
        """Generate cache keys for rate limiting."""
        ip = self.get_client_ip(request)
        
        # Get email from request if available
        email = None
        if hasattr(request, 'data'):
            email = request.data.get('email')
        elif request.content_type == 'application/json':
            import json
            try:
                data = json.loads(request.body)
                email = data.get('email')
            except:
                pass
        
        ip_key = f"login_attempts_ip_{ip}"
        email_key = f"login_attempts_email_{email}" if email else None
        
        return ip_key, email_key

    def is_rate_limited(self, request):
        """Check if the request should be rate limited."""
        ip_key, email_key = self.get_cache_keys(request)
        
        # Check IP-based rate limiting
        ip_attempts = cache.get(ip_key, 0)
        if ip_attempts >= MAX_LOGIN_ATTEMPTS:
            return True
        
        # Check email-based rate limiting if email is available
        if email_key:
            email_attempts = cache.get(email_key, 0)
            if email_attempts >= MAX_LOGIN_ATTEMPTS:
                return True
        
        return False

    def handle_failed_login(self, request):
        """Handle failed login attempt."""
        ip_key, email_key = self.get_cache_keys(request)
        ip = self.get_client_ip(request)
        
        # Increment IP-based counter
        ip_attempts = cache.get(ip_key, 0) + 1
        cache.set(ip_key, ip_attempts, timeout=RATE_LIMIT_DURATION * 60)
        
        # Increment email-based counter if email is available
        if email_key:
            email_attempts = cache.get(email_key, 0) + 1
            cache.set(email_key, email_attempts, timeout=RATE_LIMIT_DURATION * 60)
        
        # Log security event
        log_security_event(
            event_type='failed_login_attempt',
            request=request,
            details={
                'ip_attempts': ip_attempts,
                'email_attempts': cache.get(email_key, 0) if email_key else 0,
                'max_attempts': MAX_LOGIN_ATTEMPTS
            }
        )
        
        # If max attempts reached, log lockout
        if ip_attempts >= MAX_LOGIN_ATTEMPTS:
            log_security_event(
                event_type='ip_lockout',
                request=request,
                details={
                    'lockout_duration_minutes': LOCKOUT_DURATION,
                    'total_attempts': ip_attempts
                }
            )

    def rate_limit_response(self, request):
        """Return rate limit exceeded response."""
        ip_key, email_key = self.get_cache_keys(request)
        
        # Get remaining time
        ip_ttl = cache.ttl(ip_key) or 0
        email_ttl = cache.ttl(email_key) or 0 if email_key else 0
        remaining_time = max(ip_ttl, email_ttl)
        
        log_security_event(
            event_type='rate_limit_exceeded',
            request=request,
            details={
                'remaining_time_seconds': remaining_time,
                'max_attempts': MAX_LOGIN_ATTEMPTS
            }
        )
        
        return JsonResponse({
            'error': 'Too many failed login attempts',
            'detail': f'Account temporarily locked. Try again in {remaining_time // 60} minutes.',
            'retry_after_seconds': remaining_time,
            'max_attempts': MAX_LOGIN_ATTEMPTS
        }, status=429)


def clear_login_attempts(email=None, ip=None):
    """
    Utility function to clear login attempts (call after successful login).
    """
    if email:
        email_key = f"login_attempts_email_{email}"
        cache.delete(email_key)
    
    if ip:
        ip_key = f"login_attempts_ip_{ip}"
        cache.delete(ip_key)


def get_remaining_attempts(email=None, ip=None):
    """
    Get remaining login attempts for an email or IP.
    """
    attempts = 0
    
    if email:
        email_key = f"login_attempts_email_{email}"
        attempts = max(attempts, cache.get(email_key, 0))
    
    if ip:
        ip_key = f"login_attempts_ip_{ip}"
        attempts = max(attempts, cache.get(ip_key, 0))
    
    return max(0, MAX_LOGIN_ATTEMPTS - attempts)
