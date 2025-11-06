"""
Encryption utilities for surveys data using AES-256.

This module provides encryption/decryption functionality for survey data
using the same encryption standards as news_service and Files_Endpoints.
"""

import os
import logging
from cryptography.fernet import Fernet
from django.conf import settings

logger = logging.getLogger(__name__)


class SurveysDataEncryption:
    """
    Encryption handler for surveys data using AES-256 via Fernet.
    """
    
    def __init__(self):
        """Initialize encryption with key from environment or settings."""
        self.key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.key) if self.key else None
        
        if not self.cipher_suite:
            logger.warning("Surveys encryption not initialized - key not found")
    
    def _get_encryption_key(self):
        """Get encryption key from environment or generate one."""
        key = os.getenv('SURVEYS_ENCRYPTION_KEY')
        if not key:
            # Fallback to main encryption key
            key = os.getenv('ENCRYPTION_KEY')
        
        if not key:
            if settings.DEBUG:
                # Generate a key for development
                key = Fernet.generate_key().decode()
                logger.warning(f"Generated encryption key for development: {key}")
            else:
                logger.error("No encryption key found in production")
                return None
        
        return key.encode() if isinstance(key, str) else key
    
    def encrypt(self, data):
        """
        Encrypt data using AES-256.
        
        Args:
            data: Data to encrypt (will be converted to string)
            
        Returns:
            str: Encrypted data as string
        """
        if not self.cipher_suite:
            logger.error("Encryption not available")
            return data
        
        if not data:
            return data
        
        try:
            # Convert data to string if it's not already a string
            if not isinstance(data, str):
                data_str = str(data)
            else:
                data_str = data
            
            encrypted_data = self.cipher_suite.encrypt(data_str.encode())
            return encrypted_data.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data
    
    def decrypt(self, encrypted_data):
        """
        Decrypt data using AES-256.
        
        Args:
            encrypted_data: Encrypted data to decrypt (will be converted to string)
            
        Returns:
            str: Decrypted data
        """
        if not self.cipher_suite:
            logger.error("Decryption not available")
            return encrypted_data
        
        if not encrypted_data:
            return encrypted_data
        
        try:
            # Convert data to string if it's not already a string
            if not isinstance(encrypted_data, str):
                encrypted_data_str = str(encrypted_data)
            else:
                encrypted_data_str = encrypted_data
            
            decrypted_data = self.cipher_suite.decrypt(encrypted_data_str.encode())
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_data


# Global instance
surveys_data_encryption = SurveysDataEncryption()
