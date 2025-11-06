"""
Django admin configuration for notifications.

This module provides admin interface for managing notifications and preferences.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model."""
    
    list_display = [
        'title_display', 'recipient_email', 'sender_email', 
        'notification_type', 'priority', 'is_read', 'created_at',
        'websocket_status', 'expired_status'
    ]
    
    list_filter = [
        'notification_type', 'priority', 'is_read', 
        'sent_via_websocket', 'created_at'
    ]
    
    search_fields = [
        'recipient__email', 'recipient__first_name', 'recipient__last_name',
        'sender__email', 'sender__first_name', 'sender__last_name',
        'title', 'body'
    ]
    
    readonly_fields = [
        'id', 'created_at', 'read_at', 'websocket_sent_at',
        'sent_via_websocket', 'title_display', 'body_display'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'recipient', 'sender', 'title_display', 'body_display')
        }),
        ('Notification Details', {
            'fields': ('notification_type', 'priority', 'action_url', 'metadata')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'expires_at')
        }),
        ('Delivery Tracking', {
            'fields': ('sent_via_websocket', 'websocket_sent_at')
        }),
        ('Raw Data (Advanced)', {
            'classes': ('collapse',),
            'fields': ('title', 'body'),
            'description': 'Raw multi-language data stored in database'
        }),
    )
    
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    def title_display(self, obj):
        """Display title in English with length info."""
        title_en = obj.get_title('en')
        title_ar = obj.get_title('ar')
        if title_en != title_ar:
            return format_html(
                '<strong>EN:</strong> {} <br><strong>AR:</strong> {}',
                title_en[:50] + ('...' if len(title_en) > 50 else ''),
                title_ar[:50] + ('...' if len(title_ar) > 50 else '')
            )
        return title_en[:50] + ('...' if len(title_en) > 50 else '')
    title_display.short_description = 'Title'
    
    def body_display(self, obj):
        """Display body in English with length info."""
        body_en = obj.get_body('en')
        body_ar = obj.get_body('ar')
        if body_en != body_ar:
            return format_html(
                '<strong>EN:</strong> {} <br><strong>AR:</strong> {}',
                body_en[:100] + ('...' if len(body_en) > 100 else ''),
                body_ar[:100] + ('...' if len(body_ar) > 100 else '')
            )
        return body_en[:100] + ('...' if len(body_en) > 100 else '')
    body_display.short_description = 'Body'
    
    def recipient_email(self, obj):
        """Display recipient email with link to user."""
        url = reverse('admin:authentication_user_change', args=[obj.recipient.id])
        return format_html('<a href="{}">{}</a>', url, obj.recipient.email)
    recipient_email.short_description = 'Recipient'
    recipient_email.admin_order_field = 'recipient__email'
    
    def sender_email(self, obj):
        """Display sender email with link to user."""
        if obj.sender:
            url = reverse('admin:authentication_user_change', args=[obj.sender.id])
            return format_html('<a href="{}">{}</a>', url, obj.sender.email)
        return '-'
    sender_email.short_description = 'Sender'
    sender_email.admin_order_field = 'sender__email'
    
    def websocket_status(self, obj):
        """Display WebSocket delivery status."""
        if obj.sent_via_websocket:
            return format_html(
                '<span style="color: green;">✓ Sent at {}</span>',
                obj.websocket_sent_at.strftime('%H:%M:%S') if obj.websocket_sent_at else 'Unknown'
            )
        return format_html('<span style="color: orange;">⚠ Not sent</span>')
    websocket_status.short_description = 'WebSocket'
    
    def expired_status(self, obj):
        """Display expiration status."""
        if not obj.expires_at:
            return '-'
        
        if obj.is_expired():
            return format_html('<span style="color: red;">Expired</span>')
        return format_html('<span style="color: green;">Active</span>')
    expired_status.short_description = 'Status'
    
    actions = ['mark_as_read', 'mark_as_unread', 'resend_websocket']
    
    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read."""
        updated = 0
        for notification in queryset.filter(is_read=False):
            notification.mark_as_read()
            updated += 1
        
        self.message_user(
            request,
            f'Marked {updated} notifications as read.'
        )
    mark_as_read.short_description = 'Mark selected notifications as read'
    
    def mark_as_unread(self, request, queryset):
        """Mark selected notifications as unread."""
        updated = queryset.filter(is_read=True).update(
            is_read=False,
            read_at=None
        )
        
        self.message_user(
            request,
            f'Marked {updated} notifications as unread.'
        )
    mark_as_unread.short_description = 'Mark selected notifications as unread'
    
    def resend_websocket(self, request, queryset):
        """Resend notifications via WebSocket."""
        from .services import NotificationService
        
        sent_count = 0
        for notification in queryset:
            try:
                NotificationService.send_websocket_notification(notification)
                sent_count += 1
            except Exception:
                pass
        
        self.message_user(
            request,
            f'Attempted to resend {sent_count} notifications via WebSocket.'
        )
    resend_websocket.short_description = 'Resend via WebSocket'


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for NotificationPreference model."""
    
    list_display = [
        'user_email', 'user_role', 'preferred_language',
        'websocket_enabled', 'quiet_hours_enabled',
        'enabled_types_summary', 'updated_at'
    ]
    
    list_filter = [
        'preferred_language', 'websocket_enabled', 'quiet_hours_enabled',
        'survey_assigned_enabled', 'survey_completed_enabled',
        'admin_messages_enabled', 'updated_at'
    ]
    
    search_fields = [
        'user__email', 'user__first_name', 'user__last_name'
    ]
    
    readonly_fields = ['user', 'created_at', 'updated_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'preferred_language')
        }),
        ('Delivery Preferences', {
            'fields': ('websocket_enabled',)
        }),
        ('Notification Types', {
            'fields': (
                'survey_assigned_enabled', 'survey_completed_enabled',
                'survey_shared_enabled', 'admin_messages_enabled',
                'system_alerts_enabled'
            )
        }),
        ('Quiet Hours', {
            'fields': ('quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end'),
            'description': 'Times are in UAE timezone (Asia/Dubai)'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def user_email(self, obj):
        """Display user email with link."""
        url = reverse('admin:authentication_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def user_role(self, obj):
        """Display user role."""
        return obj.user.role.title() if hasattr(obj.user, 'role') else '-'
    user_role.short_description = 'Role'
    user_role.admin_order_field = 'user__role'
    
    def enabled_types_summary(self, obj):
        """Show summary of enabled notification types."""
        enabled_types = []
        
        if obj.survey_assigned_enabled:
            enabled_types.append('Surveys')
        if obj.survey_completed_enabled:
            enabled_types.append('Completions')
        if obj.admin_messages_enabled:
            enabled_types.append('Admin')
        if obj.system_alerts_enabled:
            enabled_types.append('Alerts')
        
        if enabled_types:
            return ', '.join(enabled_types)
        return format_html('<span style="color: orange;">None enabled</span>')
    enabled_types_summary.short_description = 'Enabled Types'
