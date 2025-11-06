"""
Notification service for creating and sending notifications.

This module provides utilities for creating notifications and sending them
via WebSocket with multi-language support.
"""

import logging
from typing import Dict, Any, Optional, List, Union
from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer  # COMMENTED OUT FOR PRODUCTION
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Notification, NotificationPreference

User = get_user_model()
logger = logging.getLogger(__name__)


def translate_message(messages: Dict[str, str], lang: str = "en") -> str:
    """
    Get message in specified language.
    
    Args:
        messages: Dictionary with language keys and message values
        lang: Language code ('en' or 'ar')
    
    Returns:
        Message in specified language, fallback to English
    """
    return messages.get(lang, messages.get("en", ""))


class NotificationService:
    """
    Service class for creating and managing notifications.
    
    Handles notification creation, WebSocket delivery, and user preferences.
    """
    
    @staticmethod
    def create_notification(
        recipient: User,
        title: Union[str, Dict[str, str]],
        body: Union[str, Dict[str, str]],
        notification_type: str = Notification.TYPE_ADMIN_MESSAGE,
        priority: str = Notification.PRIORITY_NORMAL,
        sender: Optional[User] = None,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[timezone.datetime] = None
    ) -> Optional[Notification]:
        """
        Create a new notification.
        
        Args:
            recipient: User who will receive the notification
            title: Notification title (string or dict with language keys)
            body: Notification body (string or dict with language keys)
            notification_type: Type of notification
            priority: Priority level
            sender: User who triggered the notification (optional)
            action_url: URL for notification action (optional)
            metadata: Additional metadata (optional)
            expires_at: Expiration datetime (optional)
        
        Returns:
            Created notification or None if creation failed
        """
        try:
            # Convert string titles/bodies to multi-language format
            if isinstance(title, str):
                title = {"en": title, "ar": title}
            if isinstance(body, str):
                body = {"en": body, "ar": body}
            
            # Check user preferences
            try:
                preferences = NotificationPreference.objects.get(user=recipient)
                if not preferences.should_receive_notification(notification_type):
                    logger.info(f"User {recipient.email} has disabled {notification_type} notifications")
                    return None
                
                if preferences.is_in_quiet_hours():
                    logger.info(f"User {recipient.email} is in quiet hours, skipping notification")
                    return None
            except NotificationPreference.DoesNotExist:
                # Create default preferences for user
                NotificationPreference.objects.create(user=recipient)
            
            # Create notification
            notification = Notification.objects.create(
                recipient=recipient,
                sender=sender,
                title=title,
                body=body,
                notification_type=notification_type,
                priority=priority,
                action_url=action_url,
                metadata=metadata or {},
                expires_at=expires_at
            )
            
            logger.info(f"Created notification {notification.id} for user {recipient.email}")
            
            # Send via WebSocket
            NotificationService.send_websocket_notification(notification)
            
            return notification
            
        except Exception as e:
            logger.error(f"Failed to create notification for {recipient.email}: {e}")
            return None
    
    @staticmethod
    def send_websocket_notification(notification: Notification):
        """
        Send notification via WebSocket to the recipient.
        
        Args:
            notification: Notification instance to send
        
        NOTE: WebSocket functionality is COMMENTED OUT FOR PRODUCTION
        """
        # WebSocket functionality COMMENTED OUT FOR PRODUCTION
        logger.warning("WebSocket notifications are disabled for production deployment")
        return
        
        # try:
        #     channel_layer = get_channel_layer()
        #     if not channel_layer:
        #         logger.warning("Channel layer not configured, WebSocket notification not sent")
        #         return
        #     
        #     # Get user's preferred language
        #     try:
        #         preferences = NotificationPreference.objects.get(user=notification.recipient)
        #         lang = preferences.preferred_language
        #     except NotificationPreference.DoesNotExist:
        #         lang = 'en'
        #     
        #     # Prepare notification data
        #     notification_data = notification.to_websocket_dict(lang)
        #     
        #     # Send to user's personal notification group
        #     group_name = f"user_notifications_{notification.recipient.id}"
        #     
        #     async_to_sync(channel_layer.group_send)(
        #         group_name,
        #         {
        #             'type': 'notification_message',
        #             'notification': notification_data
        #         }
        #     )
        #     
        #     # Update notification as sent via WebSocket
        #     notification.sent_via_websocket = True
        #     notification.websocket_sent_at = timezone.now()
        #     notification.save(update_fields=['sent_via_websocket', 'websocket_sent_at'])
        #     
        #     logger.info(f"Sent WebSocket notification {notification.id} to user {notification.recipient.email}")
        #     
        # except Exception as e:
        #     logger.error(f"Failed to send WebSocket notification {notification.id}: {e}")
    
    @staticmethod
    def create_survey_assigned_notification(
        recipient: User,
        survey_title: str,
        sender: User,
        survey_id: str,
        survey_url: str
    ) -> Optional[Notification]:
        """
        Create notification for survey assignment.
        
        Args:
            recipient: User assigned to the survey
            survey_title: Title of the survey
            sender: User who assigned the survey
            survey_id: UUID of the survey
            survey_url: URL to access the survey
        
        Returns:
            Created notification or None
        """
        title = {
            "en": "New Survey Assigned",
            "ar": "تم تعيين استبيان جديد"
        }
        
        body = {
            "en": f"{sender.first_name} {sender.last_name} assigned you a survey: {survey_title}",
            "ar": f"قام {sender.first_name} {sender.last_name} بتعيين استبيان لك: {survey_title}"
        }
        
        metadata = {
            "survey_id": survey_id,
            "survey_title": survey_title,
            "assigner_id": sender.id,
            "assigner_name": f"{sender.first_name} {sender.last_name}".strip()
        }
        
        return NotificationService.create_notification(
            recipient=recipient,
            title=title,
            body=body,
            notification_type=Notification.TYPE_SURVEY_ASSIGNED,
            priority=Notification.PRIORITY_NORMAL,
            sender=sender,
            action_url=survey_url,
            metadata=metadata
        )
    
    @staticmethod
    def create_survey_completed_notification(
        recipient: User,
        survey_title: str,
        respondent_name: str,
        survey_id: str,
        survey_url: str
    ) -> Optional[Notification]:
        """
        Create notification for survey completion.
        
        Args:
            recipient: Survey owner/creator
            survey_title: Title of the survey
            respondent_name: Name of the person who completed the survey
            survey_id: UUID of the survey
            survey_url: URL to view survey results
        
        Returns:
            Created notification or None
        """
        title = {
            "en": "Survey Completed",
            "ar": "تم إكمال الاستبيان"
        }
        
        body = {
            "en": f"{respondent_name} completed your survey: {survey_title}",
            "ar": f"أكمل {respondent_name} الاستبيان الخاص بك: {survey_title}"
        }
        
        metadata = {
            "survey_id": survey_id,
            "survey_title": survey_title,
            "respondent_name": respondent_name
        }
        
        return NotificationService.create_notification(
            recipient=recipient,
            title=title,
            body=body,
            notification_type=Notification.TYPE_SURVEY_COMPLETED,
            priority=Notification.PRIORITY_HIGH,
            action_url=survey_url,
            metadata=metadata
        )
    
    @staticmethod
    def create_survey_shared_notification(
        recipient: User,
        survey_title: str,
        sender: User,
        survey_id: str,
        survey_url: str
    ) -> Optional[Notification]:
        """
        Create notification for survey sharing.
        
        Args:
            recipient: User who received the shared survey
            survey_title: Title of the survey
            sender: User who shared the survey
            survey_id: UUID of the survey
            survey_url: URL to access the survey
        
        Returns:
            Created notification or None
        """
        title = {
            "en": "Survey Shared with You",
            "ar": "تم مشاركة استبيان معك"
        }
        
        body = {
            "en": f"{sender.first_name} {sender.last_name} shared a survey with you: {survey_title}",
            "ar": f"قام {sender.first_name} {sender.last_name} بمشاركة استبيان معك: {survey_title}"
        }
        
        metadata = {
            "survey_id": survey_id,
            "survey_title": survey_title,
            "sharer_id": sender.id,
            "sharer_name": f"{sender.first_name} {sender.last_name}".strip()
        }
        
        return NotificationService.create_notification(
            recipient=recipient,
            title=title,
            body=body,
            notification_type=Notification.TYPE_SURVEY_SHARED,
            priority=Notification.PRIORITY_NORMAL,
            sender=sender,
            action_url=survey_url,
            metadata=metadata
        )
    
    @staticmethod
    def create_survey_available_notification(
        recipient: User,
        survey_title: str,
        sender: User,
        survey_id: str,
        survey_url: str,
        survey_visibility: str
    ) -> Optional[Notification]:
        """
        Create notification for when a new survey becomes available.
        
        Args:
            recipient: User who can now access the survey
            survey_title: Title of the survey
            sender: User who created/published the survey
            survey_id: UUID of the survey
            survey_url: URL to access the survey
            survey_visibility: Visibility level of the survey
        
        Returns:
            Created notification or None
        """
        visibility_text = {
            "PUBLIC": {"en": "public", "ar": "عام"},
            "AUTH": {"en": "authenticated users", "ar": "المستخدمين المسجلين"},
            "PRIVATE": {"en": "selected users", "ar": "مستخدمين مختارين"},
            "GROUPS": {"en": "your groups", "ar": "مجموعاتك"}
        }
        
        vis_text = visibility_text.get(survey_visibility, {"en": "users", "ar": "المستخدمين"})
        
        title = {
            "en": "New Survey Available",
            "ar": "استبيان جديد متاح"
        }
        
        body = {
            "en": f"A new survey is available for {vis_text['en']}: {survey_title}",
            "ar": f"استبيان جديد متاح لـ {vis_text['ar']}: {survey_title}"
        }
        
        metadata = {
            "survey_id": survey_id,
            "survey_title": survey_title,
            "creator_id": sender.id,
            "creator_name": f"{sender.first_name} {sender.last_name}".strip(),
            "survey_visibility": survey_visibility
        }
        
        return NotificationService.create_notification(
            recipient=recipient,
            title=title,
            body=body,
            notification_type=Notification.TYPE_SURVEY_ASSIGNED,
            priority=Notification.PRIORITY_NORMAL,
            sender=sender,
            action_url=survey_url,
            metadata=metadata
        )
    
    @staticmethod
    def create_survey_deactivated_notification(
        recipient: User,
        survey_title: str,
        sender: User,
        survey_id: str,
        survey_url: str
    ) -> Optional[Notification]:
        """
        Create notification for when a survey is deactivated.
        
        Args:
            recipient: User who was affected by the deactivation
            survey_title: Title of the survey
            sender: User who deactivated the survey
            survey_id: UUID of the survey
            survey_url: URL to view the survey (likely inactive)
        
        Returns:
            Created notification or None
        """
        title = {
            "en": "Survey Deactivated",
            "ar": "تم إيقاف الاستبيان"
        }
        
        body = {
            "en": f"The survey '{survey_title}' has been deactivated and is no longer accepting responses",
            "ar": f"تم إيقاف الاستبيان '{survey_title}' ولم يعد يقبل إجابات"
        }
        
        metadata = {
            "survey_id": survey_id,
            "survey_title": survey_title,
            "deactivator_id": sender.id,
            "deactivator_name": f"{sender.first_name} {sender.last_name}".strip()
        }
        
        return NotificationService.create_notification(
            recipient=recipient,
            title=title,
            body=body,
            notification_type=Notification.TYPE_SURVEY_UPDATED,
            priority=Notification.PRIORITY_NORMAL,
            sender=sender,
            action_url=survey_url,
            metadata=metadata
        )
    
    @staticmethod
    def create_admin_message_notification(
        recipient: User,
        title: Union[str, Dict[str, str]],
        message: Union[str, Dict[str, str]],
        priority: str = Notification.PRIORITY_NORMAL,
        action_url: Optional[str] = None
    ) -> Optional[Notification]:
        """
        Create admin message notification.
        
        Args:
            recipient: User to receive the message
            title: Message title
            message: Message content
            priority: Priority level
            action_url: Optional action URL
        
        Returns:
            Created notification or None
        """
        return NotificationService.create_notification(
            recipient=recipient,
            title=title,
            body=message,
            notification_type=Notification.TYPE_ADMIN_MESSAGE,
            priority=priority,
            action_url=action_url
        )
    
    @staticmethod
    def bulk_notify_users(
        recipients: List[User],
        title: Union[str, Dict[str, str]],
        body: Union[str, Dict[str, str]],
        notification_type: str = Notification.TYPE_ADMIN_MESSAGE,
        priority: str = Notification.PRIORITY_NORMAL,
        sender: Optional[User] = None,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Notification]:
        """
        Send notifications to multiple users.
        
        Args:
            recipients: List of users to notify
            title: Notification title
            body: Notification body
            notification_type: Type of notification
            priority: Priority level
            sender: User who triggered the notification
            action_url: Optional action URL
            metadata: Additional metadata
        
        Returns:
            List of created notifications
        """
        notifications = []
        
        for recipient in recipients:
            notification = NotificationService.create_notification(
                recipient=recipient,
                title=title,
                body=body,
                notification_type=notification_type,
                priority=priority,
                sender=sender,
                action_url=action_url,
                metadata=metadata
            )
            
            if notification:
                notifications.append(notification)
        
        logger.info(f"Bulk created {len(notifications)} notifications for {len(recipients)} users")
        return notifications


