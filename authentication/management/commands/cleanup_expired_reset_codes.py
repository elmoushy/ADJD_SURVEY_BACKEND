"""
Management command: cleanup_expired_reset_codes

Removes PasswordResetCode records that are either:
  - expired AND older than 24 hours, or
  - already used AND older than 24 hours.

Intended to run as a scheduled/cron task (e.g. daily at 2am).

Example:
    python manage.py cleanup_expired_reset_codes
"""

import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete expired and used password-reset codes older than 24 hours.'

    def handle(self, *args, **options):
        from authentication.models import PasswordResetCode

        cutoff = timezone.now() - timezone.timedelta(hours=24)

        deleted_count, _ = PasswordResetCode.objects.filter(
            # Expired codes older than the cutoff
            expires_at__lt=cutoff,
        ).delete()

        # Also clean up used codes older than the cutoff (expires_at may still
        # be in the future for codes invalidated early by a new request).
        used_deleted, _ = PasswordResetCode.objects.filter(
            is_used=True,
            created_at__lt=cutoff,
        ).delete()

        total = deleted_count + used_deleted
        msg = f'Deleted {total} stale password-reset code(s).'
        self.stdout.write(self.style.SUCCESS(msg))
        logger.info(msg)
