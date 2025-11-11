"""
Serializers for the authentication API.

This module contains serializers for user-related data that will be
returned by the API endpoints, including both Azure AD and regular authentication.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Group, UserGroup
from adjd_survey.security_utils import validate_and_sanitize_text_input, sanitize_html_input


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for user information.
    
    Returns basic user information that can be safely exposed to the frontend.
    """
    
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'username',  # This will be the Azure AD Object ID
            'email',
            'first_name',
            'last_name',
            'full_name',
            'role',
            'is_active',
            'date_joined',
            'last_login'
        ]
        read_only_fields = ['id', 'username', 'date_joined', 'last_login']
    
    def get_full_name(self, obj):
        """
        Get the user's full name.
        
        Args:
            obj: User instance
            
        Returns:
            Full name string
        """
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Extended serializer for user profile information.
    
    This serializer includes additional fields that might be useful
    for user profile management.
    """
    
    full_name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()
    azure_object_id = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'azure_object_id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'initials',
            'role',
            'role_display',
            'is_active',
            'is_staff',
            'date_joined',
            'last_login'
        ]
        read_only_fields = [
            'id', 
            'azure_object_id', 
            'is_staff', 
            'date_joined', 
            'last_login'
        ]
    
    def get_full_name(self, obj):
        """Get the user's full name."""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email
    
    def get_initials(self, obj):
        """Get the user's initials."""
        if obj.first_name and obj.last_name:
            return f"{obj.first_name[0]}{obj.last_name[0]}".upper()
        elif obj.first_name:
            return obj.first_name[0].upper()
        elif obj.email:
            return obj.email[0].upper()
        return "U"
    
    def get_azure_object_id(self, obj):
        """Get the Azure AD Object ID (stored as username)."""
        return obj.username
    
    def get_role_display(self, obj):
        """Get the human-readable role name."""
        return obj.get_role_display()


class UserGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for UserGroup model (through model).
    """
    
    user = UserSerializer(read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    
    class Meta:
        model = UserGroup
        fields = [
            'id',
            'user',
            'group_name',
            'is_group_admin',
            'joined_at'
        ]
        read_only_fields = ['id', 'joined_at']


class GroupSerializer(serializers.ModelSerializer):
    """
    Serializer for Group model.
    """
    
    admin_count = serializers.ReadOnlyField()
    user_count = serializers.ReadOnlyField()
    admins = UserSerializer(source='get_admins', many=True, read_only=True)
    members = UserSerializer(source='get_members', many=True, read_only=True)
    
    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'description',
            'admin_count',
            'user_count',
            'admins',
            'members',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_name(self, value):
        """Validate and sanitize group name."""
        return validate_and_sanitize_text_input(value, max_length=100, field_name="Group name")
    
    def validate_description(self, value):
        """Validate and sanitize group description."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=500, field_name="Description")


class GroupDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for Group model with user memberships.
    """
    
    user_groups = UserGroupSerializer(many=True, read_only=True)
    admin_count = serializers.ReadOnlyField()
    user_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'description',
            'admin_count',
            'user_count',
            'user_groups',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CreateGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new group with admin assignments.
    """
    
    admin_user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        min_length=1,
        help_text="List of user IDs to be assigned as group admins"
    )
    
    class Meta:
        model = Group
        fields = ['name', 'description', 'admin_user_ids']
    
    def validate_admin_user_ids(self, value):
        """Validate that all admin user IDs exist and are valid."""
        if not value:
            raise serializers.ValidationError("At least one admin must be assigned.")
        
        # Check if all users exist
        existing_users = User.objects.filter(id__in=value).count()
        if existing_users != len(value):
            raise serializers.ValidationError("One or more user IDs do not exist.")
        
        return value
    
    def create(self, validated_data):
        """Create group and assign admins."""
        admin_user_ids = validated_data.pop('admin_user_ids')
        group = Group.objects.create(**validated_data)
        
        # Add admin users to the group
        for user_id in admin_user_ids:
            user = User.objects.get(pk=user_id)
            UserGroup.objects.create(
                user=user,
                group=group,
                is_group_admin=True
            )
        
        return group


