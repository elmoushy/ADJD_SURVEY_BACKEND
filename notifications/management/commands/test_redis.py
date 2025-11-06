"""
Management command to test Redis connection and WebSocket functionality.

This command verifies that Redis is properly configured and that the
notification system can connect to Redis and send messages via WebSockets.

NOTE: WebSocket functionality is COMMENTED OUT FOR PRODUCTION
"""

import asyncio
import json
import redis
from django.core.management.base import BaseCommand
from django.conf import settings
# from channels.layers import get_channel_layer  # COMMENTED OUT FOR PRODUCTION
# from channels_redis.core import RedisChannelLayer  # COMMENTED OUT FOR PRODUCTION


class Command(BaseCommand):
    help = 'Test Redis connection and WebSocket functionality'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--host',
            type=str,
            default='127.0.0.1',
            help='Redis host (default: 127.0.0.1)'
        )
        
        parser.add_argument(
            '--port',
            type=int,
            default=6379,
            help='Redis port (default: 6379)'
        )
        
        parser.add_argument(
            '--test-websocket',
            action='store_true',
            help='Test WebSocket message sending via channels'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        host = options['host']
        port = options['port']
        test_websocket = options['test_websocket']
        
        self.stdout.write("=== Redis Connection Test ===")
        
        # Test 1: Basic Redis connection
        redis_working = self.test_redis_connection(host, port)
        
        if not redis_working:
            self.stdout.write(
                self.style.ERROR("Redis connection failed. Please ensure Redis is running.")
            )
            self.stdout.write("Quick start with Docker:")
            self.stdout.write("  docker run --name redis-test -p 6379:6379 -d redis:7-alpine")
            return
        
        # Test 2: Django Channels Redis configuration
        channels_working = self.test_django_channels_redis()
        
        if not channels_working:
            self.stdout.write(
                self.style.ERROR("Django Channels Redis configuration failed.")
            )
            return
        
        # Test 3: WebSocket message sending (optional)
        if test_websocket:
            self.stdout.write("\n=== WebSocket Message Test ===")
            asyncio.run(self.test_websocket_messaging())
        
        self.stdout.write(
            self.style.SUCCESS("\n✓ All Redis tests passed successfully!")
        )
        
        self.stdout.write("\nNext steps:")
        self.stdout.write("1. Start Django server: python manage.py runserver")
        self.stdout.write("2. Test notifications: python manage.py test_notifications")
        self.stdout.write("3. Open browser to test WebSocket: http://localhost:8000/")
    
    def test_redis_connection(self, host, port):
        """Test basic Redis connection."""
        try:
            r = redis.Redis(host=host, port=port, db=0, decode_responses=True)
            
            # Test ping
            response = r.ping()
            if response:
                self.stdout.write(self.style.SUCCESS(f"✓ Redis ping successful ({host}:{port})"))
            
            # Test set/get
            test_key = "weaponcloud_test"
            test_value = "connection_test"
            r.set(test_key, test_value, ex=60)  # Expire in 60 seconds
            retrieved = r.get(test_key)
            
            if retrieved == test_value:
                self.stdout.write(self.style.SUCCESS("✓ Redis set/get operations working"))
            else:
                self.stdout.write(self.style.ERROR("✗ Redis set/get operations failed"))
                return False
            
            # Test pub/sub
            pubsub = r.pubsub()
            pubsub.subscribe('test_channel')
            r.publish('test_channel', 'test_message')
            
            # Clean up test key
            r.delete(test_key)
            pubsub.close()
            
            self.stdout.write(self.style.SUCCESS("✓ Redis pub/sub operations working"))
            
            # Show Redis info
            info = r.info()
            self.stdout.write(f"Redis version: {info.get('redis_version', 'Unknown')}")
            self.stdout.write(f"Connected clients: {info.get('connected_clients', 'Unknown')}")
            self.stdout.write(f"Used memory: {info.get('used_memory_human', 'Unknown')}")
            
            return True
            
        except redis.ConnectionError as e:
            self.stdout.write(self.style.ERROR(f"✗ Redis connection error: {e}"))
            return False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Redis test error: {e}"))
            return False
    
    def test_django_channels_redis(self):
        """Test Django Channels Redis configuration."""
        # WebSocket functionality COMMENTED OUT FOR PRODUCTION
        self.stdout.write(self.style.WARNING("✗ Django Channels Redis testing is disabled for production"))
        return False
        
        # try:
        #     channel_layer = get_channel_layer()
        #     
        #     if not isinstance(channel_layer, RedisChannelLayer):
        #         self.stdout.write(
        #             self.style.ERROR(
        #                 f"✗ Channel layer is not RedisChannelLayer: {type(channel_layer)}"
        #             )
        #         )
        #         return False
        #     
        #     self.stdout.write(self.style.SUCCESS("✓ Django Channels Redis layer configured"))
        #     
        #     # Test channel layer connection
        #     asyncio.run(self.test_channel_layer_async(channel_layer))
        #     
        #     return True
        #     
        # except Exception as e:
        #     self.stdout.write(self.style.ERROR(f"✗ Django Channels Redis test error: {e}"))
        #     return False
    
    async def test_channel_layer_async(self, channel_layer):
        """Test channel layer async operations."""
        try:
            test_group = "test_group"
            test_channel = "test.channel.123"
            test_message = {
                "type": "test.message",
                "message": "Hello from Redis test!"
            }
            
            # Test group add/discard
            await channel_layer.group_add(test_group, test_channel)
            self.stdout.write(self.style.SUCCESS("✓ Channel layer group add working"))
            
            # Test group send
            await channel_layer.group_send(test_group, test_message)
            self.stdout.write(self.style.SUCCESS("✓ Channel layer group send working"))
            
            # Test receive
            message = await channel_layer.receive(test_channel)
            if message and message.get('message') == test_message['message']:
                self.stdout.write(self.style.SUCCESS("✓ Channel layer receive working"))
            else:
                self.stdout.write(self.style.WARNING("⚠ Channel layer receive test incomplete"))
            
            # Cleanup
            await channel_layer.group_discard(test_group, test_channel)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Channel layer async test error: {e}"))
    
    async def test_websocket_messaging(self):
        """Test WebSocket message sending through the notification system."""
        try:
            from django.contrib.auth import get_user_model
            from notifications.services import NotificationService
            from notifications.models import Notification
            
            User = get_user_model()
            
            # Get the first user for testing
            user = User.objects.first()
            if not user:
                self.stdout.write(
                    self.style.ERROR("✗ No users found. Create a user first for WebSocket testing.")
                )
                return
            
            # Create a test notification
            notification = NotificationService.create_admin_message_notification(
                recipient=user,
                title={'en': 'Redis Test Notification', 'ar': 'إشعار اختبار Redis'},
                message={
                    'en': 'This is a test notification to verify Redis and WebSocket functionality.',
                    'ar': 'هذا إشعار تجريبي للتحقق من وظائف Redis و WebSocket.'
                },
                priority=Notification.PRIORITY_HIGH
            )
            
            if notification and notification.sent_via_websocket:
                self.stdout.write(
                    self.style.SUCCESS("✓ WebSocket message sent successfully via Redis")
                )
                self.stdout.write(f"Notification ID: {notification.id}")
            else:
                self.stdout.write(
                    self.style.WARNING("⚠ Notification created but WebSocket delivery may have failed")
                )
                self.stdout.write("This is normal if no WebSocket clients are connected.")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ WebSocket messaging test error: {e}"))
