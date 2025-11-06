"""
Django management command to update user role.

Usage:
    python manage.py update_user_role --user-id 2 --role admin
"""

from django.core.management.base import BaseCommand, CommandError
from authentication.models import User


class Command(BaseCommand):
    help = 'Update a user\'s role'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            required=True,
            help='ID of the user to update'
        )
        parser.add_argument(
            '--role',
            type=str,
            required=True,
            choices=['employee', 'manager', 'admin'],
            help='New role for the user'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        new_role = options['role']
        force = options['force']

        try:
            # Find the user
            user = User.objects.get(id=user_id)
            
            # Display current user information
            self.stdout.write(f"Found user: {user}")
            self.stdout.write(f"Current role: {user.role}")
            self.stdout.write(f"Email: {user.email}")
            self.stdout.write(f"Username: {user.username}")
            
            # Check if role is already set
            if user.role == new_role:
                self.stdout.write(
                    self.style.WARNING(f"User already has role '{new_role}'. No changes needed.")
                )
                return
            
            # Ask for confirmation unless --force is used
            if not force:
                confirm = input(f"Update user role from '{user.role}' to '{new_role}'? (y/N): ")
                if confirm.lower() not in ['y', 'yes']:
                    self.stdout.write("Operation cancelled")
                    return
            
            # Update the role
            old_role = user.role
            user.role = new_role
            user.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Successfully updated user role from '{old_role}' to '{new_role}'"
                )
            )
            
            # Verify the change
            updated_user = User.objects.get(id=user_id)
            if updated_user.role == new_role:
                self.stdout.write(
                    self.style.SUCCESS("✅ Role update verified successfully")
                )
            else:
                self.stdout.write(
                    self.style.ERROR("❌ Warning: Role update verification failed")
                )
                
        except User.DoesNotExist:
            raise CommandError(f'User with ID {user_id} does not exist')
        
        except Exception as e:
            raise CommandError(f'Error updating user role: {str(e)}')
