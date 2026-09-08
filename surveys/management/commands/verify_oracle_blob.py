"""
Verify that large BLOB uploads survive a round trip on the live database.

This is the regression check for ORA-01461 ("can bind a LONG value only for
insert into a LONG column"), which used to break every survey/response/email
attachment larger than a few kilobytes on Oracle. Run it on the target server:

    python manage.py verify_oracle_blob
    python manage.py verify_oracle_blob --size-mb 9

Everything the command writes is rolled back, so it leaves no rows behind.
"""

import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.db import connections, router, transaction

from adjd_survey.oracle_blob import blob_to_bytes
from surveys.models import Survey, SurveyAttachment


class _Rollback(Exception):
    """Sentinel used to undo everything the check wrote."""


class Command(BaseCommand):
    help = (
        'Write and read back a multi-megabyte attachment to prove the '
        'Oracle BLOB path works (ORA-01461 regression check). Rolls back.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--size-mb',
            type=float,
            default=3.0,
            help='Size of the test payload in megabytes (default: 3).',
        )

    def handle(self, *args, **options):
        size_mb = options['size_mb']
        payload = self._payload(size_mb)
        expected = hashlib.sha256(payload).hexdigest()

        using = router.db_for_write(SurveyAttachment)
        connection = connections[using]

        self.stdout.write(
            f'Database: {connection.vendor} ({connection.settings_dict.get("NAME")})'
        )
        self.stdout.write(f'Payload:  {len(payload):,} bytes  sha256={expected[:16]}…')

        try:
            with transaction.atomic(using=using):
                survey = self._survey(using)
                attachment = SurveyAttachment.objects.using(using).create(
                    survey=survey,
                    file_data=payload,
                    original_filename='ora-01461-check.pdf',
                    file_size=len(payload),
                    mime_type='application/pdf',
                    description='temporary verification row (rolled back)',
                    display_order=0,
                )
                self.stdout.write(f'Inserted: {attachment.pk}')

                stored = blob_to_bytes(
                    SurveyAttachment.objects.using(using)
                    .get(pk=attachment.pk)
                    .file_data
                )
                actual = hashlib.sha256(stored).hexdigest()

                if len(stored) != len(payload):
                    raise CommandError(
                        f'Read back {len(stored):,} bytes, expected '
                        f'{len(payload):,} — the BLOB was truncated.'
                    )
                if actual != expected:
                    raise CommandError(
                        f'Checksum mismatch: stored {actual}, expected {expected}.'
                    )

                self.stdout.write(f'Read back: {len(stored):,} bytes, checksum matches')
                raise _Rollback
        except _Rollback:
            pass

        self.stdout.write(self.style.SUCCESS('OK — large BLOB writes work. Rolled back.'))

    @staticmethod
    def _payload(size_mb):
        """Incompressible, non-ASCII bytes so nothing can quietly mangle them."""
        block = bytes(range(256))
        target = max(1, int(size_mb * 1024 * 1024))
        body = (block * (target // len(block) + 1))[:target]
        return b'%PDF-1.7\r' + body

    def _survey(self, using):
        survey = Survey.objects.using(using).order_by('created_at').first()
        if survey is not None:
            return survey
        return Survey.objects.using(using).create(
            title='ORA-01461 verification',
            description='temporary verification row (rolled back)',
        )
