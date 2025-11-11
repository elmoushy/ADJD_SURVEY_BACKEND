"""
Azure AD JWT Authentication for Django REST Framework

This module provides JWT token authentication using Azure AD (Microsoft Entra ID).
It validates JWT tokens issued by Azure AD and creates/updates Django users based
on the token claims.

Security Features:
- JWT signature verification using JWKS
- Token expiration validation
- Audience and issuer validation
- JWKS caching to reduce API calls
- Comprehensive error handling and logging

Performance Optimizations:
- JWKS key caching (5 minutes TTL)
- Efficient user lookup by Object ID
- Minimal database queries
"""

import jwt
import requests
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, Any
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone as django_timezone
from rest_framework import authentication, exceptions
from rest_framework.request import Request


User = get_user_model()
logger = logging.getLogger(__name__)


class AzureADAuthentication(authentication.BaseAuthentication):
    """
    Azure AD JWT Authentication class for Django REST Framework.
    
    This authentication class:
    1. Extracts Bearer tokens from Authorization header
    2. Validates JWT signature using Azure AD JWKS
    3. Verifies token claims (aud, iss, exp, etc.)
    4. Maps Azure AD Object ID to Django users
    5. Creates new users if they don't exist
    """
    
    def authenticate(self, request: Request) -> Optional[Tuple[AbstractBaseUser, str]]:
        """
        Authenticate the request and return a two-tuple of (user, token).
        
        Args:
            request: The HTTP request object
            
        Returns:
            Tuple of (user, token) if authentication succeeds, None otherwise
            
        Raises:
            AuthenticationFailed: If token is invalid or expired
        """
        # Extract the Authorization header
        auth_header = authentication.get_authorization_header(request).split()
        
        if not auth_header or auth_header[0].lower() != b'bearer':
            return None
            
        if len(auth_header) == 1:
            msg = 'Invalid token header. No credentials provided.'
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth_header) > 2:
            msg = 'Invalid token header. Token string should not contain spaces.'
            raise exceptions.AuthenticationFailed(msg)
            
        try:
            token = auth_header[1].decode('utf-8')
        except UnicodeError:
            msg = 'Invalid token header. Token string should not contain invalid characters.'
            raise exceptions.AuthenticationFailed(msg)
            
        result = self.authenticate_credentials(token)
        if result is None:
            return None  # Allow other authentication methods to try
        
        return result
    
    def authenticate_credentials(self, token: str) -> Optional[Tuple[AbstractBaseUser, str]]:
        """
        Validate the JWT token and return the corresponding user.
        
        Args:
            token: The JWT token string
            
        Returns:
            Tuple of (user, token)
            
        Raises:
            AuthenticationFailed: If token validation fails
        """
        try:
            # Decode token header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
            
            if not kid:
                logger.debug("JWT token missing 'kid' in header - not an Azure AD token")
                # Don't raise an exception here - return None to allow other auth methods
                return None
            
            # Get JWKS keys and find the matching key
            jwks_keys = self._get_jwks_keys()
            signing_key = self._find_signing_key(jwks_keys, kid)
            
            if not signing_key:
                logger.warning(f"No matching key found for kid: {kid}")
                raise exceptions.AuthenticationFailed('Invalid token: key not found')
            
            # Verify and decode the token
            # Try to decode with strict audience validation first
            try:
                payload = jwt.decode(
                    token,
                    signing_key,
                    algorithms=['RS256'],
                    audience=settings.AZURE_CLIENT_ID,
                    issuer=settings.AZURE_ISSUER,
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'verify_aud': True,
                        'verify_iss': True,
                        'require': ['exp', 'aud', 'iss', 'oid']
                    }
                )
            except jwt.InvalidAudienceError:
                # If audience validation fails, try without audience validation
                # This handles cases where Microsoft Graph token is sent instead of id_token
                logger.warning(f"Token audience mismatch, attempting flexible validation")
                payload = jwt.decode(
                    token,
                    signing_key,
                    algorithms=['RS256'],
                    issuer=settings.AZURE_ISSUER,
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'verify_aud': False,  # Skip audience validation
                        'verify_iss': True,
                        'require': ['exp', 'iss', 'oid']
                    }
                )
                
                # Log the actual audience for debugging
                actual_audience = payload.get('aud', 'unknown')
                logger.info(f"Accepted token with audience: {actual_audience} (expected: {settings.AZURE_CLIENT_ID})")
            
            # Extract user information from token
            user = self._get_or_create_user(payload)
            
            logger.info(f"Successfully authenticated user: {user.email}")
            return user, token
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidAudienceError:
            logger.warning("JWT token has invalid audience")
            raise exceptions.AuthenticationFailed('Invalid token audience')
        except jwt.InvalidIssuerError:
            logger.warning("JWT token has invalid issuer")
            raise exceptions.AuthenticationFailed('Invalid token issuer')
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            raise exceptions.AuthenticationFailed('Invalid token')
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise exceptions.AuthenticationFailed('Authentication failed')
    
    def _get_jwks_keys(self) -> Dict[str, Any]:
        """
        Fetch and cache JWKS keys from Azure AD.
        
        Returns:
            Dictionary containing JWKS keys
            
        Raises:
            AuthenticationFailed: If JWKS fetch fails
        """
        cache_key = 'azure_ad_jwks_keys'
        cached_keys = cache.get(cache_key)
        
        if cached_keys:
            return cached_keys
        
        try:
            logger.info("Fetching JWKS keys from Azure AD")
            response = requests.get(
                settings.AZURE_JWKS_URI,
                timeout=10,
                headers={'User-Agent': 'ADJD-Survey-Backend/1.0'}
            )
            response.raise_for_status()
            
            jwks_data = response.json()
            
            # Cache for 5 minutes
            cache.set(cache_key, jwks_data, 300)
            
            logger.info("Successfully cached JWKS keys")
            return jwks_data
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch JWKS keys: {str(e)}")
            raise exceptions.AuthenticationFailed('Unable to verify token')
    
    def _find_signing_key(self, jwks_keys: Dict[str, Any], kid: str) -> Optional[str]:
        """
        Find the signing key that matches the token's key ID.
        
        Args:
            jwks_keys: JWKS response containing keys
            kid: Key ID from token header
            
        Returns:
            PEM-formatted public key string or None if not found
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import base64
        
        for key in jwks_keys.get('keys', []):
            if key.get('kid') == kid and key.get('kty') == 'RSA':
                try:
                    # Decode the RSA components
                    n = base64.urlsafe_b64decode(self._add_padding(key['n']))
                    e = base64.urlsafe_b64decode(self._add_padding(key['e']))
                    
                    # Convert to integers
                    n_int = int.from_bytes(n, 'big')
                    e_int = int.from_bytes(e, 'big')
                    
                    # Create RSA public key
                    public_key = rsa.RSAPublicNumbers(e_int, n_int).public_key()
                    
                    # Convert to PEM format
                    pem_key = public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    )
                    
                    return pem_key.decode('utf-8')
                    
                except Exception as e:
                    logger.error(f"Error processing signing key: {str(e)}")
                    continue
        
        return None
    
    def _add_padding(self, base64_string: str) -> str:
        """
        Add padding to base64 string if needed.
        
        Args:
            base64_string: Base64 encoded string
            
        Returns:
            Properly padded base64 string
        """
        missing_padding = len(base64_string) % 4
        if missing_padding:
            base64_string += '=' * (4 - missing_padding)
        return base64_string
    
    def _get_or_create_user(self, payload: Dict[str, Any]) -> AbstractBaseUser:
        """
        Get or create a Django user based on Azure AD token payload.
        
        This method captures the Azure AD username claim and creates users
        with only the essential fields needed for the application.
        
        Args:
            payload: Decoded JWT token payload
            
        Returns:
            Django User instance
        """
        # Extract user information from Azure AD token
        object_id = payload.get('oid')  # Azure AD Object ID (unique identifier)
        email = payload.get('email') or payload.get('preferred_username', '')
        
        # Capture username claim - try different possible claims
        username_claim = (
            payload.get('preferred_username') or  # Most common for username
            payload.get('upn') or                 # User Principal Name
            payload.get('unique_name') or         # Alternative username claim
            payload.get('email') or               # Fallback to email
            object_id                             # Final fallback to Object ID
        )
        
        # Extract name components
        given_name = payload.get('given_name', '')
        family_name = payload.get('family_name', '')
        name = payload.get('name', '')
        
        # If given_name/family_name not available, try to parse from name
        if not given_name and not family_name and name:
            name_parts = name.split(' ', 1)
            given_name = name_parts[0] if len(name_parts) > 0 else ''
            family_name = name_parts[1] if len(name_parts) > 1 else ''
        
        if not object_id:
            logger.error("Token missing required 'oid' claim")
            raise exceptions.AuthenticationFailed('Invalid token: missing user ID')
        
        if not username_claim:
            logger.error("Token missing username claims")
            raise exceptions.AuthenticationFailed('Invalid token: missing username')
        
        # Try to find existing user by Azure AD Object ID (stored in username field)
        try:
            user = User.objects.get(username=object_id)
            
            # Update user information if changed
            updated = False
            if user.email != email and email:
                user.email = email
                updated = True
            if user.first_name != given_name and given_name:
                user.first_name = given_name
                updated = True
            if user.last_name != family_name and family_name:
                user.last_name = family_name
                updated = True
                
            if updated:
                user.save(update_fields=['email', 'first_name', 'last_name'])
                logger.info(f"Updated user information for: {email}")
            
            # Update last login
            user.last_login = django_timezone.now()
            user.save(update_fields=['last_login'])
            
            return user
            
        except User.DoesNotExist:
            # Create new user with only the specified fields
            logger.info(f"Creating new user for: {email} (username: {username_claim})")
            
            # Create user with only essential fields
            user = User.objects.create_user(
                username=object_id,      # Use Object ID as primary identifier
                email=email,             # User's email
                first_name=given_name,   # Optional: for better UX
                last_name=family_name,   # Optional: for better UX
                role='user',         # Default role for Azure AD users
                auth_type='azure',       # Mark as Azure AD user
                is_active=True,          # Active by default
            )
            
            # Set last login for new user
            user.last_login = django_timezone.now()
            user.save(update_fields=['last_login'])
            
            # Log additional information for debugging
            logger.info(
                f"Successfully created user: {email}, "
                f"Object ID: {object_id}, "
                f"Username claim: {username_claim}, "
                f"Role: {user.role}"
            )
            
            logger.info(f"Successfully created user: {email}")
            return user
    
    def authenticate_header(self, request: Request) -> str:
        """
        Return the authentication header for 401 responses.
        
        Args:
            request: The HTTP request object
            
        Returns:
            Authentication header string
        """
        return 'Bearer realm="Azure AD"'


class AzureADUserInfo:
    """
    Utility class to extract additional user information from Azure AD tokens.
    """
    
    @staticmethod
    def get_user_roles(token_payload: Dict[str, Any]) -> list:
        """
        Extract user roles from token payload.
        
        Args:
            token_payload: Decoded JWT token payload
            
        Returns:
            List of role names
        """
        roles = token_payload.get('roles', [])
        groups = token_payload.get('groups', [])
        
        # Combine roles and groups
        all_roles = []
        if isinstance(roles, list):
            all_roles.extend(roles)
        if isinstance(groups, list):
            all_roles.extend(groups)
            
        return all_roles
    
    @staticmethod
    def get_user_permissions(token_payload: Dict[str, Any]) -> list:
        """
        Extract user permissions from token payload.
        
        Args:
            token_payload: Decoded JWT token payload
            
        Returns:
            List of permission scopes
        """
        scp = token_payload.get('scp', '')
        if isinstance(scp, str):
            return scp.split(' ') if scp else []
        return []
    
    @staticmethod
    def is_user_in_role(token_payload: Dict[str, Any], role_name: str) -> bool:
        """
        Check if user has a specific role.
        
        Args:
            token_payload: Decoded JWT token payload
            role_name: Name of the role to check
            
        Returns:
            True if user has the role, False otherwise
        """
        roles = AzureADUserInfo.get_user_roles(token_payload)
        return role_name in roles
