"""
Management command to manage user roles and create super admins.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import models
from authentication.models import Group, UserGroup

User = get_user_model()


class Command(BaseCommand):
    help = 'Manage user roles and group memberships'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-superuser',
            dest='create_superuser',
            action='store_true',
            help='Create a super admin user',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email address for the user',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username (Azure AD Object ID) for the user',
        )
        parser.add_argument(
            '--first-name',
            type=str,
            help='First name for the user',
        )
        parser.add_argument(
            '--last-name',
            type=str,
            help='Last name for the user',
        )
        parser.add_argument(
            '--promote-user',
            type=str,
            help='Promote user to super_admin by email or username',
        )
        parser.add_argument(
            '--demote-user',
            type=str,
            help='Demote user from super_admin to user by email or username',
        )
        parser.add_argument(
            '--list-users',
            action='store_true',
            help='List all users with their roles',
        )
        parser.add_argument(
            '--list-groups',
            action='store_true',
            help='List all groups with their members',
        )

    def handle(self, *args, **options):
        if options['create_superuser']:
            self.create_superuser(options)
        elif options['promote_user']:
            self.promote_user(options['promote_user'])
        elif options['demote_user']:
            self.demote_user(options['demote_user'])
        elif options['list_users']:
            self.list_users()
        elif options['list_groups']:
            self.list_groups()
        else:
            self.stdout.write(
                self.style.ERROR('Please specify an action. Use --help for available options.')
            )

    def create_superuser(self, options):
        """Create a super admin user."""
        email = options.get('email')
        username = options.get('username')
        first_name = options.get('first_name', '')
        last_name = options.get('last_name', '')

        if not email or not username:
            raise CommandError('Both --email and --username are required for creating a superuser.')

        if User.objects.filter(email=email).exists():
            raise CommandError(f'User with email {email} already exists.')

        if User.objects.filter(username=username).exists():
            raise CommandError(f'User with username {username} already exists.')

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role='super_admin'
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Super admin user created successfully:\n'
                f'  Username: {user.username}\n'
                f'  Email: {user.email}\n'
                f'  Name: {user.full_name}\n'
                f'  Role: {user.role}'
            )
        )

    def promote_user(self, identifier):
        """Promote a user to super_admin."""
        try:
            user = User.objects.get(
                models.Q(email=identifier) | models.Q(username=identifier)
            )
        except User.DoesNotExist:
            raise CommandError(f'User with email or username "{identifier}" not found.')

        if user.role == 'super_admin':
            self.stdout.write(
                self.style.WARNING(f'User {user.email} is already a super admin.')
            )
            return

        old_role = user.role
        user.role = 'super_admin'
        user.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'User {user.email} promoted from {old_role} to super_admin.'
            )
        )

    def demote_user(self, identifier):
        """Demote a user from super_admin to user."""
        try:
            user = User.objects.get(
                models.Q(email=identifier) | models.Q(username=identifier)
            )
        except User.DoesNotExist:
            raise CommandError(f'User with email or username "{identifier}" not found.')

        if user.role != 'super_admin':
            self.stdout.write(
                self.style.WARNING(f'User {user.email} is not a super admin.')
            )
            return

        # Check if user is in any groups
        if user.user_groups.exists():
            user.role = 'admin'
            self.stdout.write(
                self.style.SUCCESS(
                    f'User {user.email} demoted from super_admin to admin (user is in groups).'
                )
            )
        else:
            user.role = 'user'
            self.stdout.write(
                self.style.SUCCESS(
                    f'User {user.email} demoted from super_admin to user.'
                )
            )
        
        user.save()

    def list_users(self):
        """List all users with their roles."""
        users = User.objects.all().order_by('role', 'email')
        
        if not users:
            self.stdout.write(self.style.WARNING('No users found.'))
            return

        self.stdout.write('\nUsers:')
        self.stdout.write('-' * 80)
        self.stdout.write(f'{"Email":<30} {"Role":<15} {"Groups":<20} {"Active":<8}')
        self.stdout.write('-' * 80)

        for user in users:
            group_count = user.user_groups.count()
            groups_str = f'{group_count} groups' if group_count > 0 else 'No groups'
            active_str = 'Yes' if user.is_active else 'No'
            
            self.stdout.write(
                f'{user.email:<30} {user.role:<15} {groups_str:<20} {active_str:<8}'
            )

    def list_groups(self):
        """List all groups with their members."""
        groups = Group.objects.all().order_by('name')
        
        if not groups:
            self.stdout.write(self.style.WARNING('No groups found.'))
            return

        self.stdout.write('\nGroups:')
        self.stdout.write('=' * 80)

        for group in groups:
            self.stdout.write(f'\nGroup: {group.name}')
            self.stdout.write(f'Description: {group.description or "No description"}')
            self.stdout.write(f'Created: {group.created_at.strftime("%Y-%m-%d %H:%M")}')
            self.stdout.write(f'Total Members: {group.user_count}')
            self.stdout.write(f'Admins: {group.admin_count}')
            
            if group.user_groups.exists():
                self.stdout.write('\nMembers:')
                self.stdout.write('-' * 60)
                self.stdout.write(f'{"Email":<30} {"Role in Group":<15} {"Joined":<15}')
                self.stdout.write('-' * 60)
                
                for user_group in group.user_groups.all().select_related('user'):
                    role_str = 'Admin' if user_group.is_group_admin else 'Member'
                    joined_str = user_group.joined_at.strftime('%Y-%m-%d')
                    
                    self.stdout.write(
                        f'{user_group.user.email:<30} {role_str:<15} {joined_str:<15}'
                    )
            else:
                self.stdout.write('No members in this group.')
            
            self.stdout.write('')
