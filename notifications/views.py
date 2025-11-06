"""
Views for notifications API.

This module provides REST API endpoints for managing notifications
and user preferences with multi-language support.
"""

from rest_framework import generics, permissions, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
import logging

from .models import Notification, NotificationPreference
from .serializers import (
    NotificationSerializer, 
    NotificationPreferenceSerializer,
    BulkNotificationActionSerializer,
    NotificationCreateSerializer,
    NotificationStatsSerializer
)
from .services import NotificationService

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationPagination(PageNumberPagination):
    """Custom pagination for notifications."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationListView(generics.ListAPIView):
    """
    List notifications for the authenticated user.
    
    Supports filtering by read status, notification type, and priority.
    Supports search by title and body content.
    """
    
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'body']
    ordering_fields = ['created_at', 'priority', 'is_read']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Get notifications for the current user with filters."""
        queryset = Notification.objects.filter(recipient=self.request.user)
        
        # Filter by read status
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')
        
        # Filter by notification type
        notification_type = self.request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        
        if date_from:
            try:
                from dateutil.parser import parse
                date_from = parse(date_from)
                queryset = queryset.filter(created_at__gte=date_from)
            except (ValueError, TypeError):
                pass
        
        if date_to:
            try:
                from dateutil.parser import parse
                date_to = parse(date_to)
                queryset = queryset.filter(created_at__lte=date_to)
            except (ValueError, TypeError):
                pass
        
        # Exclude expired notifications if requested
        exclude_expired = self.request.query_params.get('exclude_expired', 'false')
        if exclude_expired.lower() == 'true':
            queryset = queryset.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
            )
        
        return queryset.select_related('sender')
    
    def list(self, request, *args, **kwargs):
        """Override list to add metadata."""
        response = super().list(request, *args, **kwargs)
        
        # Add metadata about filters applied
        response.data['meta'] = {
            'filters_applied': {
                'is_read': request.query_params.get('is_read'),
                'type': request.query_params.get('type'),
                'priority': request.query_params.get('priority'),
                'date_from': request.query_params.get('date_from'),
                'date_to': request.query_params.get('date_to'),
                'exclude_expired': request.query_params.get('exclude_expired', 'false'),
            },
            'lang': request.query_params.get('lang', 'en'),
        }
        
        return response


class NotificationDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve and update a specific notification.
    
    Allows marking notifications as read/unread.
    """
    
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get notifications for the current user."""
        return Notification.objects.filter(recipient=self.request.user)
    
    def perform_update(self, serializer):
        """Handle notification update."""
        notification = serializer.save()
        
        # If marking as read and wasn't read before, update read_at timestamp
        if notification.is_read and not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
        
        logger.info(f"Updated notification {notification.id} for user {self.request.user.email}")


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """
    Retrieve, update, or create notification preferences for the authenticated user.
    """
    
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        """Get or create preferences for the current user."""
        preferences, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        if created:
            logger.info(f"Created default notification preferences for user {self.request.user.email}")
        return preferences
    
    def perform_update(self, serializer):
        """Handle preferences update."""
        serializer.save()
        logger.info(f"Updated notification preferences for user {self.request.user.email}")


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def bulk_notification_action(request):
    """
    Perform bulk actions on notifications.
    
    Supported actions:
    - mark_read: Mark selected notifications as read
    - delete: Delete selected notifications
    """
    serializer = BulkNotificationActionSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response({
            'status': 'error',
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    notification_ids = serializer.validated_data['notification_ids']
    action = serializer.validated_data['action']
    
    # Get notifications belonging to the current user
    notifications = Notification.objects.filter(
        id__in=notification_ids,
        recipient=request.user
    )
    
    try:
        if action == BulkNotificationActionSerializer.ACTION_MARK_READ:
            # Mark notifications as read
            updated_count = notifications.filter(is_read=False).update(
                is_read=True,
                read_at=timezone.now()
            )
            
            return Response({
                'status': 'success',
                'message': f'Marked {updated_count} notifications as read',
                'data': {
                    'action': action,
                    'processed_count': updated_count,
                    'total_selected': len(notification_ids)
                }
            })
        
        elif action == BulkNotificationActionSerializer.ACTION_DELETE:
            # Delete notifications
            deleted_count, _ = notifications.delete()
            
            return Response({
                'status': 'success',
                'message': f'Deleted {deleted_count} notifications',
                'data': {
                    'action': action,
                    'processed_count': deleted_count,
                    'total_selected': len(notification_ids)
                }
            })
        
    except Exception as e:
        logger.error(f"Bulk notification action failed: {e}")
        return Response({
            'status': 'error',
            'message': 'Failed to perform bulk action'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def notification_stats(request):
    """
    Get notification statistics for the authenticated user.
    
    Returns counts by read status, type, priority, and recent activity.
    """
    user = request.user
    lang = request.query_params.get('lang', 'en')
    
    try:
        # Get all notifications for the user
        all_notifications = Notification.objects.filter(recipient=user)
        
        # Basic counts
        total_count = all_notifications.count()
        unread_count = all_notifications.filter(is_read=False).count()
        read_count = total_count - unread_count
        
        # Count by notification type
        type_counts = dict(
            all_notifications.values('notification_type')
            .annotate(count=Count('id'))
            .values_list('notification_type', 'count')
        )
        
        # Count by priority
        priority_counts = dict(
            all_notifications.values('priority')
            .annotate(count=Count('id'))
            .values_list('priority', 'count')
        )
        
        # Recent notifications (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_count = all_notifications.filter(created_at__gte=week_ago).count()
        
        # Expired notifications
        expired_count = all_notifications.filter(
            expires_at__isnull=False,
            expires_at__lt=timezone.now()
        ).count()
        
        stats_data = {
            'total_notifications': total_count,
            'unread_notifications': unread_count,
            'read_notifications': read_count,
            'notifications_by_type': type_counts,
            'notifications_by_priority': priority_counts,
            'recent_notifications_count': recent_count,
            'expired_notifications_count': expired_count,
        }
        
        serializer = NotificationStatsSerializer(stats_data)
        
        # Add localized messages
        messages = {
            'total_label': {
                'en': 'Total Notifications',
                'ar': 'إجمالي الإشعارات'
            },
            'unread_label': {
                'en': 'Unread Notifications',
                'ar': 'الإشعارات غير المقروءة'
            },
            'recent_label': {
                'en': 'Recent Notifications (7 days)',
                'ar': 'الإشعارات الحديثة (7 أيام)'
            }
        }
        
        return Response({
            'status': 'success',
            'message': f'Retrieved notification statistics for {user.email}',
            'data': serializer.data,
            'meta': {
                'lang': lang,
                'labels': {key: value.get(lang, value['en']) for key, value in messages.items()},
                'generated_at': timezone.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get notification stats for user {user.email}: {e}")
        return Response({
            'status': 'error',
            'message': 'Failed to retrieve notification statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_all_read(request):
    """
    Mark all notifications as read for the authenticated user.
    """
    try:
        updated_count = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(
            is_read=True,
            read_at=timezone.now()
        )
        
        lang = request.query_params.get('lang', 'en')
        messages = {
            'en': f'Marked {updated_count} notifications as read',
            'ar': f'تم وضع علامة مقروء على {updated_count} إشعار'
        }
        
        return Response({
            'status': 'success',
            'message': messages.get(lang, messages['en']),
            'data': {
                'updated_count': updated_count
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to mark all notifications as read for user {request.user.email}: {e}")
        return Response({
            'status': 'error',
            'message': 'Failed to mark notifications as read'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Admin-only views
class AdminNotificationCreateView(generics.CreateAPIView):
    """
    Create notifications (admin only).
    
    Allows admins to send notifications to specific users.
    """
    
    serializer_class = NotificationCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """Restrict to admin users only."""
        permissions_list = super().get_permissions()
        
        # Check if user is admin or super admin
        if not (hasattr(self.request.user, 'role') and 
                self.request.user.role in ['admin', 'super_admin']):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Admin access required.")
        
        return permissions_list
    
    def perform_create(self, serializer):
        """Create and send notification."""
        notification = serializer.save()
        
        # Send via WebSocket
        NotificationService.send_websocket_notification(notification)
        
        logger.info(
            f"Admin {self.request.user.email} created notification {notification.id} "
            f"for user {notification.recipient.email}"
        )
