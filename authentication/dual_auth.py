"""
Dual Authentication System for Django REST Framework

This module provides authentication that supports both:
1. Azure AD JWT tokens (existing functionality)
2. Regular JWT tokens for email/password authentication

The system automatically detects the token type and applies the appropriate validation.
"""

import logging
import jwt
from typing import Optional, Tuple
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework import authentication, exceptions
from rest_framework.request import Request

# Import JWT authentication with error handling
try:
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    JWTAuthentication = None
    InvalidToken = Exception
    TokenError = Exception

from .azure_auth import AzureADAuthentication


User = get_user_model()
logger = logging.getLogger(__name__)


class DualAuthentication(authentication.BaseAuthentication):
    """
    Dual authentication class that supports both Azure AD and regular JWT tokens.
    
    This authentication class:
    1. First attempts to authenticate using regular JWT tokens
    2. Falls back to Azure AD JWT authentication if regular JWT fails
    3. Returns None if both methods fail (allowing other auth methods)
    """
    
    def __init__(self):
        if JWT_AVAILABLE:
            self.regular_jwt_auth = JWTAuthentication()
        else:
            self.regular_jwt_auth = None
        self.azure_ad_auth = AzureADAuthentication()
    
    def is_azure_token(self, token: str) -> bool:
        """
        Determine if a token is an Azure AD token by examining its structure.
        
        Args:
            token: The JWT token string
            
        Returns:
            True if it appears to be an Azure AD token, False otherwise
        """
        try:
            # Decode header without verification to check for 'kid'
            unverified_header = jwt.decode(token, options={"verify_signature": False, "verify_header": False})
            header = jwt.get_unverified_header(token)
            
            # Azure AD tokens always have 'kid' in header
            if 'kid' not in header:
                return False
            
            # Decode payload without verification to check the token structure
            unverified_payload = unverified_header
            
            # Azure AD tokens typically have these claims
            azure_claims = ['aud', 'iss', 'tid', 'oid']  # tid = tenant_id, oid = object_id
            
            # Check if it has Azure-specific issuer
            issuer = unverified_payload.get('iss', '')
            if 'login.microsoftonline.com' in issuer or 'sts.windows.net' in issuer:
                return True
            
            # Check for Azure-specific claims
            azure_claim_count = sum(1 for claim in azure_claims if claim in unverified_payload)
            if azure_claim_count >= 3:  # Stricter check - need at least 3 Azure claims
                return True
                
            return False
            
        except Exception:
            # If we can't decode the token, assume it's not Azure
            return False
    
    def authenticate(self, request: Request) -> Optional[Tuple[AbstractBaseUser, str]]:
        """
        Authenticate the request using either regular JWT or Azure AD JWT.
        
        Args:
            request: The HTTP request object
            
        Returns:
            Tuple of (user, token) if authentication succeeds, None otherwise
        """
        # Extract the Authorization header
        auth_header = authentication.get_authorization_header(request).split()
        
        if not auth_header or auth_header[0].lower() != b'bearer':
            return None
            
        if len(auth_header) != 2:
            return None
            
        try:
            token = auth_header[1].decode('utf-8')
        except UnicodeError:
            return None
        
        # Determine token type and try appropriate authentication first
        is_azure = self.is_azure_token(token)
        
        if is_azure:
            # Try Azure AD authentication first for Azure tokens
            logger.debug("Detected Azure AD token, trying Azure AD authentication first")
            try:
                result = self.azure_ad_auth.authenticate(request)
                if result is not None:
                    user, validated_token = result
                    logger.info(f"User {user.email} authenticated with Azure AD")
                    return result
            except exceptions.AuthenticationFailed as e:
                logger.debug(f"Azure AD authentication failed: {e}")
                # Continue to try regular JWT authentication as fallback
                pass
            except Exception as e:
                logger.debug(f"Unexpected error in Azure AD auth: {e}")
                pass
            
            # Try regular JWT as fallback for Azure tokens
            if JWT_AVAILABLE and self.regular_jwt_auth:
                try:
                    result = self.regular_jwt_auth.authenticate(request)
                    if result is not None:
                        user, validated_token = result
                        logger.info(f"User {user.email} authenticated with regular JWT (fallback for Azure token)")
                        return result
                except (InvalidToken, TokenError, exceptions.AuthenticationFailed) as e:
                    logger.debug(f"Regular JWT authentication failed for Azure token: {e}")
                    pass
                except Exception as e:
                    logger.debug(f"Unexpected error in regular JWT auth for Azure token: {e}")
                    pass
        else:
            # Try regular JWT authentication first for non-Azure tokens
            logger.debug("Detected regular JWT token, trying regular JWT authentication first")
            if JWT_AVAILABLE and self.regular_jwt_auth:
                try:
                    result = self.regular_jwt_auth.authenticate(request)
                    if result is not None:
                        user, validated_token = result
                        logger.info(f"User {user.email} authenticated with regular JWT")
                        return result
                except (InvalidToken, TokenError, exceptions.AuthenticationFailed) as e:
                    logger.debug(f"Regular JWT authentication failed: {e}")
                    # Continue to try Azure AD authentication as fallback
                    pass
                except Exception as e:
                    logger.debug(f"Unexpected error in regular JWT auth: {e}")
                    pass
            
            # Try Azure AD authentication as fallback for regular tokens
            try:
                result = self.azure_ad_auth.authenticate(request)
                if result is not None:
                    user, validated_token = result
                    logger.info(f"User {user.email} authenticated with Azure AD (fallback for regular token)")
                    return result
            except exceptions.AuthenticationFailed as e:
                logger.debug(f"Azure AD authentication failed for regular token: {e}")
                pass
            except Exception as e:
                logger.debug(f"Unexpected error in Azure AD auth for regular token: {e}")
                pass
        
        # Both authentication methods failed
        logger.debug("Both Azure AD and regular JWT authentication failed")
        return None

    def authenticate_header(self, request):
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response, or `None` if the
        authentication scheme should return `403 Permission Denied` responses.
        """
        return 'Bearer'


class RegularJWTAuthentication(authentication.BaseAuthentication):
    """
    Custom JWT Authentication that only works with regular users.
    
    This class extends the standard JWT authentication to ensure
    only regular users (not Azure AD users) can use this method.
    """
    
    def __init__(self):
        if JWT_AVAILABLE:
            self.jwt_auth = JWTAuthentication()
        else:
            self.jwt_auth = None
    
    def authenticate(self, request: Request) -> Optional[Tuple[AbstractBaseUser, str]]:
        """
        Authenticate using regular JWT tokens only.
        """
        if not JWT_AVAILABLE or not self.jwt_auth:
            return None
            
        try:
            result = self.jwt_auth.authenticate(request)
            if result is None:
                return None
                
            user, validated_token = result
            
            # Ensure only regular users can use JWT token auth
            if user and user.auth_type != 'regular':
                raise exceptions.AuthenticationFailed('Azure AD users must use Azure AD authentication')
            
            return result
            
        except (InvalidToken, TokenError) as e:
            raise exceptions.AuthenticationFailed(f'Invalid token: {str(e)}')
        except Exception as e:
            logger.error(f"Unexpected error in RegularJWTAuthentication: {str(e)}")
            raise exceptions.AuthenticationFailed('Authentication failed')
    
    def authenticate_header(self, request):
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response.
        """
        return 'Bearer'


