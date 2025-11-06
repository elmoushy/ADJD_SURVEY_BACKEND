"""
Simple WebSocket consumer for testing without authentication.

NOTE: This entire file is COMMENTED OUT FOR PRODUCTION - WebSocket functionality is disabled
"""

# WebSocket functionality COMMENTED OUT FOR PRODUCTION
# All code below is disabled for production deployment

import json
import logging
# from channels.generic.websocket import AsyncWebsocketConsumer  # COMMENTED OUT FOR PRODUCTION

logger = logging.getLogger(__name__)


class TestNotificationsConsumer(AsyncWebsocketConsumer):
    """
    Simple WebSocket consumer for testing.
    """
    
    async def connect(self):
        """Accept WebSocket connection without authentication."""
        logger.info("WebSocket connection attempt")
        await self.accept()
        logger.info("WebSocket connection accepted")
        
        # Send a welcome message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'WebSocket connection established successfully!'
        }))

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        logger.info(f"WebSocket disconnected with code: {close_code}")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        logger.info(f"WebSocket message received: {text_data}")
        try:
            data = json.loads(text_data)
            # Echo the message back
            await self.send(text_data=json.dumps({
                'type': 'echo',
                'message': f"Echo: {data.get('message', 'No message')}"
            }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
