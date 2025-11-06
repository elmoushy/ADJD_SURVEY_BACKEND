"""
Serializers for notifications API.

This module defines serializers for notification objects and related operations
with multi-language support.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Notification, NotificationPreference

User = get_user_model()


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notification objects with multi-language support."""
    
    sender_name = serializers.SerializerMethodField()
    title_localized = serializers.SerializerMethodField()
    body_localized = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'sender', 'sender_name',
            'title', 'body', 'title_localized', 'body_localized',
            'notification_type', 'priority', 'action_url', 'metadata',
            'is_read', 'read_at', 'created_at', 'expires_at', 'is_expired',
            'sent_via_websocket', 'websocket_sent_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'sent_via_websocket', 'websocket_sent_at',
            'sender_name', 'title_localized', 'body_localized', 'is_expired'
        ]
    
    def get_sender_name(self, obj):
        """Get sender's full name."""
        if obj.sender:
            return f"{obj.sender.first_name} {obj.sender.last_name}".strip() or obj.sender.email
        return None
    
    def get_title_localized(self, obj):
        """Get localized title based on request language."""
        request = self.context.get('request')
        lang = 'en'
        if request:
            lang = request.query_params.get('lang', 'en')
        return obj.get_title(lang)
    
    def get_body_localized(self, obj):
        """Get localized body based on request language."""
        request = self.context.get('request')
        lang = 'en'
        if request:
            lang = request.query_params.get('lang', 'en')
        return obj.get_body(lang)
    
    def get_is_expired(self, obj):
        """Check if notification is expired."""
        return obj.is_expired()


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences."""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'user', 'websocket_enabled',
            'survey_assigned_enabled', 'survey_completed_enabled',
            'survey_shared_enabled', 'admin_messages_enabled',
            'system_alerts_enabled', 'preferred_language',
            'quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Validate notification preferences."""
        # If quiet hours are enabled, both start and end times must be provided
        if data.get('quiet_hours_enabled'):
            if not data.get('quiet_hours_start') or not data.get('quiet_hours_end'):
                raise serializers.ValidationError(
                    "Both quiet_hours_start and quiet_hours_end are required when quiet hours are enabled."
                )
        
        # Validate preferred language
        if 'preferred_language' in data:
            if data['preferred_language'] not in ['en', 'ar']:
                raise serializers.ValidationError(
                    "Preferred language must be either 'en' or 'ar'."
                )
        
        return data


class BulkNotificationActionSerializer(serializers.Serializer):
    """Serializer for bulk notification actions."""
    
    ACTION_MARK_READ = 'mark_read'
    ACTION_DELETE = 'delete'
    
    ACTION_CHOICES = [
        (ACTION_MARK_READ, 'Mark as Read'),
        (ACTION_DELETE, 'Delete'),
    ]
    
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of notification IDs to perform action on"
    )
    action = serializers.ChoiceField(
        choices=ACTION_CHOICES,
        help_text="Action to perform on selected notifications"
    )
    
    def validate_notification_ids(self, value):
        """Validate that all notification IDs exist and belong to the current user."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")
        
        # Check that all notifications exist and belong to the current user
        existing_notifications = Notification.objects.filter(
            id__in=value,
            recipient=request.user
        )
        
        if existing_notifications.count() != len(value):
            raise serializers.ValidationError(
                "Some notification IDs are invalid or don't belong to you."
            )
        
        return value


class NotificationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating notifications (admin use)."""
    
    recipient_email = serializers.EmailField(write_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'recipient_email', 'title', 'body', 'notification_type',
            'priority', 'action_url', 'metadata', 'expires_at'
        ]
    
    def validate_recipient_email(self, value):
        """Validate that recipient email exists."""
        try:
            user = User.objects.get(email=value)
            return user
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
    
    def validate_title(self, value):
        """Validate title format."""
        if isinstance(value, dict):
            if 'en' not in value:
                raise serializers.ValidationError("Title must contain 'en' key.")
            if not any(value.values()):
                raise serializers.ValidationError("Title cannot be empty.")
        elif not value:
            raise serializers.ValidationError("Title cannot be empty.")
        return value
    
    def validate_body(self, value):
        """Validate body format."""
        if isinstance(value, dict):
            if 'en' not in value:
                raise serializers.ValidationError("Body must contain 'en' key.")
            if not any(value.values()):
                raise serializers.ValidationError("Body cannot be empty.")
        elif not value:
            raise serializers.ValidationError("Body cannot be empty.")
        return value
    
    def create(self, validated_data):
        """Create notification."""
        recipient = validated_data.pop('recipient_email')
        sender = self.context['request'].user
        
        # Convert string titles/bodies to multi-language format if needed
        title = validated_data.get('title')
        body = validated_data.get('body')
        
        if isinstance(title, str):
            validated_data['title'] = {"en": title, "ar": title}
        if isinstance(body, str):
            validated_data['body'] = {"en": body, "ar": body}
        
        return Notification.objects.create(
            recipient=recipient,
            sender=sender,
            **validated_data
        )


class NotificationStatsSerializer(serializers.Serializer):
    """Serializer for notification statistics."""
    
    total_notifications = serializers.IntegerField(read_only=True)
    unread_notifications = serializers.IntegerField(read_only=True)
    read_notifications = serializers.IntegerField(read_only=True)
    notifications_by_type = serializers.DictField(read_only=True)
    notifications_by_priority = serializers.DictField(read_only=True)
    recent_notifications_count = serializers.IntegerField(read_only=True)
    expired_notifications_count = serializers.IntegerField(read_only=True)
