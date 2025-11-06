#!/usr/bin/env python3
"""
Test script for WebSocket pong functionality.

This script demonstrates how the WebSocket consumer sends pong responses
when new notifications are received.
"""

import asyncio
import json
import websockets
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_websocket_pong():
    """
    Test WebSocket connection and pong responses.
    
    This function:
    1. Connects to the WebSocket
    2. Sends authentication (if needed)
    3. Configures pong behavior
    4. Listens for notifications and pong responses
    5. Sends periodic pings
    """
    
    # WebSocket URL - adjust as needed for your setup
    websocket_url = "ws://localhost:8000/ws/notifications/"
    
    try:
        async with websockets.connect(websocket_url) as websocket:
            logger.info("Connected to WebSocket")
            
            # Listen for initial connection message
            initial_message = await websocket.recv()
            data = json.loads(initial_message)
            logger.info(f"Connection established: {data}")
            
            # Configure pong behavior - enable pong on notifications
            config_message = {
                "type": "configure_pong",
                "send_pong_on_notification": True
            }
            await websocket.send(json.dumps(config_message))
            logger.info("Configured pong behavior")
            
            # Get unread count
            unread_count_message = {"type": "get_unread_count"}
            await websocket.send(json.dumps(unread_count_message))
            logger.info("Requested unread count")
            
            # Listen for messages
            message_count = 0
            ping_count = 0
            
            while message_count < 10:  # Listen for up to 10 messages
                try:
                    # Send periodic pings
                    if ping_count % 5 == 0:
                        ping_message = {
                            "type": "ping",
                            "timestamp": datetime.now().isoformat()
                        }
                        await websocket.send(json.dumps(ping_message))
                        logger.info(f"Sent ping #{ping_count // 5 + 1}")
                    
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    message_type = data.get('type')
                    
                    if message_type == 'pong':
                        trigger = data.get('trigger', 'unknown')
                        if trigger == 'new_notification':
                            logger.info(f"📨 PONG received for new notification: {data.get('notification_id')}")
                        elif trigger == 'ping':
                            logger.info(f"🏓 PONG received for ping")
                        else:
                            logger.info(f"🏓 PONG received (trigger: {trigger})")
                    
                    elif message_type == 'new_notification':
                        notification = data.get('notification', {})
                        logger.info(f"🔔 New notification: {notification.get('title', 'No title')}")
                    
                    elif message_type == 'unread_count':
                        count = data.get('count', 0)
                        logger.info(f"📊 Unread count: {count}")
                    
                    elif message_type == 'pong_configuration_updated':
                        logger.info(f"⚙️  Pong configuration updated: {data}")
                    
                    elif message_type == 'error':
                        logger.error(f"❌ Error: {data.get('message')}")
                    
                    else:
                        logger.info(f"📄 Message ({message_type}): {data}")
                    
                    message_count += 1
                    ping_count += 1
                    
                except asyncio.TimeoutError:
                    logger.info("⏰ No message received in 5 seconds, sending ping...")
                    ping_message = {
                        "type": "ping",
                        "timestamp": datetime.now().isoformat()
                    }
                    await websocket.send(json.dumps(ping_message))
                    ping_count += 1
                    
                except json.JSONDecodeError:
                    logger.error("❌ Invalid JSON received")
                    message_count += 1
                    ping_count += 1
                
                except Exception as e:
                    logger.error(f"❌ Error receiving message: {e}")
                    break
            
            logger.info("Test completed successfully")
    
    except websockets.exceptions.ConnectionClosed:
        logger.error("❌ WebSocket connection closed unexpectedly")
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")


async def test_pong_configuration():
    """
    Test different pong configurations.
    """
    websocket_url = "ws://localhost:8000/ws/notifications/"
    
    try:
        async with websockets.connect(websocket_url) as websocket:
            logger.info("Connected for pong configuration test")
            
            # Listen for initial connection message
            initial_message = await websocket.recv()
            logger.info(f"Initial: {json.loads(initial_message)}")
            
            # Test 1: Enable pong on notifications
            logger.info("\n--- Test 1: Enable pong on notifications ---")
            config_message = {
                "type": "configure_pong",
                "send_pong_on_notification": True
            }
            await websocket.send(json.dumps(config_message))
            
            response = await websocket.recv()
            logger.info(f"Config response: {json.loads(response)}")
            
            # Wait for any notifications
            await asyncio.sleep(2)
            
            # Test 2: Disable pong on notifications
            logger.info("\n--- Test 2: Disable pong on notifications ---")
            config_message = {
                "type": "configure_pong",
                "send_pong_on_notification": False
            }
            await websocket.send(json.dumps(config_message))
            
            response = await websocket.recv()
            logger.info(f"Config response: {json.loads(response)}")
            
            # Wait for any notifications
            await asyncio.sleep(2)
            
            # Test regular ping (should always work)
            logger.info("\n--- Test 3: Regular ping ---")
            ping_message = {
                "type": "ping",
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(ping_message))
            
            response = await websocket.recv()
            pong_data = json.loads(response)
            if pong_data.get('type') == 'pong':
                logger.info(f"✅ Ping/Pong working: {pong_data}")
            else:
                logger.error(f"❌ Expected pong, got: {pong_data}")
            
            logger.info("Configuration test completed")
    
    except Exception as e:
        logger.error(f"❌ Configuration test error: {e}")


if __name__ == "__main__":
    print("WebSocket Pong Test")
    print("==================")
    print("This script tests the WebSocket pong functionality.")
    print("Make sure your Django server is running with WebSocket support.")
    print()
    
    choice = input("Choose test: (1) Basic pong test, (2) Configuration test, (3) Both: ")
    
    if choice == "1":
        asyncio.run(test_websocket_pong())
    elif choice == "2":
        asyncio.run(test_pong_configuration())
    elif choice == "3":
        asyncio.run(test_pong_configuration())
        print("\n" + "="*50 + "\n")
        asyncio.run(test_websocket_pong())
    else:
        print("Invalid choice. Running basic test...")
        asyncio.run(test_websocket_pong())
