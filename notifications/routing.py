"""
WebSocket URL routing for notifications.

This module defines the WebSocket URL patterns for the notifications system.

NOTE: This entire file is COMMENTED OUT FOR PRODUCTION - WebSocket functionality is disabled
"""

# WebSocket functionality COMMENTED OUT FOR PRODUCTION
# All code below is disabled for production deployment

from django.urls import re_path
# from . import consumers  # COMMENTED OUT FOR PRODUCTION
# from . import test_consumers  # COMMENTED OUT FOR PRODUCTION

# WebSocket URL patterns - COMMENTED OUT FOR PRODUCTION
# websocket_urlpatterns = [
#     re_path(r'ws/notifications/$', consumers.NotificationsConsumer.as_asgi()),
#     re_path(r'ws/test/$', test_consumers.TestNotificationsConsumer.as_asgi()),
# ]

# Empty URL patterns for production
websocket_urlpatterns = []
