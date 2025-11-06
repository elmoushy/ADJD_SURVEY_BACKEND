"""
Custom permissions for surveys with role-based access control.

This module implements the permission classes following the same patterns
as the authentication system with support for three visibility levels.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsCreatorOrVisible(BasePermission):
    """
    Custom permission to handle survey visibility levels:
    
    For SAFE_METHODS (GET, HEAD, OPTIONS):
    - PUBLIC: Anyone can access
    - AUTH: Any authenticated user can access  
    - PRIVATE: Only creator or users in shared_with can access
    
    For unsafe methods (POST, PUT, PATCH, DELETE):
    - Only the creator can modify surveys
    """
    
    def has_object_permission(self, request, view, obj):
        # For safe methods, check visibility rules
        if request.method in SAFE_METHODS:
            if obj.visibility == "PUBLIC":
                return True
            
            if obj.visibility == "AUTH" and request.user.is_authenticated:
                return True
            
            if obj.visibility == "PRIVATE":
                if request.user == obj.creator:
                    return True
                if request.user.is_authenticated and request.user in obj.shared_with.all():
                    return True
            
            return False
        
        # For unsafe methods, only creator can modify
        return request.user == obj.creator


class IsCreatorOrReadOnly(BasePermission):
    """
    Permission for survey modification:
    - Super admin: Can edit/delete any survey
    - Admin/Manager: Can only edit/delete their own surveys
    - Regular users: Can only edit/delete their own surveys
    - Everyone can read based on visibility rules
    """
    
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            # Apply visibility rules via IsCreatorOrVisible
            return IsCreatorOrVisible().has_object_permission(request, view, obj)
        
        # Write permissions based on role
        if request.user.role == 'super_admin':
            return True
        elif request.user.role in ['admin', 'manager']:
            return request.user == obj.creator
        else:
            return request.user == obj.creator


class CanSubmitResponse(BasePermission):
    """
    Permission for submitting survey responses based on visibility.
    """
    
    def has_permission(self, request, view):
        return True  # Basic permission check in view
    
    def has_object_permission(self, request, view, obj):
        # obj here is the Survey
        if obj.visibility == "PUBLIC":
            return True
        
        if obj.visibility == "AUTH":
            return request.user.is_authenticated
        
        if obj.visibility == "PRIVATE":
            if not request.user.is_authenticated:
                return False
            
            return (
                request.user == obj.creator or
                request.user in obj.shared_with.all()
            )
        
        return False


class IsCreatorOrStaff(BasePermission):
    """
    Permission for survey responses and analytics:
    - Super admin: Can access any survey's responses
    - Admin/Manager: Can only access their own survey's responses
    - Regular users: Can only access their own survey's responses
    """
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'creator'):
            # obj is Survey
            if request.user.role == 'super_admin':
                return True
            elif request.user.role in ['admin', 'manager']:
                return request.user == obj.creator
            else:
                return request.user == obj.creator
        elif hasattr(obj, 'survey'):
            # obj is Response
            if request.user.role == 'super_admin':
                return True
            elif request.user.role in ['admin', 'manager']:
                return request.user == obj.survey.creator
            else:
                return request.user == obj.survey.creator
        
        return False