class AddUserToGroupSerializer(serializers.Serializer):
    """
    Serializer for adding a user to a group.
    """
    
    user_id = serializers.IntegerField()
    is_group_admin = serializers.BooleanField(default=False)
    
    def validate_user_id(self, value):
        """Validate that the user exists."""
        try:
            User.objects.get(pk=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist.")
        return value


class UpdateUserGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user group membership.
    """
    
    class Meta:
        model = UserGroup
        fields = ['is_group_admin']
    
    def validate(self, data):
        """Validate group admin requirements."""
        if not data.get('is_group_admin', True):
            # If removing admin status, ensure at least one admin remains
            group = self.instance.group
            if group.admin_count == 1 and self.instance.is_group_admin:
                raise serializers.ValidationError(
                    "Cannot remove the last admin from a group."
                )
        return data


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration with email/password.
    """
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'email',
            'password',
            'password_confirm',
            'first_name',
            'last_name'
        ]
    
    def validate_email(self, value):
        """Validate and sanitize email."""
        # Sanitize the email input
        cleaned_email = sanitize_html_input(value, allow_tags=False)
        
        if cleaned_email != value:
            raise serializers.ValidationError("Invalid characters detected in email address.")
        
        if User.objects.email_exists(cleaned_email):
            raise serializers.ValidationError("A user with this email already exists.")
        return cleaned_email
    
    def validate_first_name(self, value):
        """Validate and sanitize first name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=30, field_name="First name")
    
    def validate_last_name(self, value):
        """Validate and sanitize last name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=30, field_name="Last name")
    
    def validate_password(self, value):
        """Validate password meets requirements."""
        # Note: We don't sanitize passwords as they should remain exactly as entered
        # But we do validate against Django's password validators
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
    
    def validate(self, data):
        """Validate password confirmation."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords do not match.")
        return data
    
    def create(self, validated_data):
        """Create a new regular user."""
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        email = validated_data['email']
        
        user = User.objects.create_user(
            username=email,  # Use email as username for regular users
            email=email,
            password=password,
            auth_type='regular',
            **validated_data
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login with email/password.
    """
    email = serializers.EmailField()
    password = serializers.CharField(
        style={'input_type': 'password'}
    )
    
    def validate_email(self, value):
        """Validate and sanitize email input."""
        # Sanitize the email input to prevent XSS
        cleaned_email = sanitize_html_input(value, allow_tags=False)
        
        if cleaned_email != value:
            raise serializers.ValidationError("Invalid characters detected in email address.")
        
        return cleaned_email
    
    def validate(self, data):
        """Validate user credentials using Oracle-compatible method."""
        import logging
        logger = logging.getLogger(__name__)
        
        email = data.get('email')
        password = data.get('password')
        
        if email and password:
            # Check if user exists using Oracle-compatible method
            try:
                logger.info(f"Looking for user with email: {email}")
                user = User.objects.get_by_email(email)
                
                if not user:
                    logger.warning(f"User not found for email: {email}")
                    raise serializers.ValidationError("Invalid email or password.")
                
                logger.info(f"User found: {user.email}")
                
                if user.auth_type != 'regular':
                    logger.warning(f"Invalid auth_type for {email}: {user.auth_type}")
                    raise serializers.ValidationError("Invalid email or password.")
                    
            except serializers.ValidationError:
                # Re-raise validation errors
                raise
            except (TypeError, AttributeError, Exception) as e:
                # Handle isinstance errors from Django's validation or other unexpected errors
                logger.error(f"Error in get_by_email for {email}: {type(e).__name__}: {e}")
                raise serializers.ValidationError("Invalid email or password.")
            
            # Authenticate user using username field
            logger.info(f"Authenticating with username: {user.username}")
            authenticated_user = authenticate(username=user.username, password=password)
            logger.info(f"Authentication result: {'Success' if authenticated_user else 'Failed'}")
            
            if not authenticated_user:
                logger.warning(f"Authentication failed for username: {user.username}")
                raise serializers.ValidationError("Invalid email or password.")
            
            if not authenticated_user.is_active:
                logger.warning(f"User account is disabled: {authenticated_user.username}")
                raise serializers.ValidationError("User account is disabled.")
            
            data['user'] = authenticated_user
            logger.info("Validation successful")
        else:
            raise serializers.ValidationError("Email and password are required.")
        
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password.
    """
    old_password = serializers.CharField(
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        style={'input_type': 'password'},
        min_length=8
    )
    new_password_confirm = serializers.CharField(
        style={'input_type': 'password'}
    )
    
    def validate_old_password(self, value):
        """Validate old password."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
    
    def validate_new_password(self, value):
        """Validate new password meets requirements."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
    
    def validate(self, data):
        """Validate password confirmation."""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError("New passwords do not match.")
        return data
    
    def save(self):
        """Update user password."""
        user = self.context['request'].user
        if user.auth_type != 'regular':
            raise serializers.ValidationError("Password change not allowed for Azure AD users.")
        
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class BulkDeleteUsersSerializer(serializers.Serializer):
    """
    Serializer for bulk user deletion request.
    """
    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        help_text='List of user IDs to delete'
    )
    
    def validate_user_ids(self, value):
        """Validate that user IDs exist and are not the current user."""
        if not value:
            raise serializers.ValidationError("At least one user ID must be provided.")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_ids = []
        for user_id in value:
            if user_id not in seen:
                seen.add(user_id)
                unique_ids.append(user_id)
        
        # Check if current user is trying to delete themselves
        current_user_id = self.context['request'].user.id
        if current_user_id in unique_ids:
            raise serializers.ValidationError("You cannot delete your own account.")
        
        return unique_ids


class ResetUserPasswordSerializer(serializers.Serializer):
    """
    Serializer for resetting a user's password by admin.
    """
    user_id = serializers.IntegerField(
        min_value=1,
        help_text='ID of the user whose password to reset'
    )
    new_password = serializers.CharField(
        min_length=8,
        max_length=128,
        style={'input_type': 'password'},
        help_text='New password for the user'
    )
    
    def validate_new_password(self, value):
        """Validate the new password."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value
    
    def validate_user_id(self, value):
        """Validate that user exists and is not the current user."""
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this ID does not exist.")
        
        # Check if user is trying to reset their own password
        current_user_id = self.context['request'].user.id
        if current_user_id == value:
            raise serializers.ValidationError("Use the change password endpoint to change your own password.")
        
        # Check if user is a regular auth user
        if user.auth_type != 'regular':
            raise serializers.ValidationError("Password reset not allowed for Azure AD users.")
        
        return value