class UniversalAuthentication(authentication.BaseAuthentication):
    """
    Universal authentication class that ensures ALL endpoints work with both token types.
    
    This is a more aggressive version that prioritizes compatibility.
    """
    
    def __init__(self):
        if JWT_AVAILABLE:
            self.regular_jwt_auth = JWTAuthentication()
        else:
            self.regular_jwt_auth = None
        self.azure_ad_auth = AzureADAuthentication()
    
    def authenticate(self, request: Request) -> Optional[Tuple[AbstractBaseUser, str]]:
        """
        Universal authentication that works with any valid token.
        """
        # Extract the Authorization header
        auth_header = authentication.get_authorization_header(request).split()
        
        if not auth_header or auth_header[0].lower() != b'bearer':
            return None
            
        if len(auth_header) != 2:
            return None
            
        try:
            token = auth_header[1].decode('utf-8')
        except UnicodeError:
            return None
        
        # Try both authentication methods with better error handling
        regular_result = None
        azure_result = None
        
        # Try regular JWT if available
        if JWT_AVAILABLE and self.regular_jwt_auth:
            try:
                regular_result = self.regular_jwt_auth.authenticate(request)
                if regular_result is not None:
                    user, validated_token = regular_result
                    logger.info(f"User {user.email} authenticated with regular JWT (universal)")
                    return regular_result
            except (InvalidToken, TokenError) as e:
                logger.debug(f"Regular JWT failed in universal auth: {e}")
            except exceptions.AuthenticationFailed as e:
                logger.debug(f"Regular JWT authentication failed: {e}")
            except Exception as e:
                logger.debug(f"Unexpected error in regular JWT: {e}")
        
        # Try Azure AD authentication - it will return None if token doesn't have 'kid'
        try:
            azure_result = self.azure_ad_auth.authenticate(request)
            if azure_result is not None:
                user, validated_token = azure_result
                logger.info(f"User {user.email} authenticated with Azure AD (universal)")
                return azure_result
        except exceptions.AuthenticationFailed as e:
            logger.debug(f"Azure AD authentication failed: {e}")
        except Exception as e:
            logger.debug(f"Unexpected error in Azure AD auth: {e}")
        
        # Both failed or returned None
        logger.debug("Both authentication methods failed or returned None")
        return None
    
    def authenticate_header(self, request):
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response.
        """
        return 'Bearer'
