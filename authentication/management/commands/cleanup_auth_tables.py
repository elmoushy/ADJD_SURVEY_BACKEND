"""
Management command to clean up Django's default auth tables.

This command removes the auth tables related to groups and permissions
that are not needed for Azure AD authentication.
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Remove Django default auth tables for groups and permissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to remove the auth tables',
        )

    def handle(self, *args, **options):
        """Execute the command."""
        
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'This command will remove the following tables:\n'
                    '  - auth_group\n'
                    '  - auth_group_permissions\n'
                    '  - auth_permission\n'
                    '  - auth_user_groups\n'
                    '  - auth_user_user_permissions\n\n'
                    'Run with --confirm to proceed.'
                )
            )
            return

        tables_to_remove = [
            'auth_group',
            'auth_group_permissions', 
            'auth_permission',
            'auth_user_groups',
            'auth_user_user_permissions'
        ]
        
        with connection.cursor() as cursor:
            # Check which tables exist
            placeholders = ','.join([f"'{table}'" for table in tables_to_remove])
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name IN ({placeholders})"
            )
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            if not existing_tables:
                self.stdout.write(
                    self.style.SUCCESS('No auth tables found to remove.')
                )
                return
            
            # Remove existing tables
            for table in existing_tables:
                try:
                    cursor.execute(f'DROP TABLE IF EXISTS {table}')
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully removed table: {table}')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error removing table {table}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSuccessfully removed {len(existing_tables)} auth tables.\n'
                    'Your application now uses only the essential auth_user table '
                    'for Azure AD authentication.'
                )
            )