class SurveyNotificationService:
    """
    Specialized service for survey-related notifications.
    
    Handles notification logic for survey events like creation, sharing, deactivation, etc.
    """
    
    @staticmethod
    def get_eligible_users_for_survey_notification(survey, exclude_creator=True):
        """
        Get all users who would be able to see this survey in their 'my-shared' view.
        
        Args:
            survey: Survey instance
            exclude_creator: Whether to exclude the survey creator from the list
            
        Returns:
            QuerySet of User objects who should be notified
        """
        from django.contrib.auth import get_user_model
        from django.db.models import Q
        
        User = get_user_model()
        
        if survey.status != 'submitted' or not survey.is_active:
            # Only notify for active submitted surveys
            return User.objects.none()
        
        base_query = Q()
        
        if survey.visibility == 'PUBLIC':
            # All users can see public surveys
            base_query = Q()  # All users
        elif survey.visibility == 'AUTH':
            # All authenticated users can see AUTH surveys
            base_query = Q()  # All users (since they're all authenticated if they get notifications)
        elif survey.visibility == 'PRIVATE':
            # Only specifically shared users can see private surveys
            shared_user_ids = survey.shared_with.values_list('id', flat=True)
            base_query = Q(id__in=shared_user_ids)
        elif survey.visibility == 'GROUPS':
            # Users in shared groups can see group surveys
            try:
                shared_group_ids = survey.shared_with_groups.values_list('id', flat=True)
                # Get users who are members of these groups
                base_query = Q(user_groups__group__id__in=shared_group_ids)
            except Exception as e:
                logger.error(f"Error getting group members for survey {survey.id}: {e}")
                return User.objects.none()
        else:
            # Unknown visibility, no users should be notified
            return User.objects.none()
        
        queryset = User.objects.filter(base_query).distinct()
        
        if exclude_creator:
            queryset = queryset.exclude(id=survey.creator.id)
        
        return queryset
    
    @staticmethod
    def notify_users_of_new_survey(survey, request=None, force_send=False):
        """
        Send notifications to all eligible users about a new survey.
        
        Args:
            survey: Survey instance that was just made available
            request: Django request object (optional, for building URLs)
            force_send: If True, force sending notifications even for PUBLIC surveys
        """
        if survey.status != 'submitted' or not survey.is_active:
            logger.debug(f"Skipping notification for survey {survey.id} - not active/submitted")
            return
        
        # Safety check: Prevent sending notifications to all users for PUBLIC surveys unless explicitly forced
        if survey.visibility == 'PUBLIC' and not force_send:
            logger.info(f"Skipping notifications for PUBLIC survey {survey.id} - would notify all users. Use force_send=True if needed.")
            return []
        
        # Get all users who should be notified
        eligible_users = SurveyNotificationService.get_eligible_users_for_survey_notification(
            survey, exclude_creator=True
        )
        
        if not eligible_users.exists():
            logger.debug(f"No eligible users to notify for survey {survey.id}")
            return
        
        # Additional safety check for AUTH surveys which also notify all users
        if survey.visibility == 'AUTH' and not force_send and eligible_users.count() > 100:
            logger.warning(f"Skipping notifications for AUTH survey {survey.id} - would notify {eligible_users.count()} users. Use force_send=True if needed.")
            return []
        
        # Build survey URL
        survey_url = f"/surveys/{survey.id}/"
        if request:
            base_url = get_domain_url(request)
            survey_url = f"{base_url}/surveys/{survey.id}/"
        
        # Send notifications to all eligible users
        notifications = []
        for user in eligible_users:
            notification = NotificationService.create_survey_available_notification(
                recipient=user,
                survey_title=survey.title,
                sender=survey.creator,
                survey_id=str(survey.id),
                survey_url=survey_url,
                survey_visibility=survey.visibility
            )
            if notification:
                notifications.append(notification)
        
        logger.info(f"Sent {len(notifications)} survey availability notifications for survey {survey.id}")
        return notifications
    
    @staticmethod
    def notify_users_of_survey_deactivation(survey, deactivator, request=None):
        """
        Send notifications to users about a survey being deactivated.
        
        Args:
            survey: Survey instance that was deactivated
            deactivator: User who deactivated the survey
            request: Django request object (optional, for building URLs)
        """
        # Get users who were previously able to see this survey
        # (we need to check based on the survey's sharing settings regardless of current active status)
        eligible_users = SurveyNotificationService.get_eligible_users_for_survey_notification(
            survey, exclude_creator=False  # Include creator in deactivation notifications
        ).exclude(id=deactivator.id)  # Exclude the person who deactivated it
        
        if not eligible_users.exists():
            logger.debug(f"No users to notify about deactivation of survey {survey.id}")
            return
        
        # Build survey URL
        survey_url = f"/surveys/{survey.id}/"
        if request:
            base_url = get_domain_url(request)
            survey_url = f"{base_url}/surveys/{survey.id}/"
        
        # Send notifications to all eligible users
        notifications = []
        for user in eligible_users:
            notification = NotificationService.create_survey_deactivated_notification(
                recipient=user,
                survey_title=survey.title,
                sender=deactivator,
                survey_id=str(survey.id),
                survey_url=survey_url
            )
            if notification:
                notifications.append(notification)
        
        logger.info(f"Sent {len(notifications)} survey deactivation notifications for survey {survey.id}")
        return notifications


