"""
Django signals for authentication-related notifications.

This module contains signal handlers for user authentication events
such as user registration and login notifications.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in

from notifications.services import NotificationService
from notifications.models import Notification

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def user_created_notification(sender, instance, created, **kwargs):
    """
    Send welcome notification to new users.
    
    This signal is triggered when a new user is created.
    """
    if created:
        user = instance
        
        try:
            # Create welcome notification
            welcome_title_en = "Welcome to WeaponPowerCloud!"
            welcome_title_ar = "مرحباً بك في WeaponPowerCloud!"
            
            welcome_message_en = (
                f"Welcome {user.full_name or user.username}! "
                "Your account has been successfully created. "
                "You can now access surveys and participate in data collection activities."
            )
            welcome_message_ar = (
                f"مرحباً {user.full_name or user.username}! "
                "تم إنشاء حسابك بنجاح. "
                "يمكنك الآن الوصول إلى الاستبيانات والمشاركة في أنشطة جمع البيانات."
            )
            
            NotificationService.create_admin_message_notification(
                recipient=user,
                title={'en': welcome_title_en, 'ar': welcome_title_ar},
                message={'en': welcome_message_en, 'ar': welcome_message_ar},
                priority=Notification.PRIORITY_NORMAL
            )
            
            logger.info(f"Sent welcome notification to new user {user.email}")
            
        except Exception as e:
            logger.error(f"Failed to send welcome notification to {user.email}: {str(e)}")


@receiver(user_logged_in)
def user_login_notification(sender, request, user, **kwargs):
    """
    Send login notification for security purposes.
    
    This signal is triggered when a user logs in successfully.
    Note: This is disabled by default to avoid spam, but can be enabled
    for high-security environments.
    """
    # Uncomment the following code to enable login notifications
    # try:
    #     # Get IP address
    #     ip_address = request.META.get('HTTP_X_FORWARDED_FOR')
    #     if ip_address:
    #         ip_address = ip_address.split(',')[0].strip()
    #     else:
    #         ip_address = request.META.get('REMOTE_ADDR', 'Unknown')
    #     
    #     # Get user agent
    #     user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')[:100]
    #     
    #     # Create login notification
    #     login_title_en = "Security Alert: New Login"
    #     login_title_ar = "تنبيه أمني: تسجيل دخول جديد"
    #     
    #     login_message_en = (
    #         f"Your account was accessed from IP: {ip_address}. "
    #         f"If this was not you, please contact support immediately."
    #     )
    #     login_message_ar = (
    #         f"تم الوصول إلى حسابك من العنوان: {ip_address}. "
    #         f"إذا لم تكن أنت، يرجى الاتصال بالدعم الفني فوراً."
    #     )
    #     
    #     NotificationService.create_admin_message_notification(
    #         recipient=user,
    #         title={'en': login_title_en, 'ar': login_title_ar},
    #         message={'en': login_message_en, 'ar': login_message_ar},
    #         priority=Notification.PRIORITY_LOW
    #     )
    #     
    #     logger.info(f"Sent login notification to user {user.email} from IP {ip_address}")
    #     
    # except Exception as e:
    #     logger.error(f"Failed to send login notification to {user.email}: {str(e)}")
    pass
