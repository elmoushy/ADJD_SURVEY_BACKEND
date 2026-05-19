"""
URL patterns for surveys API endpoints.

This module defines the URL routing following the same patterns
as the authentication system.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views_followup import FollowUpViewSet
from .views_access_picker import AccessPickerSearchView
from .views_attachments import (
    ResponseAttachmentUploadView,
    ResponseAttachmentListView,
    ResponseAttachmentDownloadView,
    ResponseAttachmentDeleteView,
    FollowUpAttachmentUploadView,
    FollowUpAttachmentDownloadView,
    FollowUpAttachmentDeleteView,
)

app_name = 'surveys'

# Router for ViewSets
router = DefaultRouter()
router.register('surveys', views.SurveyViewSet, basename='survey')
router.register('follow-ups', FollowUpViewSet, basename='follow-ups')

urlpatterns = [
    # ViewSet routes
    path('', include(router.urls)),
    
    # Draft and Submit endpoints
    path('draft/', 
         views.SurveyDraftView.as_view(), 
         name='survey-draft'),
    
    path('submit/', 
         views.SurveySubmitView.as_view(), 
         name='survey-submit'),
    
    # My shared surveys endpoint
    path('my-shared/', 
         views.MySharedSurveysView.as_view(), 
         name='my-shared-surveys'),
    
    # New survey response submission endpoint
    path('responses/', 
         views.SurveyResponseSubmissionView.as_view(), 
         name='survey-response-submission'),
    
    # Authenticated survey response submission (no email required)
    path('auth-responses/', 
         views.AuthenticatedSurveyResponseView.as_view(), 
         name='authenticated-survey-response'),
    
    # Survey submission endpoint (legacy)
    path('surveys/<uuid:survey_id>/submit/', 
         views.SurveySubmissionView.as_view(), 
         name='survey-submit'),
    
    # Response management
    path('surveys/<uuid:survey_id>/responses/', 
         views.SurveyResponsesView.as_view(), 
         name='survey-responses'),
    
    # Admin APIs - Survey Response Management
    path('admin/responses/', 
         views.AdminResponsesView.as_view(), 
         name='admin-all-responses'),
    
    path('admin/surveys/<uuid:survey_id>/responses/', 
         views.AdminSurveyResponsesView.as_view(), 
         name='admin-survey-responses'),
    
    # Analytics Dashboard APIs
    path('admin/surveys/<uuid:survey_id>/dashboard/',
         views.SurveyAnalyticsDashboardView.as_view(),
         name='survey-analytics-dashboard'),
    
    # Alternative URL pattern for frontend compatibility
    path('admin/surveys/<uuid:survey_id>/analytics/dashboard/',
         views.SurveyAnalyticsDashboardView.as_view(),
         name='survey-analytics-dashboard-alt'),
    
    # Questions analytics overview endpoint
    path('admin/surveys/<uuid:survey_id>/questions/analytics/dashboard/',
         views.SurveyQuestionsAnalyticsView.as_view(),
         name='survey-questions-analytics'),
    
    path('admin/surveys/<uuid:survey_id>/questions/<uuid:question_id>/dashboard/',
         views.QuestionAnalyticsDashboardView.as_view(),
         name='question-analytics-dashboard'),
    
    # Alternative URL pattern for question analytics frontend compatibility
    path('admin/surveys/<uuid:survey_id>/questions/<uuid:question_id>/analytics/dashboard/',
         views.QuestionAnalyticsDashboardView.as_view(),
         name='question-analytics-dashboard-alt'),
    
    # Token-Based Access APIs
    path('token/surveys/', 
         views.TokenSurveysView.as_view(), 
         name='token-surveys'),
    
    path('token/surveys/<uuid:survey_id>/', 
         views.TokenSurveyDetailView.as_view(), 
         name='token-survey-detail'),
    
    # Password-Protected Survey Access APIs
    path('password-access/<str:token>/', 
         views.PasswordAccessValidationView.as_view(), 
         name='password-access-validation'),
    
    path('password-surveys/<uuid:survey_id>/', 
         views.PasswordProtectedSurveyView.as_view(), 
         name='password-survey-detail'),
    
    path('password-responses/', 
         views.PasswordProtectedSurveyResponseView.as_view(), 
         name='password-survey-response'),
    
    # Bulk operations
    path('bulk-operations/', views.bulk_operations, name='bulk-operations'),
    
    # User search for sharing
    path('users/search/', views.UserSearchView.as_view(), name='user-search'),
    
    # Get admin groups for sharing
    path('my-admin-groups/', views.MyAdminGroupsView.as_view(), name='my-admin-groups'),
    
    # Template Management APIs
    path('templates/gallery/', 
         views.TemplateGalleryView.as_view(), 
         name='template-gallery'),
    
    path('templates/predefined/', 
         views.PredefinedTemplatesView.as_view(), 
         name='predefined-templates'),
    
    path('templates/predefined/create/', 
         views.CreatePredefinedTemplateView.as_view(), 
         name='create-predefined-template'),
    
    path('templates/predefined/<uuid:template_id>/', 
         views.DeletePredefinedTemplateView.as_view(), 
         name='delete-predefined-template'),
    
    path('templates/user/', 
         views.UserTemplatesView.as_view(), 
         name='user-templates'),
    
    path('recent/', 
         views.RecentSurveysView.as_view(), 
         name='recent-surveys'),
    
    path('templates/<uuid:template_id>/', 
         views.TemplateDetailView.as_view(), 
         name='template-detail'),
    
    path('templates/create/', 
         views.CreateTemplateView.as_view(), 
         name='create-template'),
    
    path('from-template/', 
         views.CreateSurveyFromTemplateView.as_view(), 
         name='create-survey-from-template'),
    
    path('surveys/<uuid:survey_id>/clone/', 
         views.CloneSurveyView.as_view(), 
         name='clone-survey'),
    
    path('templates/<uuid:template_id>/update/', 
         views.UpdateTemplateView.as_view(), 
         name='update-template'),
    
    path('templates/<uuid:template_id>/delete/', 
         views.DeleteTemplateView.as_view(), 
         name='delete-template'),
    
    # Health check
    path('health/', views.health_check, name='health-check'),

    # Access picker search (users + groups combined, admin only)
    path('access-picker/search/', AccessPickerSearchView.as_view(), name='access-picker-search'),

    # ─── Response Attachments ─────────────────────────────────────────────────
    path('responses/<uuid:response_id>/attachments/upload/',
         ResponseAttachmentUploadView.as_view(), name='response-attachment-upload'),

    path('responses/<uuid:response_id>/attachments/',
         ResponseAttachmentListView.as_view(), name='response-attachment-list'),

    path('response-attachments/<uuid:pk>/download/',
         ResponseAttachmentDownloadView.as_view(), name='response-attachment-download'),

    path('response-attachments/<uuid:pk>/',
         ResponseAttachmentDeleteView.as_view(), name='response-attachment-delete'),

    # ─── Follow-Up Message Attachments ────────────────────────────────────────
    path('follow-ups/<uuid:thread_id>/messages/<uuid:message_id>/attachments/upload/',
         FollowUpAttachmentUploadView.as_view(), name='followup-attachment-upload'),

    path('follow-up-attachments/<uuid:pk>/download/',
         FollowUpAttachmentDownloadView.as_view(), name='followup-attachment-download'),

    path('follow-up-attachments/<uuid:pk>/',
         FollowUpAttachmentDeleteView.as_view(), name='followup-attachment-delete'),
]
