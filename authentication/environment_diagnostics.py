"""
Environment diagnostics to help debug production issues.
"""

import sys
import django
import logging

logger = logging.getLogger(__name__)


def log_environment_info():
    """Log detailed environment information for debugging."""
    logger.info("="*60)
    logger.info("ENVIRONMENT DIAGNOSTICS")
    logger.info("="*60)
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Django version: {django.get_version()}")
    logger.info(f"Django VERSION tuple: {django.VERSION}")
    
    try:
        from django.db import connection
        logger.info(f"Database engine: {connection.settings_dict['ENGINE']}")
        logger.info(f"Database name: {connection.settings_dict.get('NAME', 'N/A')}")
    except Exception as e:
        logger.error(f"Could not get database info: {e}")
    
    try:
        import rest_framework
        logger.info(f"DRF version: {rest_framework.VERSION}")
    except Exception as e:
        logger.error(f"Could not get DRF version: {e}")
    
    logger.info("="*60)


def diagnose_user_manager():
    """Diagnose User manager and field types."""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    logger.info("User Model Diagnostics:")
    logger.info(f"User model: {User}")
    logger.info(f"User manager: {User.objects}")
    logger.info(f"User manager class: {User.objects.__class__}")
    
    # Check field types
    for field in User._meta.get_fields():
        logger.info(f"Field: {field.name}, Type: {field.__class__.__name__}")
        if hasattr(field, 'max_length'):
            logger.info(f"  - max_length: {field.max_length}")
        if hasattr(field, 'unique'):
            logger.info(f"  - unique: {field.unique}")
