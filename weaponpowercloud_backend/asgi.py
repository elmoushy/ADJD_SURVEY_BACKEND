"""
ASGI config for weaponpowercloud_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django
# from channels.routing import ProtocolTypeRouter, URLRouter  # COMMENTED OUT FOR PRODUCTION
from django.core.asgi import get_asgi_application
# from django.urls import re_path  # COMMENTED OUT FOR PRODUCTION

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weaponpowercloud_backend.settings')
django.setup()

# WebSocket imports - COMMENTED OUT FOR PRODUCTION
# from notifications.routing import websocket_urlpatterns
# from notifications.middleware import JWTWebSocketMiddleware
# from notifications.test_consumers import TestNotificationsConsumer
# from notifications.consumers import NotificationsConsumer

django_asgi_app = get_asgi_application()

# WebSocket routing - COMMENTED OUT FOR PRODUCTION
# Separate routing for authenticated and test WebSocket connections
# websocket_routing = URLRouter([
#     # Test route without authentication
#     re_path(r'ws/test/$', TestNotificationsConsumer.as_asgi()),
#     # Authenticated notifications route
#     re_path(r'ws/notifications/$', JWTWebSocketMiddleware(NotificationsConsumer.as_asgi())),
# ])

# Standard ASGI application for production without WebSocket support
application = django_asgi_app

# WebSocket-enabled application - COMMENTED OUT FOR PRODUCTION
# application = ProtocolTypeRouter({
#     "http": django_asgi_app,
#     "websocket": websocket_routing,
# })
