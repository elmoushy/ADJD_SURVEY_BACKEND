"""
Django admin configuration for authentication models.

This module configures the Django admin interface for our custom
User model without Django's default group and permission system.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Group, UserGroup


User = get_user_model()


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    Custom admin configuration for User model.
    
    This admin interface is simplified to work without Django's
    group and permission system.
    """
    
    # Fields to display in the user list
    list_display = [
        'email',
        'username',
        'first_name',
        'last_name', 
        'role',
        'is_active',
        'date_joined',
        'last_login'
    ]
    
    # Fields that can be used to filter the user list
    list_filter = [
        'role',
        'is_active',
        'date_joined',
        'last_login'
    ]
    
    # Fields that can be searched
    search_fields = [
        'email',
        'username',
        'first_name',
        'last_name'
    ]
    
    # Default ordering
    ordering = ['-date_joined']
    
    # Fields displayed when editing a user
    fieldsets = (
        ('User Information', {
            'fields': ('username', 'email', 'first_name', 'last_name')
        }),
        ('Permissions', {
            'fields': ('role', 'is_active')
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    # Fields displayed when adding a new user
    add_fieldsets = (
        ('Create User', {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'role', 'is_active')
        }),
    )
    
    # Read-only fields
    readonly_fields = ['date_joined', 'last_login']
    
    def has_delete_permission(self, request, obj=None):
        """
        Only admins can delete users.
        """
        return hasattr(request.user, 'role') and request.user.role == 'admin'
    
    def has_change_permission(self, request, obj=None):
        """
        Super admins can change any user, admins have limited access.
        """
        if hasattr(request.user, 'role'):
            if request.user.role == 'super_admin':
                return True
            if request.user.role == 'admin' and obj and obj.role in ['user', 'admin']:
                return True
        return False
    
    def get_queryset(self, request):
        """
        Filter queryset based on user role.
        """
        qs = super().get_queryset(request)
        if hasattr(request.user, 'role'):
            if request.user.role == 'super_admin':
                return qs
            elif request.user.role == 'admin':
                # Admins can see users in their groups
                user_groups = request.user.user_groups.all()
                group_ids = [ug.group_id for ug in user_groups]
                return qs.filter(groups__id__in=group_ids).distinct()
            else:
                return qs.filter(id=request.user.id)  # Users can only see themselves
        return qs.none()


class UserGroupInline(admin.TabularInline):
    """
    Inline admin for UserGroup model to display users within groups.
    """
    model = UserGroup
    extra = 1
    fields = ['user', 'is_group_admin', 'joined_at']
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """
    Admin configuration for Group model.
    """
    
    list_display = [
        'name',
        'description',
        'user_count',
        'admin_count',
        'created_at',
        'updated_at'
    ]
    
    list_filter = [
        'created_at',
        'updated_at'
    ]
    
    search_fields = [
        'name',
        'description'
    ]
    
    ordering = ['name']
    
    fieldsets = (
        ('Group Information', {
            'fields': ('name', 'description')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    inlines = [UserGroupInline]
    
    def has_module_permission(self, request):
        """Only super_admin and admin users can access groups."""
        return hasattr(request.user, 'role') and request.user.role in ['super_admin', 'admin']
    
    def has_add_permission(self, request):
        """Only super_admin can create groups."""
        return hasattr(request.user, 'role') and request.user.role == 'super_admin'
    
    def has_delete_permission(self, request, obj=None):
        """Only super_admin can delete groups."""
        return hasattr(request.user, 'role') and request.user.role == 'super_admin'
    
    def has_change_permission(self, request, obj=None):
        """Super_admin can change any group, admin can change their groups."""
        if hasattr(request.user, 'role'):
            if request.user.role == 'super_admin':
                return True
            elif request.user.role == 'admin' and obj:
                # Check if user is admin of this group
                return obj.users.filter(id=request.user.id, user_groups__is_group_admin=True).exists()
        return False
    
    def get_queryset(self, request):
        """Filter groups based on user role."""
        qs = super().get_queryset(request)
        if hasattr(request.user, 'role'):
            if request.user.role == 'super_admin':
                return qs
            elif request.user.role == 'admin':
                # Admins can only see their groups
                return qs.filter(users=request.user)
        return qs.none()


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    """
    Admin configuration for UserGroup model.
    """
    
    list_display = [
        'user',
        'group',
        'is_group_admin',
        'joined_at'
    ]
    
    list_filter = [
        'is_group_admin',
        'joined_at',
        'group'
    ]
    
    search_fields = [
        'user__email',
        'user__first_name',
        'user__last_name',
        'group__name'
    ]
    
    ordering = ['group__name', 'user__email']
    
    fieldsets = (
        ('Membership Information', {
            'fields': ('user', 'group', 'is_group_admin')
        }),
        ('Metadata', {
            'fields': ('joined_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user', 'group']
    
    def has_module_permission(self, request):
        """Only super_admin and admin users can access user groups."""
        return hasattr(request.user, 'role') and request.user.role in ['super_admin', 'admin']
    
    def has_add_permission(self, request):
        """Both super_admin and admin can add user groups."""
        return hasattr(request.user, 'role') and request.user.role in ['super_admin', 'admin']
    
    def has_delete_permission(self, request, obj=None):
        """Check deletion permissions and group admin constraints."""
        if not hasattr(request.user, 'role'):
            return False
        
        if request.user.role == 'super_admin':
            return True
        elif request.user.role == 'admin' and obj:
            # Admin can delete if they're admin of the group and it's not the last admin
            is_group_admin = obj.group.users.filter(
                id=request.user.id, 
                user_groups__is_group_admin=True
            ).exists()
            
            if is_group_admin:
                # Check if removing this membership would leave the group without admins
                if obj.is_group_admin and obj.group.admin_count <= 1:
                    return False
                return True
        
        return False
    
    def has_change_permission(self, request, obj=None):
        """Check change permissions."""
        if hasattr(request.user, 'role'):
            if request.user.role == 'super_admin':
                return True
            elif request.user.role == 'admin' and obj:
                # Admin can change if they're admin of the group
                return obj.group.users.filter(
                    id=request.user.id,
                    user_groups__is_group_admin=True
                ).exists()
        return False
    
    def get_queryset(self, request):
        """Filter user groups based on user role."""
        qs = super().get_queryset(request)
        if hasattr(request.user, 'role'):
            if request.user.role == 'super_admin':
                return qs
            elif request.user.role == 'admin':
                # Admins can only see memberships of their groups
                user_groups = request.user.user_groups.all()
                group_ids = [ug.group_id for ug in user_groups]
                return qs.filter(group_id__in=group_ids)
        return qs.none()
