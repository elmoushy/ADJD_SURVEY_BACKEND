"""
API Views for authentication endpoints.

This module provides REST API endpoints for user authentication and profile management.
Supports both Azure AD JWT authentication and regular email/password authentication.
"""

import logging
from datetime import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from csp.decorators import csp_exempt
from django.db import transaction, models
from .serializers import (
    UserSerializer, UserProfileSerializer, GroupSerializer, 
    GroupDetailSerializer, CreateGroupSerializer, AddUserToGroupSerializer,
    UpdateUserGroupSerializer, UserGroupSerializer,
    UserRegistrationSerializer, UserLoginSerializer, ChangePasswordSerializer,
    BulkDeleteUsersSerializer, ResetUserPasswordSerializer
)
from .models import Group, UserGroup
from .permissions import (
    IsSuperAdmin, IsAdminOrSuperAdmin, IsGroupAdmin, 
    CanViewGroup, CanManageGroupUsers, CanAccessUserData
)
from .dual_auth import UniversalAuthentication
from adjd_survey.security_utils import log_security_event
from adjd_survey.middleware.brute_force_protection import (
    clear_login_attempts, get_remaining_attempts
)


User = get_user_model()
logger = logging.getLogger(__name__)


class CurrentUserView(APIView):
    """
    API endpoint to get current user information.
    
    This endpoint returns information about the currently authenticated user
    based on the Azure AD JWT token.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get current user information.
        
        Returns:
            User information in JSON format
        """
        try:
            serializer = UserProfileSerializer(request.user)
            logger.info(f"User profile accessed: {request.user.email}")
            
            return Response({
                'user': serializer.data,
                'message': 'User information retrieved successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving user profile: {str(e)}")
            return Response({
                'detail': 'Error retrieving user information'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def patch(self, request):
        """
        Update current user information.
        
        Args:
            request: HTTP request with user data to update
            
        Returns:
            Updated user information
        """
        try:
            serializer = UserProfileSerializer(
                request.user, 
                data=request.data, 
                partial=True
            )
            
            if serializer.is_valid():
                serializer.save()
                logger.info(f"User profile updated: {request.user.email}")
                
                return Response({
                    'user': serializer.data,
                    'message': 'Profile updated successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'detail': 'Invalid data provided',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}")
            return Response({
                'detail': 'Error updating user information'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_info(request):
    """
    Simple endpoint to get current user information.
    
    This is a function-based view that provides basic user information.
    Use this for simple user info requests.
    
    Args:
        request: HTTP request object
        
    Returns:
        JSON response with user information
    """
    try:
        serializer = UserSerializer(request.user)
        
        return Response({
            'id': serializer.data['id'],
            'email': serializer.data['email'],
            'name': serializer.data['full_name'],
            'first_name': serializer.data['first_name'],
            'last_name': serializer.data['last_name'],
            'is_active': serializer.data['is_active']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in user_info endpoint: {str(e)}")
        return Response({
            'detail': 'Error retrieving user information'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def health_check(request):
    """
    Health check endpoint for authenticated users.
    
    This endpoint can be used to verify that authentication is working
    and the API is responding correctly.
    
    Args:
        request: HTTP request object
        
    Returns:
        JSON response with health status
    """
    return Response({
        'status': 'healthy',
        'authenticated': True,
        'user': request.user.email,
        'message': 'Authentication is working correctly'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout endpoint with JWT token blacklisting.
    
    This endpoint handles logout for both regular and Azure AD users by:
    1. Blacklisting the provided refresh token to prevent further use
    2. Invalidating the current session
    3. Logging the logout event
    
    Args:
        request: HTTP request object containing refresh_token in body
        
    Returns:
        JSON response confirming logout
        
    Request body:
        {
            "refresh_token": "your_refresh_token_here"
        }
    """
    try:
        # Import blacklist functionality
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import TokenError
        
        # Get refresh token from request body
        refresh_token = request.data.get('refresh_token')
        
        if refresh_token:
            try:
                # Blacklist the refresh token
                token = RefreshToken(refresh_token)
                token.blacklist()
                
                logger.info(f"User logged out with token blacklisting: {request.user.email}")
                
                return Response({
                    'message': 'Logged out successfully',
                    'detail': 'Refresh token has been blacklisted'
                }, status=status.HTTP_200_OK)
                
            except TokenError as e:
                logger.warning(f"Invalid token during logout for user {request.user.email}: {str(e)}")
                
                return Response({
                    'message': 'Logged out successfully',
                    'detail': 'Invalid or expired token provided, but logout completed'
                }, status=status.HTTP_200_OK)
        else:
            # No refresh token provided - basic logout
            logger.info(f"User logged out without token blacklisting: {request.user.email}")
            
            return Response({
                'message': 'Logged out successfully',
                'detail': 'No refresh token provided. Please clear your authentication tokens on the client side'
            }, status=status.HTTP_200_OK)
            
    except ImportError:
        # Fallback if blacklist functionality is not available
        logger.info(f"User logged out (no blacklist available): {request.user.email}")
        
        return Response({
            'message': 'Logged out successfully',
            'detail': 'Token blacklisting not available. Please clear your authentication tokens on the client side'
        }, status=status.HTTP_200_OK)


class UserStatsView(APIView):
    """
    API endpoint to get user statistics and metadata.
    
    This endpoint provides additional information about the user's
    account and usage statistics.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get user statistics and metadata.
        
        Returns:
            User statistics in JSON format
        """
        try:
            user = request.user
            
            # Calculate basic statistics
            days_since_joined = (timezone.now() - user.date_joined).days if user.date_joined else 0
            last_login_days = (timezone.now() - user.last_login).days if user.last_login else None
            
            stats = {
                'account_age_days': days_since_joined,
                'last_login_days_ago': last_login_days,
                'is_first_login': user.last_login is None,
                'account_status': 'active' if user.is_active else 'inactive',
                'profile_completion': self._calculate_profile_completion(user)
            }
            
            return Response({
                'user_id': user.id,
                'stats': stats,
                'message': 'User statistics retrieved successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving user stats: {str(e)}")
            return Response({
                'detail': 'Error retrieving user statistics'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _calculate_profile_completion(self, user):
        """
        Calculate profile completion percentage.
        
        Args:
            user: User instance
            
        Returns:
            Profile completion percentage (0-100)
        """
        fields = ['email', 'first_name', 'last_name']
        completed_fields = sum(1 for field in fields if getattr(user, field, None))
        return int((completed_fields / len(fields)) * 100)


# Group Management Views

class GroupListView(APIView):
    """
    API endpoint for listing and creating groups.
    """
    
    def get_permissions(self):
        """Set permissions based on request method."""
        if self.request.method == 'POST':
            permission_classes = [IsSuperAdmin]
        else:
            permission_classes = [IsAdminOrSuperAdmin]
        
        return [permission() for permission in permission_classes]
    
    def get(self, request):
        """
        List groups based on user role.
        
        - super_admin: Can see all groups
        - admin: Can see their own groups only
        """
        user = request.user
        
        if user.role == 'super_admin':
            # Super admins can see all groups
            groups = Group.objects.all()
        else:
            # Admins can see only their groups
            groups = Group.objects.filter(users=user)
        
        serializer = GroupSerializer(groups, many=True)
        return Response({
            'groups': serializer.data,
            'count': groups.count()
        }, status=status.HTTP_200_OK)
    
    def post(self, request):
        """
        Create a new group (super_admin only).
        """
        serializer = CreateGroupSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    group = serializer.save()
                    
                # Return the created group with details
                detail_serializer = GroupDetailSerializer(group)
                return Response({
                    'group': detail_serializer.data,
                    'message': 'Group created successfully'
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                logger.error(f"Error creating group: {str(e)}")
                return Response({
                    'detail': 'Error creating group'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GroupDetailView(APIView):
    """
    API endpoint for retrieving, updating, and deleting specific groups.
    """
    
    def get_permissions(self):
        """Set permissions based on request method."""
        if self.request.method == 'GET':
            permission_classes = [CanViewGroup]
        else:
            permission_classes = [IsSuperAdmin]
        
        return [permission() for permission in permission_classes]
    
    def get_group(self, group_id, user):
        """Get group based on user permissions."""
        try:
            group = Group.objects.get(id=group_id)
            
            # Check permissions
            if user.role == 'super_admin':
                return group
            elif user.role == 'admin' and group.users.filter(id=user.id).exists():
                return group
            else:
                return None
                
        except Group.DoesNotExist:
            return None
    
    def get(self, request, group_id):
        """Get group details."""
        group = self.get_group(group_id, request.user)
        
        if not group:
            return Response({
                'detail': 'Group not found or access denied.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = GroupDetailSerializer(group)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, group_id):
        """Update group (super_admin only)."""
        group = self.get_group(group_id, request.user)
        if not group:
            return Response({
                'detail': 'Group not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = GroupSerializer(group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, group_id):
        """Delete group (super_admin only)."""
        group = self.get_group(group_id, request.user)
        if not group:
            return Response({
                'detail': 'Group not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        group_name = group.name
        group.delete()
        
        return Response({
            'message': f'Group "{group_name}" deleted successfully'
        }, status=status.HTTP_200_OK)


class GroupUsersView(APIView):
    """
    API endpoint for managing users in a group.
    """
    
    permission_classes = [CanManageGroupUsers]
    
    def get_group(self, group_id, user):
        """Get group based on user permissions."""
        try:
            group = Group.objects.get(id=group_id)
            
            if user.role == 'super_admin':
                return group
            elif user.role == 'admin' and group.users.filter(id=user.id).exists():
                return group
            else:
                return None
                
        except Group.DoesNotExist:
            return None
    
    def post(self, request, group_id):
        """Add user to group."""
        user = request.user
        
        group = self.get_group(group_id, user)
        if not group:
            return Response({
                'detail': 'Group not found or access denied.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = AddUserToGroupSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    user_to_add = User.objects.get(id=serializer.validated_data['user_id'])
                    is_group_admin = serializer.validated_data['is_group_admin']
                    
                    # Check if user is already in the group
                    if UserGroup.objects.filter(user=user_to_add, group=group).exists():
                        return Response({
                            'detail': 'User is already in this group.'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Create the membership
                    user_group = UserGroup.objects.create(
                        user=user_to_add,
                        group=group,
                        is_group_admin=is_group_admin
                    )
                    
                    # Return updated group details
                    group_serializer = GroupDetailSerializer(group)
                    return Response({
                        'group': group_serializer.data,
                        'message': f'User {user_to_add.email} added to group successfully'
                    }, status=status.HTTP_201_CREATED)
                    
            except User.DoesNotExist:
                return Response({
                    'detail': 'User not found.'
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error(f"Error adding user to group: {str(e)}")
                return Response({
                    'detail': 'Error adding user to group'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GroupUserDetailView(APIView):
    """
    API endpoint for managing individual user membership in a group.
    """
    
    permission_classes = [CanManageGroupUsers]
    
    def get_user_group(self, group_id, user_id, request_user):
        """Get UserGroup instance based on permissions."""
        try:
            group = Group.objects.get(id=group_id)
            user_group = UserGroup.objects.get(group=group, user_id=user_id)
            
            # Check permissions
            if request_user.role == 'super_admin':
                return user_group
            elif request_user.role == 'admin' and group.users.filter(id=request_user.id).exists():
                # Check if request user is admin of this group
                is_group_admin = UserGroup.objects.filter(
                    user=request_user, group=group, is_group_admin=True
                ).exists()
                if is_group_admin:
                    return user_group
            
            return None
            
        except (Group.DoesNotExist, UserGroup.DoesNotExist):
            return None
    
    def put(self, request, group_id, user_id):
        """Update user's group membership."""
        user_group = self.get_user_group(group_id, user_id, request.user)
        
        if not user_group:
            return Response({
                'detail': 'User group membership not found or access denied.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UpdateUserGroupSerializer(user_group, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            
            # Return updated group details
            group_serializer = GroupDetailSerializer(user_group.group)
            return Response({
                'group': group_serializer.data,
                'message': 'User group membership updated successfully'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, group_id, user_id):
        """Remove user from group."""
        user_group = self.get_user_group(group_id, user_id, request.user)
        
        if not user_group:
            return Response({
                'detail': 'User group membership not found or access denied.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if this is the last admin
        if user_group.is_group_admin and user_group.group.admin_count == 1:
            return Response({
                'detail': 'Cannot remove the last admin from a group.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user_email = user_group.user.email
        group_name = user_group.group.name
        user_group.delete()
        
        return Response({
            'message': f'User {user_email} removed from group "{group_name}" successfully'
        }, status=status.HTTP_200_OK)


class AllUsersView(APIView):
    """
    API endpoint for listing all users (super_admin only).
    """
    
    permission_classes = [IsSuperAdmin]
    
    def get(self, request):
        """List all users (super_admin only)."""
        users = User.objects.all().order_by('email')
        serializer = UserSerializer(users, many=True)
        
        return Response({
            'users': serializer.data,
            'count': users.count()
        }, status=status.HTTP_200_OK)


class AllUsersNamesEmailsView(APIView):
    """
    API endpoint for getting all users with just name and email (no pagination).
    
    This endpoint is useful for email recipient selection in the email communication system.
    Returns a lightweight list of all active users with their ID, full name, and email.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """
        Get all active users with name and email without pagination.
        
        Returns:
            List of users with id, full_name, and email
        """
        try:
            # Get all active users ordered by name
            users = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'email')
            
            # Build lightweight response
            users_data = [
                {
                    'id': user.id,
                    'full_name': user.full_name,
                    'email': user.email
                }
                for user in users
            ]
            
            return Response({
                'users': users_data,
                'count': len(users_data)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving all users names and emails: {str(e)}")
            return Response({
                'detail': 'Error retrieving users list'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# New endpoints implementation

class RolesListView(APIView):
    """
    API endpoint for getting available user roles for dropdowns.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAdminOrSuperAdmin]
    
    def get(self, request):
        """Get list of available user roles."""
        try:
            roles = [
                {'value': role[0], 'display': role[1]} 
                for role in User.ROLE_CHOICES
            ]
            
            return Response({
                'roles': roles
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving roles: {str(e)}")
            return Response({
                'detail': 'Error retrieving roles'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroupDropdownView(APIView):
    """
    API endpoint for getting lightweight group list for dropdowns.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAdminOrSuperAdmin]
    
    def get(self, request):
        """Get lightweight list of groups for dropdown selections."""
        try:
            user = request.user
            
            if user.role == 'super_admin':
                # Super admins can see all groups
                groups = Group.objects.all()
            else:
                # Admins can see only their groups
                groups = Group.objects.filter(users=user)
            
            groups_data = [
                {'id': group.id, 'name': group.name} 
                for group in groups.order_by('name')
            ]
            
            return Response({
                'groups': groups_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving groups dropdown: {str(e)}")
            return Response({
                'detail': 'Error retrieving groups'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserSearchView(APIView):
    """
    API endpoint for searching users by name or email.
    """
    
    permission_classes = [IsAdminOrSuperAdmin]
    
    def get(self, request):
        """Search users by name or email for user selection."""
        try:
            user = request.user
            query = request.query_params.get('q', '').strip()
            limit = int(request.query_params.get('limit', 20))
            
            if not query:
                return Response({
                    'users': [],
                    'count': 0
                }, status=status.HTTP_200_OK)
            
            # Base queryset
            if user.role == 'super_admin':
                # Super admins can search all users
                queryset = User.objects.all()
            else:
                # Admins can search users in their groups plus unassigned users
                user_groups = user.user_groups.all()
                group_ids = [ug.group_id for ug in user_groups]
                queryset = User.objects.filter(
                    models.Q(groups__id__in=group_ids) | 
                    models.Q(groups__isnull=True)
                ).distinct()
            
            # Apply search filters
            queryset = queryset.filter(
                models.Q(email__icontains=query) |
                models.Q(first_name__icontains=query) |
                models.Q(last_name__icontains=query)
            ).order_by('email')[:limit]
            
            users_data = [
                {
                    'id': u.id,
                    'email': u.email,
                    'full_name': u.full_name,
                    'role': u.role,
                    'is_active': u.is_active
                } 
                for u in queryset
            ]
            
            return Response({
                'users': users_data,
                'count': len(users_data)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error searching users: {str(e)}")
            return Response({
                'detail': 'Error searching users'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserRoleUpdateView(APIView):
    """
    API endpoint for updating user roles (super_admin only).
    """
    
    permission_classes = [IsSuperAdmin]
    
    def put(self, request, user_id):
        """Update user role."""
        try:
            target_user = User.objects.get(id=user_id)
            new_role = request.data.get('role')
            
            if new_role not in [role[0] for role in User.ROLE_CHOICES]:
                return Response({
                    'role': ['Invalid role selection.']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            old_role = target_user.role
            target_user.role = new_role
            target_user.save()
            
            logger.info(f"User {target_user.email} role changed from {old_role} to {new_role} by {request.user.email}")
            
            serializer = UserSerializer(target_user)
            return Response({
                'user': serializer.data,
                'message': 'User role updated successfully'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'detail': 'User not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating user role: {str(e)}")
            return Response({
                'detail': 'Error updating user role'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BulkAddUsersView(APIView):
    """
    API endpoint for adding multiple users to a group at once.
    """
    
    permission_classes = [CanManageGroupUsers]
    
    def post(self, request):
        """Add multiple users to a group."""
        try:
            group_id = request.data.get('group_id')
            user_ids = request.data.get('user_ids', [])
            is_group_admin = request.data.get('is_group_admin', False)
            
            if not group_id:
                return Response({
                    'group_id': ['This field is required.']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not user_ids:
                return Response({
                    'user_ids': ['At least one user ID is required.']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get the group
            try:
                group = Group.objects.get(id=group_id)
            except Group.DoesNotExist:
                return Response({
                    'detail': 'Group not found.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check permissions
            user = request.user
            if user.role != 'super_admin':
                # Check if user is admin of this group
                is_admin = UserGroup.objects.filter(
                    user=user, group=group, is_group_admin=True
                ).exists()
                if not is_admin:
                    return Response({
                        'detail': 'You do not have permission to manage this group.'
                    }, status=status.HTTP_403_FORBIDDEN)
            
            added_users = []
            already_in_group = []
            
            with transaction.atomic():
                for user_id in user_ids:
                    try:
                        target_user = User.objects.get(id=user_id)
                        
                        # Check if user is already in group
                        if UserGroup.objects.filter(user=target_user, group=group).exists():
                            already_in_group.append(target_user.email)
                            continue
                        
                        # Add user to group
                        UserGroup.objects.create(
                            user=target_user,
                            group=group,
                            is_group_admin=is_group_admin
                        )
                        
                        added_users.append({
                            'id': target_user.id,
                            'email': target_user.email,
                            'full_name': target_user.full_name
                        })
                        
                    except User.DoesNotExist:
                        continue
            
            message = f"{len(added_users)} users added to group successfully"
            if already_in_group:
                message += f". {len(already_in_group)} users were already in the group."
            
            return Response({
                'group': {
                    'id': group.id,
                    'name': group.name,
                    'user_count': group.user_count,
                    'admin_count': group.admin_count
                },
                'added_users': added_users,
                'already_in_group': already_in_group,
                'message': message
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error in bulk add users: {str(e)}")
            return Response({
                'detail': 'Error adding users to group'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserGroupsView(APIView):
    """
    API endpoint for getting all groups a specific user belongs to.
    """
    
    permission_classes = [IsAdminOrSuperAdmin]
    
    def get(self, request, user_id):
        """Get all groups a specific user belongs to."""
        try:
            # Check if target user exists
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({
                    'detail': 'User not found.'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check permissions
            request_user = request.user
            if request_user.role != 'super_admin':
                # Admins can only see users in their groups
                admin_groups = UserGroup.objects.filter(
                    user=request_user, is_group_admin=True
                ).values_list('group_id', flat=True)
                
                target_user_groups = UserGroup.objects.filter(
                    user=target_user, group_id__in=admin_groups
                )
                
                if not target_user_groups.exists():
                    return Response({
                        'detail': 'You do not have permission to view this user.'
                    }, status=status.HTTP_403_FORBIDDEN)
            
            # Get user's group memberships
            user_groups = UserGroup.objects.filter(user=target_user).select_related('group')
            
            groups_data = [
                {
                    'id': ug.group.id,
                    'name': ug.group.name,
                    'is_group_admin': ug.is_group_admin,
                    'joined_at': ug.joined_at
                }
                for ug in user_groups.order_by('group__name')
            ]
            
            return Response({
                'user': {
                    'id': target_user.id,
                    'email': target_user.email,
                    'full_name': target_user.full_name,
                    'role': target_user.role
                },
                'groups': groups_data,
                'group_count': len(groups_data)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving user groups: {str(e)}")
            return Response({
                'detail': 'Error retrieving user groups'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DashboardStatsView(APIView):
    """
    API endpoint for getting dashboard statistics for user management overview.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAdminOrSuperAdmin]
    
    def get(self, request):
        """Get dashboard statistics."""
        try:
            user = request.user
            
            if user.role == 'super_admin':
                # Super admin sees global stats
                total_users = User.objects.count()
                total_groups = Group.objects.count()
                active_users = User.objects.filter(is_active=True).count()
                
                # Role breakdown
                super_admins = User.objects.filter(role='super_admin').count()
                admins = User.objects.filter(role='admin').count()
                regular_users = User.objects.filter(role='user').count()
                
                # Recent activity - get recent group memberships
                recent_memberships = UserGroup.objects.select_related(
                    'user', 'group'
                ).order_by('-joined_at')[:10]
                
            else:
                # Admin sees stats for their groups only
                admin_groups = Group.objects.filter(
                    user_groups__user=user,
                    user_groups__is_group_admin=True
                )
                
                total_groups = admin_groups.count()
                
                # Get users in admin's groups
                users_in_groups = User.objects.filter(
                    groups__in=admin_groups
                ).distinct()
                
                total_users = users_in_groups.count()
                active_users = users_in_groups.filter(is_active=True).count()
                
                # Role breakdown for users in admin's groups
                super_admins = users_in_groups.filter(role='super_admin').count()
                admins = users_in_groups.filter(role='admin').count()
                regular_users = users_in_groups.filter(role='user').count()
                
                # Recent activity in admin's groups
                recent_memberships = UserGroup.objects.filter(
                    group__in=admin_groups
                ).select_related('user', 'group').order_by('-joined_at')[:10]
            
            # Format recent activity
            recent_activity = []
            for membership in recent_memberships:
                activity = {
                    'type': 'user_added_to_group',
                    'user': membership.user.email,
                    'group': membership.group.name,
                    'timestamp': membership.joined_at,
                    'is_admin': membership.is_group_admin
                }
                recent_activity.append(activity)
            
            stats = {
                'total_users': total_users,
                'total_groups': total_groups,
                'active_users': active_users,
                'super_admins': super_admins,
                'admins': admins,
                'regular_users': regular_users,
                'recent_activity': recent_activity
            }
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving dashboard stats: {str(e)}")
            return Response({
                'detail': 'Error retrieving dashboard statistics'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================
# Azure AD Authentication Views
# =============================================

@method_decorator(csp_exempt(), name='dispatch')
class AzureADLoginView(APIView):
    """
    API endpoint for Azure AD login with access token exchange.
    
    This endpoint:
    1. Receives an Azure AD access token from the frontend
    2. Validates the token using Azure AD JWKS
    3. Creates or updates the user in the database
    4. Returns application JWT tokens and user details
    
    Flow:
    - Frontend obtains Azure AD access token
    - Frontend sends token to this endpoint
    - Backend validates token and creates/updates user
    - Backend returns application JWT tokens
    """
    
    permission_classes = [AllowAny]
    
    def options(self, request, *args, **kwargs):
        """
        Handle OPTIONS requests for CORS preflight.
        
        This ensures that browsers can make preflight requests to check
        if the actual POST request is allowed.
        """
        return Response(status=status.HTTP_200_OK)
    
    def post(self, request):
        """
        Exchange Azure AD access token for application JWT tokens.
        
        Request body:
            {
                "access_token": "Azure AD access token from frontend"
            }
        
        Returns:
            {
                "message": "Login successful",
                "tokens": {
                    "access": "application access token",
                    "refresh": "application refresh token"
                },
                "user": {
                    "id": 1,
                    "username": "object_id",
                    "email": "user@example.com",
                    "first_name": "First",
                    "last_name": "Last",
                    "full_name": "First Last",
                    "role": "employee",
                    "is_active": true,
                    "date_joined": "2025-11-05T...",
                    "last_login": "2025-11-05T..."
                }
            }
        """
        try:
            # Get Azure AD token from request body
            azure_token = request.data.get('access_token')
            
            if not azure_token:
                return Response({
                    'detail': 'Azure AD access token is required',
                    'field': 'access_token'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Use the Azure AD authentication class to validate token
            from .azure_auth import AzureADAuthentication
            
            azure_auth = AzureADAuthentication()
            
            try:
                # Validate Azure AD token and get/create user
                auth_result = azure_auth.authenticate_credentials(azure_token)
                
                if not auth_result:
                    return Response({
                        'detail': 'Invalid Azure AD token'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                user, validated_token = auth_result
                
            except Exception as e:
                logger.error(f"Azure AD token validation failed: {str(e)}")
                return Response({
                    'detail': str(e)
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            # Generate application JWT tokens
            try:
                from rest_framework_simplejwt.tokens import RefreshToken
                
                # Create JWT tokens for the authenticated user
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                
                # Update last login
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                # Log successful Azure AD login
                log_security_event(
                    event_type='successful_azure_login',
                    user=user,
                    request=request,
                    details={
                        'login_method': 'azure_ad',
                        'user_created': user.date_joined == user.last_login
                    }
                )
                
                logger.info(f"Azure AD user logged in: {user.email}")
                
                # Return response matching your desired format
                return Response({
                    'message': 'Login successful',
                    'tokens': {
                        'access': str(access_token),
                        'refresh': str(refresh),
                    },
                    'user': UserSerializer(user).data
                }, status=status.HTTP_200_OK)
                
            except ImportError:
                logger.error("JWT package not available")
                return Response({
                    'detail': 'JWT tokens not available - please install djangorestframework-simplejwt'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"Error during Azure AD login: {str(e)}")
            return Response({
                'detail': 'Azure AD login failed due to server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================
# Regular Authentication Views (Email/Password)
# =============================================

class RegisterView(APIView):
    """
    API endpoint for user registration with email/password.
    
    This endpoint allows new users to register with email and password,
    creating a regular authentication account (not Azure AD).
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """
        Register a new user with email/password.
        
        Returns:
            User information and JWT tokens
        """
        try:
            serializer = UserRegistrationSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()
                
                # Import here to avoid circular imports and handle case where package isn't installed yet
                try:
                    from rest_framework_simplejwt.tokens import RefreshToken
                    
                    # Generate JWT tokens
                    refresh = RefreshToken.for_user(user)
                    access_token = refresh.access_token
                    
                    # Update last login
                    user.last_login = timezone.now()
                    user.save()
                    
                    logger.info(f"New user registered: {user.email}")
                    
                    return Response({
                        'message': 'User registered successfully',
                        'user': UserSerializer(user).data,
                        'tokens': {
                            'access': str(access_token),
                            'refresh': str(refresh),
                        }
                    }, status=status.HTTP_201_CREATED)
                    
                except ImportError:
                    # JWT package not installed, return user data without tokens
                    logger.warning("JWT package not installed - returning user data without tokens")
                    return Response({
                        'message': 'User registered successfully',
                        'user': UserSerializer(user).data,
                        'note': 'JWT tokens not available - please install djangorestframework-simplejwt'
                    }, status=status.HTTP_201_CREATED)
                
            else:
                return Response({
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error during user registration: {str(e)}")
            return Response({
                'detail': 'Registration failed due to server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    """
    API endpoint for user login with email/password.
    
    This endpoint authenticates users with email/password and returns JWT tokens.
    Includes brute force protection.
    """
    
    permission_classes = [AllowAny]
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def post(self, request):
        """
        Authenticate user with email/password.
        
        Returns:
            User information and JWT tokens
        """
        try:
            email = request.data.get('email', '')
            ip_address = self.get_client_ip(request)
            
            # Check remaining attempts before processing
            remaining_attempts = get_remaining_attempts(email=email, ip=ip_address)
            
            serializer = UserLoginSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.validated_data['user']
                
                # Import here to avoid circular imports and handle case where package isn't installed yet
                try:
                    from rest_framework_simplejwt.tokens import RefreshToken
                    
                    # Generate JWT tokens
                    refresh = RefreshToken.for_user(user)
                    access_token = refresh.access_token
                    
                    # Update last login
                    user.last_login = timezone.now()
                    try:
                        user.save(update_fields=['last_login'])
                    except Exception as save_error:
                        logger.warning(f"Could not update last login: {save_error}")
                        # Continue without saving last_login to avoid breaking login
                        pass
                    
                    # Clear login attempts on successful login
                    clear_login_attempts(email=user.email, ip=ip_address)
                    
                    # Log successful login
                    log_security_event(
                        event_type='successful_login',
                        user=user,
                        request=request,
                        details={'login_method': 'email_password'}
                    )
                    
                    logger.info(f"User logged in: {user.email}")
                    
                    return Response({
                        'message': 'Login successful',
                        'user': UserSerializer(user).data,
                        'tokens': {
                            'access': str(access_token),
                            'refresh': str(refresh),
                        }
                    }, status=status.HTTP_200_OK)
                    
                except ImportError:
                    # JWT package not installed
                    logger.warning("JWT package not installed - login not available")
                    return Response({
                        'detail': 'JWT tokens not available - please install djangorestframework-simplejwt'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
            else:
                # Log failed login attempt
                log_security_event(
                    event_type='failed_login_validation',
                    request=request,
                    details={
                        'email': email,
                        'remaining_attempts': remaining_attempts,
                        'errors': serializer.errors
                    }
                )
                
                response_data = {
                    'errors': serializer.errors
                }
                
                # Add remaining attempts info if rate limiting is in effect
                if remaining_attempts <= 3:  # Show warning when attempts are low
                    response_data['remaining_attempts'] = remaining_attempts
                    response_data['warning'] = f'You have {remaining_attempts} login attempts remaining.'
                
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error during user login: {str(e)}")
            return Response({
                'detail': 'Login failed due to server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChangePasswordView(APIView):
    """
    API endpoint for changing user password.
    
    This endpoint allows regular users to change their password.
    Azure AD users cannot change passwords through this endpoint.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Change user password.
        
        Returns:
            Success message
        """
        try:
            if request.user.auth_type != 'regular':
                return Response({
                    'detail': 'Password change not allowed for Azure AD users'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                
                logger.info(f"Password changed for user: {request.user.email}")
                
                return Response({
                    'message': 'Password changed successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error during password change: {str(e)}")
            return Response({
                'detail': 'Password change failed due to server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddUserView(APIView):
    """
    API endpoint for admins to add new users.
    
    This endpoint allows admins and super_admins to create new users
    with either regular email/password authentication or Azure AD authentication.
    """
    
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    
    def post(self, request):
        """
        Create a new user (admin/super_admin only).
        
        Returns:
            User information
        """
        try:
            # Extract data
            email = request.data.get('email')
            auth_type = request.data.get('auth_type', 'regular')
            password = request.data.get('password')
            first_name = request.data.get('first_name', '')
            last_name = request.data.get('last_name', '')
            role = request.data.get('role', 'user')
            
            # Validate required fields
            if not email:
                return Response({
                    'errors': {'email': ['This field is required.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate auth_type
            if auth_type not in ['regular', 'azure']:
                return Response({
                    'errors': {'auth_type': ['Must be either "regular" or "azure".']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # For regular users, password is required
            if auth_type == 'regular' and not password:
                return Response({
                    'errors': {'password': ['Password is required for regular users.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate role
            valid_roles = ['user', 'admin', 'super_admin']
            if role not in valid_roles:
                return Response({
                    'errors': {'role': [f'Role must be one of: {", ".join(valid_roles)}']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Only super_admins can create super_admins
            if role == 'super_admin' and request.user.role != 'super_admin':
                return Response({
                    'errors': {'role': ['Only super_admins can create super_admin users.']}
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Check if user already exists
            if User.objects.email_exists(email):
                return Response({
                    'errors': {'email': ['A user with this email already exists.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate password if provided
            if auth_type == 'regular' and password:
                from django.contrib.auth.password_validation import validate_password
                from django.core.exceptions import ValidationError
                try:
                    validate_password(password)
                except ValidationError as e:
                    return Response({
                        'errors': {'password': list(e.messages)}
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create the user
            username = email if auth_type == 'regular' else f"azure_{email}"
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password if auth_type == 'regular' else None,
                auth_type=auth_type,
                first_name=first_name,
                last_name=last_name,
                role=role
            )
            
            logger.info(f"New user created by {request.user.email}: {user.email} ({user.auth_type})")
            
            return Response({
                'message': 'User created successfully',
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error during user creation: {str(e)}")
            return Response({
                'detail': 'User creation failed due to server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================
# Custom JWT Views (Oracle Compatible)
# =============================================

class CustomTokenRefreshView(APIView):
    """
    Custom JWT Token Refresh View that doesn't use token blacklisting.
    
    This view is designed for Oracle database compatibility where the
    token_blacklist app is not available. It refreshes JWT tokens without
    trying to track outstanding tokens.
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """
        Refresh JWT access token using refresh token.
        
        Args:
            request: HTTP request containing refresh token
            
        Returns:
            New access and refresh tokens
            
        Request body:
            {
                "refresh": "your_refresh_token_here"
            }
        """
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
            from rest_framework_simplejwt.settings import api_settings
            
            # Get refresh token from request
            refresh_token = request.data.get('refresh')
            
            if not refresh_token:
                return Response({
                    'detail': 'Refresh token is required',
                    'code': 'refresh_required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                # Validate and refresh the token
                refresh = RefreshToken(refresh_token)
                
                # Get user from token payload
                user_id = refresh.payload.get('user_id')
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                    return Response({
                        'detail': 'User not found',
                        'code': 'user_not_found'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                
                # Generate new access token
                access_token = refresh.access_token
                
                response_data = {
                    'access': str(access_token),
                }
                
                # If rotation is enabled, generate new refresh token
                if api_settings.ROTATE_REFRESH_TOKENS:
                    # Create new refresh token
                    new_refresh = RefreshToken.for_user(user)
                    response_data['refresh'] = str(new_refresh)
                    
                    logger.info(f"JWT tokens refreshed with rotation for user: {user.email}")
                else:
                    # Return the same refresh token
                    response_data['refresh'] = str(refresh)
                    
                    logger.info(f"JWT access token refreshed for user: {user.email}")
                
                return Response(response_data, status=status.HTTP_200_OK)
                
            except TokenError as e:
                logger.warning(f"Token refresh failed - invalid token: {str(e)}")
                return Response({
                    'detail': 'Invalid or expired refresh token',
                    'code': 'token_invalid'
                }, status=status.HTTP_401_UNAUTHORIZED)
                
        except ImportError:
            logger.error("JWT package not available")
            return Response({
                'detail': 'JWT functionality not available'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {str(e)}")
            return Response({
                'detail': 'Token refresh failed due to server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BulkDeleteUsersView(APIView):
    """
    API endpoint to bulk delete users.
    
    Only admins and super admins can delete users.
    Users cannot delete themselves.
    Surveys created by deleted users are preserved.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAdminOrSuperAdmin]
    
    def post(self, request):
        """
        Delete multiple users in bulk.
        
        Args:
            request: HTTP request with user_ids in the body
            
        Returns:
            Summary of deletion results
        """
        try:
            from .serializers import BulkDeleteUsersSerializer
            
            serializer = BulkDeleteUsersSerializer(
                data=request.data, 
                context={'request': request}
            )
            
            if not serializer.is_valid():
                return Response({
                    'detail': 'Invalid data provided',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user_ids = serializer.validated_data['user_ids']
            
            # Track results
            successful_deletions = []
            failed_deletions = []
            
            with transaction.atomic():
                for user_id in user_ids:
                    try:
                        # Get user
                        user = User.objects.get(id=user_id)
                        
                        # Check if user exists and gather info before deletion
                        user_info = {
                            'id': user.id,
                            'email': user.email,
                            'username': user.username,
                            'role': user.role
                        }
                        
                        # Check if this is a protected super admin
                        if user.role == 'super_admin':
                            # Count remaining super admins
                            super_admin_count = User.objects.filter(
                                role='super_admin',
                                is_active=True
                            ).exclude(id=user.id).count()
                            
                            if super_admin_count < 1:
                                failed_deletions.append({
                                    'user_id': user_id,
                                    'email': user.email,
                                    'error': 'Cannot delete the last super admin account'
                                })
                                continue
                        
                        # Delete the user (surveys will be preserved due to SET_NULL)
                        user.delete()
                        
                        successful_deletions.append(user_info)
                        
                        # Log the deletion
                        log_security_event(
                            event_type='user_deletion',
                            user=request.user,
                            details={
                                'deleted_user_id': user_id,
                                'deleted_user_email': user_info['email'],
                                'deleted_user_role': user_info['role']
                            }
                        )
                        
                        logger.info(f"User deleted by admin {request.user.email}: {user_info['email']}")
                        
                    except User.DoesNotExist:
                        failed_deletions.append({
                            'user_id': user_id,
                            'email': 'Unknown',
                            'error': 'User does not exist'
                        })
                        
                    except Exception as e:
                        failed_deletions.append({
                            'user_id': user_id,
                            'email': 'Unknown',
                            'error': f'Unexpected error: {str(e)}'
                        })
            
            # Prepare response
            response_data = {
                'message': 'Bulk user deletion completed',
                'summary': {
                    'total_requested': len(user_ids),
                    'successful_deletions': len(successful_deletions),
                    'failed_deletions': len(failed_deletions)
                },
                'results': {
                    'successful': successful_deletions,
                    'failed': failed_deletions
                }
            }
            
            # Determine response status
            if len(successful_deletions) > 0 and len(failed_deletions) == 0:
                response_status = status.HTTP_200_OK
            elif len(successful_deletions) > 0 and len(failed_deletions) > 0:
                response_status = status.HTTP_207_MULTI_STATUS
            else:
                response_status = status.HTTP_400_BAD_REQUEST
                response_data['message'] = 'No users were deleted'
            
            return Response(response_data, status=response_status)
            
        except Exception as e:
            logger.error(f"Error in bulk user deletion: {str(e)}")
            return Response({
                'detail': 'An unexpected error occurred during user deletion'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResetUserPasswordView(APIView):
    """
    API endpoint to reset a user's password by admin.
    
    Only admins and super admins can reset user passwords.
    Only works for regular authentication users (not Azure AD).
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAdminOrSuperAdmin]
    
    def post(self, request):
        """
        Reset a user's password.
        
        Args:
            request: HTTP request with user_id and new_password
            
        Returns:
            Confirmation of password reset
        """
        try:
            from .serializers import ResetUserPasswordSerializer
            
            serializer = ResetUserPasswordSerializer(
                data=request.data,
                context={'request': request}
            )
            
            if not serializer.is_valid():
                return Response({
                    'detail': 'Invalid data provided',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user_id = serializer.validated_data['user_id']
            new_password = serializer.validated_data['new_password']
            
            # Get the user
            user = User.objects.get(id=user_id)
            
            # Set the new password (automatically hashes it)
            user.set_password(new_password)
            user.save()
            
            # Log the password reset
            log_security_event(
                event_type='password_reset_by_admin',
                user=request.user,
                details={
                    'target_user_id': user_id,
                    'target_user_email': user.email
                }
            )
            
            logger.info(f"Password reset by admin {request.user.email} for user: {user.email}")
            
            return Response({
                'message': 'Password reset successfully',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username
                }
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response({
                'detail': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            logger.error(f"Error resetting user password: {str(e)}")
            return Response({
                'detail': 'An unexpected error occurred during password reset'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BulkCreateAzureUsersView(APIView):
    """
    API endpoint for bulk creation of Azure AD users.
    
    This endpoint allows admins to create multiple Azure AD users at once.
    Users that already exist (by email) are automatically skipped.
    Object IDs are auto-generated from email addresses.
    
    Only super admins can create users with super_admin role.
    """
    
    authentication_classes = [UniversalAuthentication]
    permission_classes = [IsAdminOrSuperAdmin]
    
    def _generate_object_id(self, email):
        """
        Generate a unique Object ID from email address.
        
        Uses SHA256 hash of email to create a UUID-like identifier.
        This simulates an Azure AD Object ID for users created through this endpoint.
        
        Args:
            email: User's email address
            
        Returns:
            String in UUID format (e.g., "12345678-1234-5678-9abc-123456789abc")
        """
        import hashlib
        import uuid
        
        # Create SHA256 hash of email
        email_hash = hashlib.sha256(email.lower().encode()).hexdigest()
        
        # Convert first 32 hex characters to UUID format
        uuid_str = f"{email_hash[:8]}-{email_hash[8:12]}-{email_hash[12:16]}-{email_hash[16:20]}-{email_hash[20:32]}"
        
        return uuid_str
    
    def post(self, request):
        """
        Create multiple Azure AD users in bulk.
        
        Request body:
            {
                "users": [
                    {
                        "email": "user1@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "role": "user"
                    },
                    {
                        "email": "user2@example.com",
                        "first_name": "Jane",
                        "last_name": "Smith",
                        "role": "admin"
                    }
                ]
            }
        
        Returns:
            Summary of created and skipped users
        """
        try:
            from .serializers import BulkCreateAzureUsersSerializer
            
            serializer = BulkCreateAzureUsersSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    'detail': 'Invalid data provided',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            users_data = serializer.validated_data['users']
            
            # Track results
            created_users = []
            skipped_users = []
            failed_users = []
            
            with transaction.atomic():
                for user_data in users_data:
                    try:
                        email = user_data['email']
                        first_name = user_data.get('first_name', '')
                        last_name = user_data.get('last_name', '')
                        role = user_data.get('role', 'user')
                        
                        # Auto-generate Object ID from email
                        object_id = self._generate_object_id(email)
                        
                        # Check if user is trying to create super_admin
                        if role == 'super_admin' and request.user.role != 'super_admin':
                            failed_users.append({
                                'email': email,
                                'error': 'Only super admins can create super_admin users'
                            })
                            continue
                        
                        # Check if user already exists by email
                        if User.objects.email_exists(email):
                            existing_user = User.objects.get_by_email(email)
                            skipped_users.append({
                                'email': email,
                                'reason': 'User already exists with this email',
                                'existing_user': {
                                    'id': existing_user.id,
                                    'email': existing_user.email,
                                    'username': existing_user.username,
                                    'role': existing_user.role
                                }
                            })
                            continue
                        
                        # Create the new Azure AD user
                        user = User.objects.create_user(
                            username=object_id,       # Use auto-generated Object ID
                            email=email,              # User's email
                            first_name=first_name,    # Optional: for better UX
                            last_name=last_name,      # Optional: for better UX
                            role=role,                # User role
                            auth_type='azure',        # Mark as Azure AD user
                            is_active=True,           # Active by default
                        )
                        
                        created_users.append({
                            'id': user.id,
                            'object_id': object_id,
                            'email': email,
                            'full_name': user.full_name,
                            'role': role
                        })
                        
                        # Log the creation
                        logger.info(
                            f"Azure AD user created by {request.user.email}: "
                            f"{email} (Object ID: {object_id}, Role: {role})"
                        )
                        
                    except Exception as e:
                        logger.error(f"Error creating Azure AD user {user_data.get('email')}: {str(e)}")
                        failed_users.append({
                            'email': user_data.get('email', 'unknown'),
                            'error': str(e)
                        })
            
            # Prepare response
            response_data = {
                'message': 'Bulk Azure AD user creation completed',
                'summary': {
                    'total_requested': len(users_data),
                    'created': len(created_users),
                    'skipped': len(skipped_users),
                    'failed': len(failed_users)
                },
                'results': {
                    'created': created_users,
                    'skipped': skipped_users,
                    'failed': failed_users
                }
            }
            
            # Determine response status
            if len(created_users) > 0 and len(failed_users) == 0:
                response_status = status.HTTP_201_CREATED
                response_data['message'] = f"Successfully created {len(created_users)} Azure AD user(s)"
            elif len(created_users) > 0 and len(failed_users) > 0:
                response_status = status.HTTP_207_MULTI_STATUS
                response_data['message'] = f"Partially successful: {len(created_users)} created, {len(failed_users)} failed"
            elif len(created_users) == 0 and len(skipped_users) > 0:
                response_status = status.HTTP_200_OK
                response_data['message'] = "All users already exist - no new users created"
            else:
                response_status = status.HTTP_400_BAD_REQUEST
                response_data['message'] = "No users were created"
            
            # Log security event
            log_security_event(
                event_type='bulk_azure_user_creation',
                user=request.user,
                request=request,
                details={
                    'total_requested': len(users_data),
                    'created': len(created_users),
                    'skipped': len(skipped_users),
                    'failed': len(failed_users)
                }
            )
            
            return Response(response_data, status=response_status)
            
        except Exception as e:
            logger.error(f"Error in bulk Azure AD user creation: {str(e)}")
            return Response({
                'detail': 'An unexpected error occurred during bulk user creation'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