class AzureUserDataSerializer(serializers.Serializer):
    """
    Serializer for individual Azure AD user data in bulk creation.
    
    Note: Object ID is auto-generated from email to create a unique identifier.
    """
    email = serializers.EmailField(
        required=True,
        help_text='User email address (will be used to generate Object ID)'
    )
    first_name = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        default='',
        help_text='First name'
    )
    last_name = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        default='',
        help_text='Last name'
    )
    role = serializers.ChoiceField(
        choices=['user', 'admin', 'super_admin'],
        default='user',
        help_text='User role in the system'
    )
    
    def validate_email(self, value):
        """Validate and sanitize email."""
        cleaned_email = sanitize_html_input(value, allow_tags=False)
        if cleaned_email != value:
            raise serializers.ValidationError("Invalid characters detected in email address.")
        return cleaned_email
    
    def validate_first_name(self, value):
        """Validate and sanitize first name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=30, field_name="First name")
    
    def validate_last_name(self, value):
        """Validate and sanitize last name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=30, field_name="Last name")


class BulkCreateAzureUsersSerializer(serializers.Serializer):
    """
    Serializer for bulk creation of Azure AD users.
    
    This serializer accepts a list of Azure AD user data and creates
    users in the system. Users that already exist (by email) are 
    automatically skipped. Object IDs are auto-generated from email.
    """
    users = serializers.ListField(
        child=AzureUserDataSerializer(),
        min_length=1,
        help_text='List of Azure AD users to create'
    )
    
    def validate_users(self, value):
        """Validate user data and check for duplicates in the request."""
        if not value:
            raise serializers.ValidationError("At least one user must be provided.")
        
        # Check for duplicate emails in the request
        emails = [user['email'] for user in value]
        if len(emails) != len(set(emails)):
            raise serializers.ValidationError("Duplicate emails found in the request.")
        
        return value
