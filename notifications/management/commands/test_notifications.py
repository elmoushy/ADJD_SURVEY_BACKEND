"""
Management command to test the notification system.

This command creates test notifications and sends them via WebSocket
to verify the notification system is working correctly.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from notifications.services import NotificationService
from notifications.models import Notification

User = get_user_model()


class Command(BaseCommand):
    help = 'Test the notification system by creating sample notifications'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--email',
            type=str,
            help='Email of user to send test notifications to'
        )
        
        parser.add_argument(
            '--count',
            type=int,
            default=3,
            help='Number of test notifications to create (default: 3)'
        )
        
        parser.add_argument(
            '--type',
            choices=['survey_assigned', 'survey_completed', 'admin_message'],
            default='admin_message',
            help='Type of notification to create'
        )
        
        parser.add_argument(
            '--lang',
            choices=['en', 'ar'],
            default='en',
            help='Language for test notifications'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        email = options['email']
        count = options['count']
        notification_type = options['type']
        lang = options['lang']
        
        # Get user or use first available user
        if email:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User with email {email} not found')
                )
                return
        else:
            user = User.objects.first()
            if not user:
                self.stdout.write(
                    self.style.ERROR('No users found in database')
                )
                return
        
        self.stdout.write(f'Creating {count} test notifications for {user.email}')
        
        # Create test notifications based on type
        created_notifications = []
        
        for i in range(count):
            if notification_type == 'admin_message':
                notification = self._create_admin_message(user, i + 1, lang)
            elif notification_type == 'survey_assigned':
                notification = self._create_survey_assigned(user, i + 1, lang)
            elif notification_type == 'survey_completed':
                notification = self._create_survey_completed(user, i + 1, lang)
            
            if notification:
                created_notifications.append(notification)
        
        # Report results
        success_count = len(created_notifications)
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {success_count}/{count} test notifications'
            )
        )
        
        if created_notifications:
            self.stdout.write('Created notification IDs:')
            for notification in created_notifications:
                self.stdout.write(f'  - {notification.id} ({notification.get_title(lang)})')
        
        # Show WebSocket status
        websocket_sent = sum(1 for n in created_notifications if n.sent_via_websocket)
        self.stdout.write(
            self.style.SUCCESS(
                f'WebSocket delivery: {websocket_sent}/{success_count} notifications sent'
            )
        )
    
    def _create_admin_message(self, user, num, lang):
        """Create admin message notification."""
        if lang == 'ar':
            title = f"رسالة إدارية تجريبية {num}"
            body = f"هذه رسالة إدارية تجريبية رقم {num} لاختبار نظام الإشعارات."
        else:
            title = f"Test Admin Message {num}"
            body = f"This is test admin message #{num} to verify the notification system is working."
        
        return NotificationService.create_admin_message_notification(
            recipient=user,
            title={lang: title, 'en' if lang != 'en' else 'ar': title},
            message={lang: body, 'en' if lang != 'en' else 'ar': body},
            priority=Notification.PRIORITY_NORMAL
        )
    
    def _create_survey_assigned(self, user, num, lang):
        """Create survey assigned notification."""
        if lang == 'ar':
            survey_title = f"استبيان تجريبي {num}"
        else:
            survey_title = f"Test Survey {num}"
        
        # Create a mock sender (use the same user for testing)
        sender = user
        
        return NotificationService.create_survey_assigned_notification(
            recipient=user,
            survey_title=survey_title,
            sender=sender,
            survey_id=f"test-survey-{num}",
            survey_url=f"https://example.com/surveys/test-{num}/"
        )
    
    def _create_survey_completed(self, user, num, lang):
        """Create survey completed notification."""
        if lang == 'ar':
            survey_title = f"استبيان تجريبي {num}"
            respondent_name = f"مستخدم تجريبي {num}"
        else:
            survey_title = f"Test Survey {num}"
            respondent_name = f"Test User {num}"
        
        return NotificationService.create_survey_completed_notification(
            recipient=user,
            survey_title=survey_title,
            respondent_name=respondent_name,
            survey_id=f"test-survey-{num}",
            survey_url=f"https://example.com/surveys/test-{num}/results/"
        )
