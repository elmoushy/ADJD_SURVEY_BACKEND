"""
URL patterns for notifications API endpoints.

This module defines the URL routing for the notifications system
following the established patterns from other apps.
"""

from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Notification CRUD
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('<uuid:pk>/', views.NotificationDetailView.as_view(), name='notification-detail'),
    
    # Notification preferences
    path('preferences/', views.NotificationPreferenceView.as_view(), name='notification-preferences'),
    
    # Bulk operations
    path('bulk-action/', views.bulk_notification_action, name='bulk-notification-action'),
    path('mark-all-read/', views.mark_all_read, name='mark-all-read'),
    
    # Statistics
    path('stats/', views.notification_stats, name='notification-stats'),
    
    # Admin endpoints
    path('admin/create/', views.AdminNotificationCreateView.as_view(), name='admin-notification-create'),
]
