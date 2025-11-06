/**
 * WebSocket Client for Notification Pong Testing
 * 
 * This JavaScript example shows how to handle WebSocket connections
 * and pong responses from the notifications consumer.
 */

class NotificationWebSocket {
    constructor(websocketUrl, authToken = null) {
        this.websocketUrl = websocketUrl;
        this.authToken = authToken;
        this.websocket = null;
        this.pingInterval = null;
        this.pongOnNotification = true;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        try {
            // Include authentication token in URL if provided
            const url = this.authToken 
                ? `${this.websocketUrl}?token=${this.authToken}`
                : this.websocketUrl;

            this.websocket = new WebSocket(url);

            this.websocket.onopen = (event) => {
                console.log('✅ WebSocket connected:', event);
                this.reconnectAttempts = 0;
                this.startPingInterval();
                this.configurePongBehavior(this.pongOnNotification);
            };

            this.websocket.onmessage = (event) => {
                this.handleMessage(event);
            };

            this.websocket.onclose = (event) => {
                console.log('❌ WebSocket closed:', event.code, event.reason);
                this.stopPingInterval();
                this.attemptReconnect();
            };

            this.websocket.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
            };

        } catch (error) {
            console.error('❌ Failed to connect:', error);
        }
    }

    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            const messageType = data.type;

            switch (messageType) {
                case 'connection_established':
                    console.log('🔗 Connection established:', data);
                    this.onConnectionEstablished(data);
                    break;

                case 'new_notification':
                    console.log('🔔 New notification:', data.notification);
                    this.onNewNotification(data.notification, data.lang);
                    break;

                case 'pong':
                    const trigger = data.trigger;
                    if (trigger === 'new_notification') {
                        console.log('📨 Pong for notification:', data.notification_id);
                        this.onNotificationPong(data);
                    } else if (trigger === 'ping') {
                        console.log('🏓 Pong for ping');
                        this.onPingPong(data);
                    } else {
                        console.log('🏓 Pong (unknown trigger):', data);
                    }
                    break;

                case 'unread_count':
                    console.log('📊 Unread count:', data.count);
                    this.onUnreadCount(data.count);
                    break;

                case 'pong_configuration_updated':
                    console.log('⚙️ Pong configuration updated:', data);
                    this.onPongConfigurationUpdated(data);
                    break;

                case 'notification_marked_read':
                    console.log('✅ Notification marked as read:', data.notification_id);
                    this.onNotificationMarkedRead(data.notification_id);
                    break;

                case 'all_notifications_marked_read':
                    console.log('✅ All notifications marked as read:', data.count);
                    this.onAllNotificationsMarkedRead(data.count);
                    break;

                case 'error':
                    console.error('❌ Server error:', data.message);
                    this.onError(data.message);
                    break;

                default:
                    console.log('📄 Unknown message type:', messageType, data);
            }

        } catch (error) {
            console.error('❌ Failed to parse message:', error, event.data);
        }
    }

    /**
     * Send a message to the WebSocket server
     */
    send(message) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(message));
        } else {
            console.warn('⚠️ WebSocket not connected, message not sent:', message);
        }
    }

    /**
     * Configure pong behavior for notifications
     */
    configurePongBehavior(sendPongOnNotification) {
        this.pongOnNotification = sendPongOnNotification;
        this.send({
            type: 'configure_pong',
            send_pong_on_notification: sendPongOnNotification
        });
    }

    /**
     * Send a ping message
     */
    ping() {
        this.send({
            type: 'ping',
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Mark a notification as read
     */
    markNotificationRead(notificationId) {
        this.send({
            type: 'mark_read',
            notification_id: notificationId
        });
    }

    /**
     * Mark all notifications as read
     */
    markAllNotificationsRead() {
        this.send({
            type: 'mark_all_read'
        });
    }

    /**
     * Get unread notification count
     */
    getUnreadCount() {
        this.send({
            type: 'get_unread_count'
        });
    }

    /**
     * Start sending periodic pings
     */
    startPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
        }
        
        this.pingInterval = setInterval(() => {
            this.ping();
        }, 30000); // Ping every 30 seconds
    }

    /**
     * Stop sending periodic pings
     */
    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    /**
     * Attempt to reconnect to WebSocket
     */
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.pow(2, this.reconnectAttempts) * 1000; // Exponential backoff
            
            console.log(`🔄 Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms...`);
            
            setTimeout(() => {
                this.connect();
            }, delay);
        } else {
            console.error('❌ Max reconnect attempts reached. Connection failed.');
        }
    }

    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        this.stopPingInterval();
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
    }

    // Event handlers (override these in your implementation)
    onConnectionEstablished(data) {
        // Override this method to handle connection establishment
        console.log('Connection established with config:', data);
    }

    onNewNotification(notification, lang) {
        // Override this method to handle new notifications
        console.log('New notification received:', notification);
    }

    onNotificationPong(data) {
        // Override this method to handle pong responses for notifications
        console.log('Notification pong received:', data);
    }

    onPingPong(data) {
        // Override this method to handle pong responses for pings
        console.log('Ping pong received:', data);
    }

    onUnreadCount(count) {
        // Override this method to handle unread count updates
        console.log('Unread count:', count);
    }

    onPongConfigurationUpdated(data) {
        // Override this method to handle pong configuration updates
        console.log('Pong configuration updated:', data);
    }

    onNotificationMarkedRead(notificationId) {
        // Override this method to handle notification read confirmations
        console.log('Notification marked as read:', notificationId);
    }

    onAllNotificationsMarkedRead(count) {
        // Override this method to handle all notifications read confirmations
        console.log('All notifications marked as read:', count);
    }

    onError(message) {
        // Override this method to handle errors
        console.error('Error:', message);
    }
}

// Example usage:
// const notificationWS = new NotificationWebSocket('ws://localhost:8000/ws/notifications/');
// notificationWS.connect();

// Example with custom event handlers:
/*
class MyNotificationHandler extends NotificationWebSocket {
    onNewNotification(notification, lang) {
        // Display notification in UI
        this.showNotificationInUI(notification);
        
        // Play notification sound
        this.playNotificationSound();
    }
    
    onNotificationPong(data) {
        // Handle acknowledgment that notification was received
        console.log('Server acknowledged notification receipt:', data.notification_id);
        
        // Could be used for delivery tracking or reliability features
        this.trackNotificationDelivery(data.notification_id);
    }
    
    onUnreadCount(count) {
        // Update unread count in UI
        document.getElementById('unread-count').textContent = count;
        document.title = count > 0 ? `(${count}) My App` : 'My App';
    }
    
    showNotificationInUI(notification) {
        // Implementation for showing notification in UI
        console.log('Showing notification:', notification.title);
    }
    
    playNotificationSound() {
        // Implementation for playing notification sound
        // new Audio('/static/sounds/notification.mp3').play();
    }
    
    trackNotificationDelivery(notificationId) {
        // Implementation for tracking notification delivery
        console.log('Tracked delivery for:', notificationId);
    }
}

const myNotificationWS = new MyNotificationHandler('ws://localhost:8000/ws/notifications/');
myNotificationWS.connect();
*/
