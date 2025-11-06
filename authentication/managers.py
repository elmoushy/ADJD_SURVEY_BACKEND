"""
Oracle-compatible managers for the authentication app.

These managers provide Oracle-compatible database operations by using
hash fields instead of direct encrypted field queries.
"""

import hashlib
from django.contrib.auth.models import BaseUserManager
from django.db import models


class OracleCompatibleUserManager(BaseUserManager):
    """
    Custom manager for Oracle-compatible user operations.
    
    This manager uses hash fields for filtering to support Oracle's
    limitations with encrypted fields.
    """
    
    def create_user(self, username, email=None, password=None, auth_type='regular', **extra_fields):
        """
        Create and return a regular user.
        
        Args:
            username: The username (email for regular users, Azure AD Object ID for Azure users)
            email: User's email address
            password: User's password (only for regular users)
            auth_type: 'regular' for email/password, 'azure' for Azure AD
            **extra_fields: Additional fields
            
        Returns:
            User instance
        """
        if not username:
            raise ValueError('The Username field must be set')
        
        email = self.normalize_email(email) if email else ''
        
        # For regular users, username should be the email
        if auth_type == 'regular' and not email:
            if '@' in username:
                email = username
            else:
                raise ValueError('Email must be provided for regular users')
        
        user = self.model(
            username=username,
            email=email,
            auth_type=auth_type,
            **extra_fields
        )
        
        if auth_type == 'regular' and password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # For Azure AD users
            
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """
        Create and return a superuser.
        
        Args:
            username: The username (typically Azure AD Object ID for Azure users)
            email: User's email address
            password: User's password (only for regular users)
            **extra_fields: Additional fields
            
        Returns:
            User instance with admin privileges
        """
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'super_admin')
        extra_fields.setdefault('auth_type', 'regular')  # Default to regular for superuser creation
        
        return self.create_user(username, email, password, **extra_fields)
    
    def get_by_email(self, email):
        """
        Get user by email using hash field for Oracle compatibility.
        
        Args:
            email: Email address to search for
            
        Returns:
            User instance or None
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not email:
            return None
        
        try:
            # Ensure email is a string type
            if not isinstance(email, str):
                email = str(email)
            
            # Generate hash - ensure it's always a string
            email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()
            
            logger.info(f"Looking for user with email: {email}")
            
            # Use explicit TO_CHAR for Oracle to force string comparison
            from .oracle_utils import is_oracle_db
            from django.db import connection
            
            if is_oracle_db():
                # Use raw SQL with N prefix for NVARCHAR2 fields
                # Oracle's oracledb driver has issues with NVARCHAR2 bind parameters
                # The N'...' prefix is required to match NVARCHAR2 columns
                with connection.cursor() as cursor:
                    # Escape single quotes in hash (though hash is hex, this is for safety)
                    safe_hash = email_hash.replace("'", "''")
                    sql = f"""
                        SELECT id FROM auth_user 
                        WHERE email_hash = N'{safe_hash}'
                        AND ROWNUM = 1
                    """
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    
                    if row:
                        user_id = row[0]
                        # Use filter().first() instead of get(pk=) to avoid DoesNotExist issues
                        # This is more robust with Oracle's cursor/transaction handling
                        return self.filter(pk=user_id).first()
                    return None
            else:
                # For non-Oracle databases, use standard ORM
                return self.filter(email_hash=email_hash).first()
            
        except (TypeError, AttributeError, ValueError) as e:
            # Handle isinstance() errors from Django's validation or type annotation issues  
            logger.error(f"Error in get_by_email hash lookup for {email}: {type(e).__name__}: {e}", exc_info=True)
            
            # Fallback to direct email lookup (less Oracle-compatible but works)
            try:
                from django.db.models import Q
                return self.filter(Q(email=email)).first()
            except Exception as fallback_error:
                logger.error(f"Fallback email lookup also failed: {fallback_error}", exc_info=True)
                return None
                
        except Exception as e:
            # Catch-all for any other unexpected errors
            logger.error(f"Unexpected error in get_by_email for {email}: {type(e).__name__}: {e}", exc_info=True)
            return None
    
    def get_by_username(self, username):
        """
        Get user by username using hash field for Oracle compatibility.
        
        Args:
            username: Username to search for
            
        Returns:
            User instance or None
        """
        if not username:
            return None
        
        username_hash = hashlib.sha256(username.encode('utf-8')).hexdigest()
        
        from .oracle_utils import is_oracle_db
        from django.db import connection
        
        if is_oracle_db():
            # Use raw SQL with N prefix for NVARCHAR2 fields
            with connection.cursor() as cursor:
                # Escape single quotes (hash is hex so this is just safety)
                safe_hash = username_hash.replace("'", "''")
                sql = f"""
                    SELECT id FROM auth_user 
                    WHERE username_hash = N'{safe_hash}'
                    AND ROWNUM = 1
                """
                cursor.execute(sql)
                row = cursor.fetchone()
                
                if row:
                    user_id = row[0]
                    return self.filter(pk=user_id).first()
                return None
        else:
            return self.filter(username_hash=username_hash).first()
    
    def filter_by_email(self, email):
        """
        Filter users by email using hash field.
        
        Args:
            email: Email address to filter by
            
        Returns:
            QuerySet of users
        """
        if not email:
            return self.none()
        
        email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()
        
        from .oracle_utils import is_oracle_db
        
        if is_oracle_db():
            # Use raw SQL with N prefix for NVARCHAR2 fields
            from django.db import connection
            with connection.cursor() as cursor:
                safe_hash = email_hash.replace("'", "''")
                cursor.execute(
                    f"SELECT id FROM auth_user WHERE email_hash = N'{safe_hash}'"
                )
                rows = cursor.fetchall()
                if rows:
                    ids = [row[0] for row in rows]
                    return self.filter(id__in=ids)
                return self.none()
        else:
            return self.filter(email_hash=email_hash)
    
    def filter_by_username(self, username):
        """
        Filter users by username using hash field.
        
        Args:
            username: Username to filter by
            
        Returns:
            QuerySet of users
        """
        if not username:
            return self.none()
        
        username_hash = hashlib.sha256(username.encode('utf-8')).hexdigest()
        
        from .oracle_utils import is_oracle_db
        
        if is_oracle_db():
            # Use raw SQL with N prefix for NVARCHAR2 fields
            from django.db import connection
            with connection.cursor() as cursor:
                safe_hash = username_hash.replace("'", "''")
                cursor.execute(
                    f"SELECT id FROM auth_user WHERE username_hash = N'{safe_hash}'"
                )
                rows = cursor.fetchall()
                if rows:
                    ids = [row[0] for row in rows]
                    return self.filter(id__in=ids)
                return self.none()
        else:
            return self.filter(username_hash=username_hash)
    
    def email_exists(self, email):
        """
        Check if a user with the given email exists.
        
        Args:
            email: Email address to check
            
        Returns:
            bool: True if user exists, False otherwise
        """
        if not email:
            return False
        
        email_hash = hashlib.sha256(email.encode('utf-8')).hexdigest()
        
        from .oracle_utils import is_oracle_db
        
        if is_oracle_db():
            # Use raw SQL with N prefix for NVARCHAR2 fields
            from django.db import connection
            with connection.cursor() as cursor:
                safe_hash = email_hash.replace("'", "''")
                cursor.execute(
                    f"SELECT COUNT(*) FROM auth_user WHERE email_hash = N'{safe_hash}'"
                )
                count = cursor.fetchone()[0]
                return count > 0
        else:
            return self.filter(email_hash=email_hash).exists()


class OracleCompatibleSurveyManager(models.Manager):
    """
    Custom manager for Oracle-compatible survey operations.
    
    This manager uses hash fields for filtering encrypted survey titles.
    """
    
    def filter_by_title(self, title):
        """
        Filter surveys by title using hash field.
        
        Args:
            title: Survey title to filter by
            
        Returns:
            QuerySet of surveys
        """
        if not title:
            return self.none()
        title_hash = hashlib.sha256(title.encode('utf-8')).hexdigest()
        return self.filter(title_hash=title_hash)
    
    def get_by_title(self, title):
        """
        Get survey by title using hash field.
        
        Args:
            title: Survey title to search for
            
        Returns:
            Survey instance or None
        """
        if not title:
            return None
        title_hash = hashlib.sha256(title.encode('utf-8')).hexdigest()
        return self.filter(title_hash=title_hash).first()


class OracleCompatibleQuestionManager(models.Manager):
    """
    Custom manager for Oracle-compatible question operations.
    
    This manager uses hash fields for filtering encrypted question text.
    """
    
    def filter_by_text(self, text):
        """
        Filter questions by text using hash field.
        
        Args:
            text: Question text to filter by
            
        Returns:
            QuerySet of questions
        """
        if not text:
            return self.none()
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return self.filter(text_hash=text_hash)
    
    def get_by_text(self, text):
        """
        Get question by text using hash field.
        
        Args:
            text: Question text to search for
            
        Returns:
            Question instance or None
        """
        if not text:
            return None
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        return self.filter(text_hash=text_hash).first()
