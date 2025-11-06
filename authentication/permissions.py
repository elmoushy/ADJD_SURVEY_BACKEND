"""
Custom permission classes for the role-based access control system.
"""

from rest_framework.permissions import BasePermission
from .models import UserGroup


class IsSuperAdmin(BasePermission):
    """
    Permission class that only allows access to super administrators.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'super_admin'
        )


class IsAdminOrSuperAdmin(BasePermission):
    """
    Permission class that allows access to admins and super administrators.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['admin', 'super_admin']
        )


class IsGroupAdmin(BasePermission):
    """
    Permission class that checks if user is an admin of a specific group.
    Requires the view to have a 'get_group' method or 'group_id' in kwargs.
    """
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Super admins always have permission
        if request.user.role == 'super_admin':
            return True
        
        # Check if user is admin
        if request.user.role != 'admin':
            return False
        
        # Get group from view
        group_id = view.kwargs.get('group_id')
        if not group_id:
            return False
        
        # Check if user is admin of this specific group
        return UserGroup.objects.filter(
            user=request.user,
            group_id=group_id,
            is_group_admin=True
        ).exists()


class CanViewGroup(BasePermission):
    """
    Permission class that checks if user can view a specific group.
    Super admins can view all groups, group members can view their groups.
    """
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Super admins can view all groups
        if request.user.role == 'super_admin':
            return True
        
        # Regular users have no group access
        if request.user.role == 'user':
            return False
        
        # Get group from view
        group_id = view.kwargs.get('group_id')
        if not group_id:
            return False
        
        # Check if user is a member of this group
        return UserGroup.objects.filter(
            user=request.user,
            group_id=group_id
        ).exists()


class CanManageGroupUsers(BasePermission):
    """
    Permission class for managing users within a group.
    Super admins and group admins can manage users.
    """
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Super admins can manage users in any group
        if request.user.role == 'super_admin':
            return True
        
        # Only admins can manage users
        if request.user.role != 'admin':
            return False
        
        # Get group from view
        group_id = view.kwargs.get('group_id')
        if not group_id:
            return False
        
        # Check if user is admin of this specific group
        return UserGroup.objects.filter(
            user=request.user,
            group_id=group_id,
            is_group_admin=True
        ).exists()


class IsOwnerOrSuperAdmin(BasePermission):
    """
    Permission class that allows access to object owners or super admins.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Super admins can access any object
        if request.user.role == 'super_admin':
            return True
        
        # Check if user owns the object
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user
        
        return False


class CanAccessUserData(BasePermission):
    """
    Permission class for accessing user data based on role hierarchy.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        target_user = obj
        
        # Super admins can access any user data
        if user.role == 'super_admin':
            return True
        
        # Users can access their own data
        if user == target_user:
            return True
        
        # Admins can access users in their groups
        if user.role == 'admin':
            # Get all groups where current user is admin
            admin_groups = UserGroup.objects.filter(
                user=user,
                is_group_admin=True
            ).values_list('group_id', flat=True)
            
            # Check if target user is in any of these groups
            return UserGroup.objects.filter(
                user=target_user,
                group_id__in=admin_groups
            ).exists()
        
        return False
