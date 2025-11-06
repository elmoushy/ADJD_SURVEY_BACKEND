"""
Notification models for real-time notifications system.

This module defines the models for managing notifications and user preferences
with multi-language support.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import hashlib
import json
import uuid
from typing import Dict, Any

User = get_user_model()


class Notification(models.Model):
    """
    Model to store notifications for users with multi-language support.
    
    Supports various notification types and channels.
    """
    
    # Notification Types
    TYPE_SURVEY_ASSIGNED = 'survey_assigned'
    TYPE_SURVEY_COMPLETED = 'survey_completed'
    TYPE_SURVEY_SHARED = 'survey_shared'
    TYPE_SURVEY_UPDATED = 'survey_updated'
    TYPE_SURVEY_DELETED = 'survey_deleted'
    TYPE_ADMIN_MESSAGE = 'admin_message'
    TYPE_SYSTEM_ALERT = 'system_alert'
    TYPE_USER_MENTION = 'user_mention'
    TYPE_GROUP_INVITATION = 'group_invitation'
    TYPE_RESPONSE_RECEIVED = 'response_received'
    
    NOTIFICATION_TYPES = [
        (TYPE_SURVEY_ASSIGNED, 'Survey Assigned'),
        (TYPE_SURVEY_COMPLETED, 'Survey Completed'),
        (TYPE_SURVEY_SHARED, 'Survey Shared'),
        (TYPE_SURVEY_UPDATED, 'Survey Updated'),
        (TYPE_SURVEY_DELETED, 'Survey Deleted'),
        (TYPE_ADMIN_MESSAGE, 'Admin Message'),
        (TYPE_SYSTEM_ALERT, 'System Alert'),
        (TYPE_USER_MENTION, 'User Mention'),
        (TYPE_GROUP_INVITATION, 'Group Invitation'),
        (TYPE_RESPONSE_RECEIVED, 'Response Received'),
    ]
    
    # Priority Levels
    PRIORITY_LOW = 'low'
    PRIORITY_NORMAL = 'normal'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_NORMAL, 'Normal'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text='User who will receive this notification'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        help_text='User who triggered this notification (optional)'
    )
    
    # Notification Content (Multi-language support)
    title = models.JSONField(
        help_text='Notification title in multiple languages {"en": "...", "ar": "..."}'
    )
    body = models.JSONField(
        help_text='Notification body in multiple languages {"en": "...", "ar": "..."}'
    )
    
    # Notification Metadata
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default=TYPE_ADMIN_MESSAGE,
        help_text='Type of notification'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
        help_text='Priority level of the notification'
    )
    
    # Optional URL for action
    action_url = models.URLField(
        blank=True,
        null=True,
        help_text='Optional URL to navigate when notification is clicked'
    )
    
    # Metadata for additional context
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional metadata as JSON (survey_id, response_id, etc.)'
    )
    
    # Status fields
    is_read = models.BooleanField(
        default=False,
        help_text='Whether the notification has been read'
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the notification was read'
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the notification was created'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the notification expires (optional)'
    )
    
    # Delivery tracking
    sent_via_websocket = models.BooleanField(
        default=False,
        help_text='Whether notification was sent via WebSocket'
    )
    websocket_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When notification was sent via WebSocket'
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['recipient', 'created_at']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['expires_at']),
        ]
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
    
    def __str__(self):
        title_text = self.get_title('en')
        return f"{title_text} - {self.recipient.email}"
    
    def get_title(self, lang: str = 'en') -> str:
        """Get notification title in specified language."""
        if isinstance(self.title, dict):
            return self.title.get(lang, self.title.get('en', ''))
        return str(self.title)
    
    def get_body(self, lang: str = 'en') -> str:
        """Get notification body in specified language."""
        if isinstance(self.body, dict):
            return self.body.get(lang, self.body.get('en', ''))
        return str(self.body)
    
    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def to_websocket_dict(self, lang: str = 'en') -> Dict[str, Any]:
        """Convert notification to dictionary for WebSocket transmission."""
        return {
            'id': str(self.id),
            'title': self.get_title(lang),
            'body': self.get_body(lang),
            'type': self.notification_type,
            'priority': self.priority,
            'action_url': self.action_url,
            'metadata': self.metadata,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'sender': {
                'id': self.sender.id if self.sender else None,
                'email': self.sender.email if self.sender else None,
                'name': f"{self.sender.first_name} {self.sender.last_name}".strip() if self.sender else None
            } if self.sender else None
        }


class NotificationPreference(models.Model):
    """
    Model to store user notification preferences.
    
    Controls which types of notifications a user wants to receive
    and through which channels.
    """
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        help_text='User these preferences belong to'
    )
    
    # WebSocket/Real-time preferences
    websocket_enabled = models.BooleanField(
        default=True,
        help_text='Receive real-time notifications via WebSocket'
    )
    
    # Notification type preferences
    survey_assigned_enabled = models.BooleanField(
        default=True,
        help_text='Receive notifications when surveys are assigned'
    )
    survey_completed_enabled = models.BooleanField(
        default=True,
        help_text='Receive notifications when surveys are completed'
    )
    survey_shared_enabled = models.BooleanField(
        default=True,
        help_text='Receive notifications when surveys are shared'
    )
    admin_messages_enabled = models.BooleanField(
        default=True,
        help_text='Receive admin messages'
    )
    system_alerts_enabled = models.BooleanField(
        default=True,
        help_text='Receive system alerts'
    )
    
    # Preferred language
    preferred_language = models.CharField(
        max_length=5,
        choices=[('en', 'English'), ('ar', 'Arabic')],
        default='en',
        help_text='Preferred language for notifications'
    )
    
    # Quiet hours
    quiet_hours_enabled = models.BooleanField(
        default=False,
        help_text='Enable quiet hours (no notifications during specified time)'
    )
    quiet_hours_start = models.TimeField(
        null=True,
        blank=True,
        help_text='Start time for quiet hours (UAE timezone)'
    )
    quiet_hours_end = models.TimeField(
        null=True,
        blank=True,
        help_text='End time for quiet hours (UAE timezone)'
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text='When preferences were created'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='When preferences were last updated'
    )
    
    class Meta:
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'
    
    def __str__(self):
        return f"Notification preferences for {self.user.email}"
    
    def should_receive_notification(self, notification_type: str) -> bool:
        """Check if user should receive a specific type of notification."""
        type_mapping = {
            Notification.TYPE_SURVEY_ASSIGNED: self.survey_assigned_enabled,
            Notification.TYPE_SURVEY_COMPLETED: self.survey_completed_enabled,
            Notification.TYPE_SURVEY_SHARED: self.survey_shared_enabled,
            Notification.TYPE_ADMIN_MESSAGE: self.admin_messages_enabled,
            Notification.TYPE_SYSTEM_ALERT: self.system_alerts_enabled,
        }
        return type_mapping.get(notification_type, True)
    
    def is_in_quiet_hours(self) -> bool:
        """Check if current time is within user's quiet hours."""
        if not self.quiet_hours_enabled or not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        # Get current UAE time
        from django.utils import timezone as django_timezone
        import pytz
        
        uae_tz = pytz.timezone('Asia/Dubai')
        current_time = django_timezone.now().astimezone(uae_tz).time()
        
        if self.quiet_hours_start <= self.quiet_hours_end:
            # Same day range (e.g., 22:00 - 06:00 next day)
            return self.quiet_hours_start <= current_time <= self.quiet_hours_end
        else:
            # Overnight range (e.g., 22:00 - 06:00 next day)
            return current_time >= self.quiet_hours_start or current_time <= self.quiet_hours_end
