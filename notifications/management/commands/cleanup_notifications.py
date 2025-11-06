"""
Management command to clean up old notifications.

This command removes expired notifications and old read notifications
to keep the database clean and performant.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Clean up old notifications'
    
    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Remove read notifications older than X days (default: 30)'
        )
        
        parser.add_argument(
            '--expired',
            action='store_true',
            help='Remove all expired notifications'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
    
    def handle(self, *args, **options):
        """Execute the command."""
        days = options['days']
        remove_expired = options['expired']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No notifications will be deleted')
            )
        
        total_deleted = 0
        
        # Remove expired notifications
        if remove_expired:
            expired_notifications = Notification.objects.filter(
                expires_at__isnull=False,
                expires_at__lt=timezone.now()
            )
            
            expired_count = expired_notifications.count()
            if expired_count > 0:
                if not dry_run:
                    deleted_count, _ = expired_notifications.delete()
                    total_deleted += deleted_count
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'{"Would delete" if dry_run else "Deleted"} {expired_count} expired notifications'
                    )
                )
        
        # Remove old read notifications
        cutoff_date = timezone.now() - timedelta(days=days)
        old_read_notifications = Notification.objects.filter(
            is_read=True,
            read_at__lt=cutoff_date
        )
        
        old_read_count = old_read_notifications.count()
        if old_read_count > 0:
            if not dry_run:
                deleted_count, _ = old_read_notifications.delete()
                total_deleted += deleted_count
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'{"Would delete" if dry_run else "Deleted"} {old_read_count} old read notifications (>{days} days)'
                )
            )
        
        # Summary
        if not dry_run and total_deleted > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully deleted {total_deleted} notifications total')
            )
        elif not dry_run:
            self.stdout.write(
                self.style.SUCCESS('No notifications needed to be deleted')
            )
        
        # Show current statistics
        total_notifications = Notification.objects.count()
        unread_notifications = Notification.objects.filter(is_read=False).count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Current statistics: {total_notifications} total, {unread_notifications} unread'
            )
        )