# Utility function to get domain URL from request
def get_domain_url(request) -> str:
    """
    Get the domain URL from a request object.
    
    Args:
        request: Django request object
    
    Returns:
        Full domain URL (protocol + domain)
    """
    protocol = 'https' if request.is_secure() else 'http'
    domain = request.get_host()
    return f"{protocol}://{domain}"


# Usage Examples for URL Notifications
class NotificationUsageExamples:
    """
    Example usage patterns for creating notifications with URLs.
    
    These examples show how to integrate notifications with survey actions.
    """
    
    @staticmethod
    def example_survey_assignment(request, survey, assigned_users, assigner):
        """
        Example: Notify users when a survey is assigned to them.
        
        Args:
            request: Django request object
            survey: Survey instance
            assigned_users: List of User objects
            assigner: User who assigned the survey
        """
        base_url = get_domain_url(request)
        survey_url = f"{base_url}/surveys/{survey.id}/"
        
        for user in assigned_users:
            NotificationService.create_survey_assigned_notification(
                recipient=user,
                survey_title=survey.title,
                sender=assigner,
                survey_id=str(survey.id),
                survey_url=survey_url
            )
    
    @staticmethod
    def example_survey_completion(request, survey, respondent_name):
        """
        Example: Notify survey creator when someone completes their survey.
        
        Args:
            request: Django request object
            survey: Survey instance
            respondent_name: Name of the person who completed the survey
        """
        base_url = get_domain_url(request)
        results_url = f"{base_url}/surveys/{survey.id}/results/"
        
        NotificationService.create_survey_completed_notification(
            recipient=survey.creator,
            survey_title=survey.title,
            respondent_name=respondent_name,
            survey_id=str(survey.id),
            survey_url=results_url
        )
