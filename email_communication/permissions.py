"""
Custom permissions for Email Communication System
"""
from rest_framework import permissions


class CanSendEmail(permissions.BasePermission):
    """
    Permission to send emails.
    By default, all authenticated users can send emails.
    Can be restricted by adding 'can_send_email' permission to user/group.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Super admins can always send
        if request.user.is_superuser or request.user.role == 'super_admin':
            return True
        
        # Check if user has specific permission (optional)
        # For now, all authenticated users can send
        return True


class CanManageCostCenters(permissions.BasePermission):
    """
    Permission to create/edit/delete cost centers.
    Only admins and super admins.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Read-only for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write operations for admins only
        return request.user.is_superuser or request.user.role in ['admin', 'super_admin']


class CanCreateTemplates(permissions.BasePermission):
    """
    Permission to create/edit email templates.
    Admins and users with specific permission.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Read-only for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Create/edit for admins
        return request.user.is_superuser or request.user.role in ['admin', 'super_admin']


class IsDraftOwner(permissions.BasePermission):
    """
    Permission to manage draft - only owner can edit/delete/send
    """
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class CanViewEmailLog(permissions.BasePermission):
    """
    Permission to view email logs.
    Users see only their own, admins see all.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Admins see all
        if request.user.is_superuser or request.user.role in ['admin', 'super_admin']:
            return True
        
        # Users see only their own
        return obj.user == request.user


class IsRecipient(permissions.BasePermission):
    """
    Permission to view inbox email - only recipient can view
    """
    def has_object_permission(self, request, view, obj):
        return obj.recipient_user == request.user
