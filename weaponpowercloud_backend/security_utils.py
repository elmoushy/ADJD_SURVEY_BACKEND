"""
Security utility functions for the WeaponPowerCloud backend.

This module provides common security functions including:
- HTML/JS sanitization
- Input validation
- Security logging
"""

import logging
import bleach
from django.utils.html import strip_tags
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Allowed HTML tags for rich text content (if needed)
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 
    'ul', 'ol', 'li', 'blockquote'
]

# Allowed attributes for HTML tags
ALLOWED_ATTRIBUTES = {
    '*': ['class'],
}

# Allowed protocols for links
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def sanitize_html_input(value, allow_tags=False):
    """
    Sanitize HTML input to prevent XSS attacks.
    
    Args:
        value (str): The input string to sanitize
        allow_tags (bool): Whether to allow safe HTML tags or strip all tags
        
    Returns:
        str: Sanitized string safe for storage and display
    """
    if not value:
        return value
    
    try:
        if allow_tags:
            # Allow only safe tags with bleach
            cleaned = bleach.clean(
                value,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                protocols=ALLOWED_PROTOCOLS,
                strip=True  # Strip disallowed tags instead of escaping
            )
        else:
            # Strip all HTML tags
            cleaned = strip_tags(value)
            # Additional cleaning with bleach to be extra safe
            cleaned = bleach.clean(cleaned, tags=[], strip=True)
        
        # Log if sanitization occurred
        if cleaned != value:
            logger.warning(f"HTML content sanitized. Original length: {len(value)}, "
                         f"Cleaned length: {len(cleaned)}")
        
        return cleaned.strip()
        
    except Exception as e:
        logger.error(f"Error sanitizing HTML input: {str(e)}")
        # Fallback to basic tag stripping
        return strip_tags(value).strip()


def validate_and_sanitize_text_input(value, max_length=None, field_name="input"):
    """
    Validate and sanitize text input for forms.
    
    Args:
        value (str): Input value to validate and sanitize
        max_length (int): Maximum allowed length
        field_name (str): Name of the field for error messages
        
    Returns:
        str: Sanitized and validated input
        
    Raises:
        ValidationError: If input fails validation
    """
    if not value:
        return value
    
    # Sanitize HTML/JS content
    sanitized_value = sanitize_html_input(value, allow_tags=False)
    
    # Check for potentially malicious patterns and remove them
    suspicious_patterns = [
        'javascript:', 'data:', 'vbscript:', 'onload=', 'onerror=',
        '<script', '</script>', 'eval(', 'document.cookie'
    ]
    
    for pattern in suspicious_patterns:
        if pattern.lower() in sanitized_value.lower():
            logger.warning(f"Suspicious pattern '{pattern}' detected in {field_name}")
            # Remove the suspicious content (case insensitive)
            sanitized_value = sanitized_value.replace(pattern, '')
            sanitized_value = sanitized_value.replace(pattern.upper(), '')
            sanitized_value = sanitized_value.replace(pattern.lower(), '')
    
    # Check length constraints
    if max_length and len(sanitized_value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed {max_length} characters after sanitization."
        )
    
    return sanitized_value.strip()


def log_security_event(event_type, user=None, request=None, details=None):
    """
    Log security-related events for monitoring.
    
    Args:
        event_type (str): Type of security event
        user: User object (if available)
        request: Request object (if available)
        details (dict): Additional details about the event
    """
    try:
        ip_address = 'unknown'
        user_agent = 'unknown'
        
        if request:
            # Get IP address
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
            if ip_address:
                ip_address = ip_address.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR', 'unknown')
            
            # Get user agent
            user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')[:200]
        
        log_data = {
            'event_type': event_type,
            'user': user.email if user else 'anonymous',
            'ip_address': ip_address,
            'user_agent': user_agent,
            'details': details or {}
        }
        
        logger.warning(f"SECURITY_EVENT: {log_data}")
        
    except Exception as e:
        logger.error(f"Error logging security event: {str(e)}")


def validate_file_upload(uploaded_file, allowed_types=None, max_size_mb=10):
    """
    Validate uploaded files for security.
    
    Args:
        uploaded_file: Django UploadedFile object
        allowed_types (list): List of allowed MIME types
        max_size_mb (int): Maximum file size in MB
        
    Returns:
        bool: True if file is safe
        
    Raises:
        ValidationError: If file fails validation
    """
    if not uploaded_file:
        return True
    
    # Check file size
    max_size_bytes = max_size_mb * 1024 * 1024
    if uploaded_file.size > max_size_bytes:
        raise ValidationError(f"File size cannot exceed {max_size_mb}MB")
    
    # Check file type if specified
    if allowed_types:
        content_type = getattr(uploaded_file, 'content_type', '')
        if content_type not in allowed_types:
            raise ValidationError(f"File type not allowed. Allowed types: {allowed_types}")
    
    # Check for potentially dangerous file extensions
    dangerous_extensions = [
        '.exe', '.bat', '.cmd', '.com', '.scr', '.vbs', '.js', '.jar',
        '.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.pl'
    ]
    
    filename = getattr(uploaded_file, 'name', '').lower()
    for ext in dangerous_extensions:
        if filename.endswith(ext):
            raise ValidationError(f"File extension '{ext}' is not allowed for security reasons")
    
    return True
