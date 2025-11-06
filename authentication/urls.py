"""
URL patterns for authentication API endpoints.

This module defines the URL routing for all authentication-related
API endpoints including user profile, authentication health checks, 
regular email/password authentication, and JWT token management.
"""

from django.urls import path
from . import views

# Import JWT views with error handling
try:
    # We're not using the default TokenRefreshView anymore, but keep the import 
    # for compatibility checks
    from rest_framework_simplejwt.views import TokenRefreshView
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

# Import our custom token refresh view
from .views import CustomTokenRefreshView


app_name = 'authentication'

urlpatterns = [
    # Authentication endpoints
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('azure-login/', views.AzureADLoginView.as_view(), name='azure-login'),
    path('add-user/', views.AddUserView.as_view(), name='add-user'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    
    # Current user endpoints
    path('me/', views.CurrentUserView.as_view(), name='current-user'),
    path('user-info/', views.user_info, name='user-info'),
    
    # User management
    path('stats/', views.UserStatsView.as_view(), name='user-stats'),
    path('logout/', views.logout, name='logout'),
    path('users/', views.AllUsersView.as_view(), name='all-users'),
    path('users/names-emails/', views.AllUsersNamesEmailsView.as_view(), name='all-users-names-emails'),
    path('users/search/', views.UserSearchView.as_view(), name='user-search'),
    path('users/bulk-delete/', views.BulkDeleteUsersView.as_view(), name='bulk-delete-users'),
    path('users/reset-password/', views.ResetUserPasswordView.as_view(), name='reset-user-password'),
    path('users/<int:user_id>/role/', views.UserRoleUpdateView.as_view(), name='user-role-update'),
    path('users/<int:user_id>/groups/', views.UserGroupsView.as_view(), name='user-groups'),
    
    # Group management
    path('groups/', views.GroupListView.as_view(), name='groups'),
    path('groups/dropdown/', views.GroupDropdownView.as_view(), name='groups-dropdown'),
    path('groups/bulk-add-users/', views.BulkAddUsersView.as_view(), name='bulk-add-users'),
    path('groups/<int:group_id>/', views.GroupDetailView.as_view(), name='group-detail'),
    path('groups/<int:group_id>/users/', views.GroupUsersView.as_view(), name='group-users'),
    path('groups/<int:group_id>/users/<int:user_id>/', views.GroupUserDetailView.as_view(), name='group-user-detail'),
    
    # Reference data endpoints
    path('roles/', views.RolesListView.as_view(), name='roles-list'),
    
    # Dashboard
    path('stats/dashboard/', views.DashboardStatsView.as_view(), name='dashboard-stats'),
    
    # Health check
    path('health/', views.health_check, name='health-check'),
]

# Add JWT token refresh endpoint if available
if JWT_AVAILABLE:
    urlpatterns += [
        path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    ]
