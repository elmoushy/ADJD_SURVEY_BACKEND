"""
JWT WebSocket Middleware for Django Channels

This middleware handles JWT authentication for WebSocket connections
using the same JWT tokens from the authentication system.

NOTE: This entire file is COMMENTED OUT FOR PRODUCTION - WebSocket functionality is disabled
"""

# WebSocket functionality COMMENTED OUT FOR PRODUCTION
# All code below is disabled for production deployment

from urllib.parse import parse_qs
# from channels.middleware import BaseMiddleware  # COMMENTED OUT FOR PRODUCTION
# from channels.db import database_sync_to_async  # COMMENTED OUT FOR PRODUCTION
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import jwt
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_by_id(user_id):
    """Get user by ID from database."""
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTWebSocketMiddleware(BaseMiddleware):
    """
    JWT WebSocket authentication middleware.
    
    Authenticates WebSocket connections using JWT tokens passed as query parameters.
    """
    
    async def __call__(self, scope, receive, send):
        """
        Authenticate WebSocket connection using JWT token.
        
        Token can be passed as:
        - Query parameter: ?token=jwt_token
        - Authorization header: Authorization: Bearer jwt_token
        """
        
        # Only process WebSocket connections
        if scope["type"] != "websocket":
            return await super().__call__(scope, receive, send)
        
        # Extract token from query parameters or headers
        token = None
        
        # Try to get token from query parameters first
        query_string = scope.get("query_string", b"").decode()
        if query_string:
            query_params = parse_qs(query_string)
            if "token" in query_params:
                token = query_params["token"][0]
        
        # Try to get token from headers if not in query params
        if not token:
            headers = dict(scope.get("headers", []))
            if b"authorization" in headers:
                auth_header = headers[b"authorization"].decode()
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Set default user
        scope["user"] = AnonymousUser()
        
        if token:
            try:
                # Validate the token
                validated_token = UntypedToken(token)
                
                # Extract user ID from token
                user_id = validated_token.get("user_id")
                if user_id:
                    # Get user from database
                    user = await get_user_by_id(user_id)
                    if user and not isinstance(user, AnonymousUser):
                        scope["user"] = user
                        logger.info(f"WebSocket authenticated user: {user.email}")
                    else:
                        logger.warning(f"WebSocket: User not found for ID {user_id}")
                else:
                    logger.warning("WebSocket: No user_id in token")
                    
            except (InvalidToken, TokenError) as e:
                logger.warning(f"WebSocket JWT validation failed: {e}")
            except Exception as e:
                logger.error(f"WebSocket authentication error: {e}")
        
        # Continue with the connection
        return await super().__call__(scope, receive, send)
