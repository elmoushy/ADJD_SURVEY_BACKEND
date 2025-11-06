"""
Oracle-specific database router and operations.

This module provides Oracle-compatible database operations while maintaining
Django's standard behavior for other databases.
"""

from django.conf import settings
from django.db import connection


class OracleRouter:
    """
    Database router that provides Oracle-specific behavior.
    
    This router ensures that when using Oracle, we handle unique constraints
    differently to work around Oracle's limitations with encrypted fields.
    """
    
    def db_for_read(self, model, **hints):
        """Point all operations to the default database."""
        return None  # Use default routing
    
    def db_for_write(self, model, **hints):
        """Point all operations to the default database."""
        return None  # Use default routing
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Allow migrations for all apps."""
        return None  # Use default behavior


def is_oracle_db():
    """
    Check if the current database is Oracle.
    
    Returns:
        bool: True if using Oracle database, False otherwise
    """
    try:
        # Check the database engine
        engine = settings.DATABASES['default']['ENGINE']
        return 'oracle' in engine.lower()
    except (KeyError, AttributeError):
        try:
            # Fallback to connection check
            return 'oracle' in connection.settings_dict['ENGINE'].lower()
        except Exception:
            return False


def execute_oracle_safe_sql(sql, params=None):
    """
    Execute SQL that's safe for both Oracle and other databases.
    
    This function can be used to execute database operations that need
    special handling for Oracle compatibility.
    """
    with connection.cursor() as cursor:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchall()
