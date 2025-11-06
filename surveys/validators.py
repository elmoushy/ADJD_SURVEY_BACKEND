"""
Answer validation utilities for survey responses.

This module provides validation functions for different answer types
based on question validation_type.
"""

import re
import logging
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError

logger = logging.getLogger(__name__)


def validate_email(value):
    """
    Validate email address format.
    
    Args:
        value (str): Email address to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not value or not value.strip():
        return (True, None)  # Empty values handled by is_required
    
    # Basic email regex pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if re.match(email_pattern, value.strip()):
        return (True, None)
    
    return (False, "يرجى إدخال عنوان بريد إلكتروني صحيح / Please enter a valid email address")


def validate_phone(value):
    """
    Validate phone number format (numeric only, optionally with + prefix).
    
    Accepts formats:
    - +971501234567
    - 971501234567
    - 0501234567
    - 501234567
    
    Args:
        value (str): Phone number to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not value or not value.strip():
        return (True, None)  # Empty values handled by is_required
    
    # Remove spaces and dashes for validation
    cleaned = value.strip().replace(' ', '').replace('-', '')
    
    # Allow optional + prefix followed by digits only
    phone_pattern = r'^\+?[0-9]{7,15}$'
    
    if re.match(phone_pattern, cleaned):
        return (True, None)
    
    return (False, "يرجى إدخال رقم هاتف صحيح (أرقام فقط) / Please enter a valid phone number (numbers only)")


def validate_number(value):
    """
    Validate numeric value (integers and decimals).
    
    Args:
        value (str): Number to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not value or not value.strip():
        return (True, None)  # Empty values handled by is_required
    
    # Remove spaces
    cleaned = value.strip().replace(' ', '')
    
    # Allow integers and decimals (with . or ,)
    number_pattern = r'^-?[0-9]+([.,][0-9]+)?$'
    
    if re.match(number_pattern, cleaned):
        return (True, None)
    
    return (False, "يرجى إدخال رقم صحيح / Please enter a valid number")


def validate_url(value):
    """
    Validate URL format (http/https only).
    
    Args:
        value (str): URL to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not value or not value.strip():
        return (True, None)  # Empty values handled by is_required
    
    # Check for http/https protocol
    cleaned_url = value.strip()
    if not (cleaned_url.startswith('http://') or cleaned_url.startswith('https://')):
        return (False, "يرجى إدخال رابط صحيح (يجب أن يبدأ بـ http:// أو https://) / Please enter a valid URL (must start with http:// or https://)")
    
    validator = URLValidator(schemes=['http', 'https'])
    try:
        validator(cleaned_url)
        return (True, None)
    except DjangoValidationError:
        return (False, "يرجى إدخال رابط صحيح / Please enter a valid URL")


def validate_answer(question, answer_text):
    """
    Validate answer based on question's validation_type.
    
    Args:
        question: Question model instance
        answer_text (str): Answer text to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Skip validation for non-text question types
    if question.question_type not in ['text', 'textarea']:
        return (True, None)
    
    # Get validation type
    validation_type = getattr(question, 'validation_type', 'none')
    
    # Skip if no validation required
    if validation_type == 'none':
        return (True, None)
    
    # Apply appropriate validation
    if validation_type == 'email':
        return validate_email(answer_text)
    elif validation_type == 'phone':
        return validate_phone(answer_text)
    elif validation_type == 'number':
        return validate_number(answer_text)
    elif validation_type == 'url':
        return validate_url(answer_text)
    
    return (True, None)


def get_validation_error_messages():
    """
    Get common validation error messages in Arabic and English.
    
    Returns:
        dict: Error messages for different validation types
    """
    return {
        'email': "يرجى إدخال عنوان بريد إلكتروني صحيح / Please enter a valid email address",
        'phone': "يرجى إدخال رقم هاتف صحيح (أرقام فقط) / Please enter a valid phone number (numbers only)",
        'number': "يرجى إدخال رقم صحيح / Please enter a valid number",
        'url': "يرجى إدخال رابط صحيح / Please enter a valid URL",
        'required': "هذا السؤال مطلوب / This question is required"
    }
