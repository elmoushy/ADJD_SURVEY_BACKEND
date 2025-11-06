"""
Management command to send survey deadline reminder notifications.

This command checks for surveys that are approaching their deadline
and sends reminder notifications to users who have access to them.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from surveys.models import Survey
from surveys.signals import send_survey_deadline_reminder


class Command(BaseCommand):
    help = 'Send deadline reminder notifications for surveys approaching their end date'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--days',
            nargs='+',
            type=int,
            default=[1, 3, 7],
            help='Days before deadline to send reminders (default: 1, 3, 7)'
        )
        
        parser.add_argument(
            '--survey-id',
            type=str,
            help='Send reminder for specific survey ID only'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without sending notifications'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        reminder_days = options['days']
        survey_id = options['survey_id']
        dry_run = options['dry_run']
        
        now = timezone.now()
        
        # Get surveys to check
        if survey_id:
            try:
                surveys = Survey.objects.filter(id=survey_id, status='submitted')
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f'Invalid survey ID: {survey_id}')
                )
                return
        else:
            # Get all submitted surveys with end dates
            surveys = Survey.objects.filter(
                status='submitted',
                end_date__isnull=False,
                end_date__gt=now,  # Only future deadlines
                is_active=True
            )
        
        total_reminders = 0
        
        for survey in surveys:
            if not survey.end_date:
                continue
                
            # Calculate days until deadline
            time_until_deadline = survey.end_date - now
            days_until_deadline = time_until_deadline.days
            
            # Check if we should send a reminder for this survey
            if days_until_deadline in reminder_days:
                if dry_run:
                    self.stdout.write(
                        f'Would send {days_until_deadline}-day reminder for survey: '
                        f'{survey.title} (ID: {survey.id})'
                    )
                    # Count potential recipients
                    recipients = set(survey.shared_with.all())
                    try:
                        from authentication.models import Group
                        for group in survey.shared_with_groups.all():
                            recipients.update(group.users.all())
                    except ImportError:
                        pass
                    
                    self.stdout.write(f'  - Recipients: {len(recipients)} users')
                    total_reminders += len(recipients)
                else:
                    # Send the actual reminder
                    try:
                        send_survey_deadline_reminder(survey, days_until_deadline)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Sent {days_until_deadline}-day reminder for survey: '
                                f'{survey.title} (ID: {survey.id})'
                            )
                        )
                        total_reminders += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Failed to send reminder for survey {survey.id}: {str(e)}'
                            )
                        )
        
        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Dry run complete. Would send {total_reminders} reminder notifications.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Sent deadline reminders for {total_reminders} surveys.'
                )
            )
        
        # Show configuration
        self.stdout.write(f'Reminder schedule: {reminder_days} days before deadline')
        if survey_id:
            self.stdout.write(f'Filtered to survey ID: {survey_id}')
