"""
Custom managers for Email Communication models
Provides database-agnostic query methods following project patterns
"""
from django.db import models
import hashlib


class CostCenterManager(models.Manager):
    """Custom manager for CostCenter with hash-based queries"""
    
    def get_by_code(self, code):
        """Get cost center by code (database-portable)"""
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        return self.get(cost_center_code_hash=code_hash)
    
    def filter_by_code(self, code):
        """Filter cost centers by code (database-portable)"""
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        return self.filter(cost_center_code_hash=code_hash)
    
    def active(self):
        """Get active cost centers"""
        return self.filter(is_active=True)
    
    def with_user(self, user):
        """Get cost centers that include a specific user"""
        return self.filter(users=user, is_active=True)


class EmailTemplateManager(models.Manager):
    """Custom manager for EmailTemplate"""
    
    def active(self):
        """Get active templates"""
        return self.filter(is_active=True)
    
    def by_category(self, category):
        """Get templates by category"""
        return self.filter(category=category, is_active=True)


class EmailDraftManager(models.Manager):
    """Custom manager for EmailDraft"""
    
    def for_user(self, user):
        """Get non-deleted drafts for a user"""
        return self.filter(user=user, is_deleted=False)
    
    def get_queryset(self):
        """Override to exclude deleted by default"""
        return super().get_queryset().filter(is_deleted=False)


class EmailLogManager(models.Manager):
    """Custom manager for EmailLog"""
    
    def sent_by_user(self, user):
        """Get emails sent by user (Outbox)"""
        return self.filter(user=user, email_type='SENT')
    
    def successful(self):
        """Get successful emails"""
        return self.filter(email_status='SUCCESS')
    
    def failed(self):
        """Get failed emails"""
        return self.filter(email_status='FAILED')
    
    def for_cost_center(self, cost_center):
        """Get emails for a specific cost center"""
        return self.filter(cost_center=cost_center)


class EmailRecipientViewManager(models.Manager):
    """Custom manager for EmailRecipientView (Inbox)"""
    
    def inbox_for_user(self, user):
        """Get inbox emails for user"""
        return self.filter(recipient_user=user, is_archived=False)
    
    def unread_for_user(self, user):
        """Get unread emails for user"""
        return self.filter(recipient_user=user, is_read=False, is_archived=False)
    
    def starred_for_user(self, user):
        """Get starred emails for user"""
        return self.filter(recipient_user=user, is_starred=True, is_archived=False)
    
    def archived_for_user(self, user):
        """Get archived emails for user"""
        return self.filter(recipient_user=user, is_archived=True)
    
    def unread_count(self, user):
        """Get count of unread emails"""
        return self.unread_for_user(user).count()
