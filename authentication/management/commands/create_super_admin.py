"""
Django management command to create a super admin user.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a super admin user'

    def handle(self, *args, **options):
        # User details
        email = "seif778811@gmail.com"
        auth_type = "regular"
        password = "Password778811"
        first_name = "Seif"
        last_name = "Eldein"
        role = "super_admin"
        
        self.stdout.write(
            self.style.SUCCESS(f'Creating super_admin user: {email}')
        )
        
        try:
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                self.stdout.write(
                    self.style.ERROR(f'User with email "{email}" already exists!')
                )
                return
            
            # Validate password
            try:
                validate_password(password)
                self.stdout.write(self.style.SUCCESS('Password validation passed'))
            except ValidationError as e:
                self.stdout.write(self.style.ERROR('Password validation failed:'))
                for error in e.messages:
                    self.stdout.write(f'   - {error}')
                return
            
            # Create the user
            user = User.objects.create_user(
                username=email,  # Use email as username for regular users
                email=email,
                password=password,
                auth_type=auth_type,
                first_name=first_name,
                last_name=last_name,
                role=role
            )
            
            self.stdout.write(
                self.style.SUCCESS('Super admin user created successfully!')
            )
            self.stdout.write(f'   - ID: {user.id}')
            self.stdout.write(f'   - Email: {user.email}')
            self.stdout.write(f'   - Username: {user.username}')
            self.stdout.write(f'   - Name: {user.full_name}')
            self.stdout.write(f'   - Role: {user.role}')
            self.stdout.write(f'   - Auth Type: {user.auth_type}')
            self.stdout.write(f'   - Active: {user.is_active}')
            self.stdout.write(f'   - Is Staff: {user.is_staff}')
            self.stdout.write(f'   - Is Superuser: {user.is_superuser}')
            self.stdout.write(f'   - Date Joined: {user.date_joined}')
            
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write(
                self.style.SUCCESS('SUCCESS: Super admin user created!')
            )
            self.stdout.write('=' * 60)
            self.stdout.write('\nLogin credentials:')
            self.stdout.write('  Email: seif778811@gmail.com')
            self.stdout.write('  Password: Password778811')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating user: {str(e)}')
            )
