"""
Django management command to delete specific ResponseFollowUp threads by ID.

Oracle-compatible: uses the Django ORM's `filter(id__in=...)` (parameterized
query, no raw SQL / manual NVARCHAR2 quoting needed). Deleting a
ResponseFollowUp cascades to its FollowUpMessage records and their
FollowUpMessageAttachment BLOBs (both are on_delete=CASCADE), so no manual
cleanup of messages/attachments is required.

Usage:
    python manage.py delete_follow_ups                       # deletes the preset IDs below
    python manage.py delete_follow_ups --ids <uuid> <uuid>    # deletes the given IDs instead
    python manage.py delete_follow_ups --dry-run              # preview only, no deletion
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from surveys.models import ResponseFollowUp

DEFAULT_IDS = [
    "d576ce61-8041-41e5-b1d7-40487da65b00",
    "699ea639-c5cd-4dd0-bdb5-e9ecad167808",
    "43456b21-f193-4a2a-8571-87e00b5b17ae",
    "70214e6f-670d-46bc-8951-dfbdd4b2bf34",
    "95b482c8-9234-483f-b38f-89a3dd8dd6ab",
]


class Command(BaseCommand):
    help = "Delete specific follow-up threads (and their messages/attachments) by ID"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            nargs="+",
            default=DEFAULT_IDS,
            help="One or more ResponseFollowUp UUIDs to delete (defaults to the preset list)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        ids = options["ids"]
        dry_run = options["dry_run"]

        threads = ResponseFollowUp.objects.filter(id__in=ids)
        found_ids = {str(t.id) for t in threads}
        missing_ids = [i for i in ids if i not in found_ids]

        self.stdout.write(f"Requested: {len(ids)} follow-up(s)")
        self.stdout.write(f"Found:     {threads.count()} follow-up(s)")
        if missing_ids:
            self.stdout.write(self.style.WARNING(f"Not found:  {', '.join(missing_ids)}"))

        if threads.count() == 0:
            self.stdout.write(self.style.WARNING("Nothing to delete."))
            return

        self.stdout.write("\nFollow-ups to delete:")
        for t in threads:
            self.stdout.write(f"  - {t.id} [{t.status}] ({t.messages.count()} message(s))")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - no data was deleted"))
            return

        with transaction.atomic():
            deleted_count, deleted_detail = ResponseFollowUp.objects.filter(id__in=ids).delete()

        self.stdout.write(self.style.SUCCESS(
            f"\nDeleted {deleted_count} row(s) total (threads + messages + attachments):"
        ))
        for model_label, count in deleted_detail.items():
            self.stdout.write(f"  - {model_label}: {count}")
