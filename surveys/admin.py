"""
Django admin configuration for surveys.

This module provides admin interface for managing surveys, questions,
responses, and answers with proper encryption handling.
"""

from django.contrib import admin
from .models import Survey, Question, Response, Answer, PublicAccessToken


class OrphanedSurveyFilter(admin.SimpleListFilter):
    """Custom filter for orphaned surveys (creator is null)"""
    title = 'Survey Status'
    parameter_name = 'survey_status'

    def lookups(self, request, model_admin):
        return (
            ('orphaned', 'Orphaned (Creator Deleted)'),
            ('active', 'Has Creator'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'orphaned':
            return queryset.filter(creator__isnull=True)
        elif self.value() == 'active':
            return queryset.filter(creator__isnull=False)


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    """Admin interface for Survey model"""
    
    list_display = [
        'title', 'creator_display', 'visibility', 'is_active', 
        'is_locked', 'response_count', 'created_at'
    ]
    list_filter = ['visibility', 'is_active', 'is_locked', 'created_at', OrphanedSurveyFilter]
    search_fields = ['title', 'description', 'creator__email']
    readonly_fields = ['id', 'title_hash', 'created_at', 'updated_at']
    filter_horizontal = ['shared_with']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'title', 'description', 'creator')
        }),
        ('Visibility & Sharing', {
            'fields': ('visibility', 'shared_with')
        }),
        ('Settings', {
            'fields': ('is_active', 'is_locked')
        }),
        ('Metadata', {
            'fields': ('title_hash', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def creator_display(self, obj):
        """Display creator or 'Deleted User' for orphaned surveys"""
        if obj.creator:
            return obj.creator.email
        return 'Deleted User (Orphaned Survey)'
    creator_display.short_description = 'Creator'
    creator_display.admin_order_field = 'creator__email'
    
    def response_count(self, obj):
        """Get response count for survey"""
        return obj.responses.count()
    response_count.short_description = 'Responses'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Admin interface for Question model"""
    
    list_display = [
        'text_preview', 'survey_title', 'question_type', 
        'is_required', 'order', 'created_at'
    ]
    list_filter = ['question_type', 'is_required', 'created_at']
    search_fields = ['text', 'survey__title']
    readonly_fields = ['id', 'text_hash', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Question Details', {
            'fields': ('id', 'survey', 'text', 'question_type', 'options')
        }),
        ('Settings', {
            'fields': ('is_required', 'order')
        }),
        ('Metadata', {
            'fields': ('text_hash', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def text_preview(self, obj):
        """Show preview of question text"""
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Question Text'
    
    def survey_title(self, obj):
        """Show survey title"""
        return obj.survey.title
    survey_title.short_description = 'Survey'


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    """Admin interface for Response model"""
    
    list_display = [
        'id', 'survey_title', 'respondent_info', 
        'is_complete', 'submitted_at', 'answer_count'
    ]
    list_filter = ['is_complete', 'submitted_at']
    search_fields = ['survey__title', 'respondent__email']
    readonly_fields = ['id', 'submitted_at']
    
    fieldsets = (
        ('Response Details', {
            'fields': ('id', 'survey', 'respondent', 'is_complete')
        }),
        ('Metadata', {
            'fields': ('ip_address', 'submitted_at')
        }),
    )
    
    def survey_title(self, obj):
        """Show survey title"""
        return obj.survey.title
    survey_title.short_description = 'Survey'
    
    def respondent_info(self, obj):
        """Show respondent information"""
        return obj.respondent.email if obj.respondent else "Anonymous"
    respondent_info.short_description = 'Respondent'
    
    def answer_count(self, obj):
        """Get answer count for response"""
        return obj.answers.count()
    answer_count.short_description = 'Answers'


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    """Admin interface for Answer model"""
    
    list_display = [
        'id', 'response_id', 'question_preview', 
        'answer_preview', 'created_at'
    ]
    list_filter = ['created_at']
    search_fields = ['question__text', 'answer_text']
    readonly_fields = ['id', 'created_at']
    
    fieldsets = (
        ('Answer Details', {
            'fields': ('id', 'response', 'question', 'answer_text')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def question_preview(self, obj):
        """Show preview of question text"""
        return obj.question.text[:30] + "..." if len(obj.question.text) > 30 else obj.question.text
    question_preview.short_description = 'Question'
    
    def answer_preview(self, obj):
        """Show preview of answer text"""
        return obj.answer_text[:50] + "..." if len(obj.answer_text) > 50 else obj.answer_text
    answer_preview.short_description = 'Answer'


@admin.register(PublicAccessToken)
class PublicAccessTokenAdmin(admin.ModelAdmin):
    """Admin interface for PublicAccessToken model"""
    
    list_display = [
        'token', 'survey_title', 'created_by_display', 
        'is_active', 'expires_at', 'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'expires_at']
    search_fields = ['survey__title', 'token', 'created_by__email']
    readonly_fields = ['id', 'token', 'created_at']
    
    fieldsets = (
        ('Token Details', {
            'fields': ('id', 'token', 'survey', 'created_by', 'is_active')
        }),
        ('Access Control', {
            'fields': ('password', 'restricted_email', 'restricted_phone')
        }),
        ('Timing', {
            'fields': ('expires_at', 'created_at')
        }),
    )
    
    def survey_title(self, obj):
        """Show survey title"""
        return obj.survey.title
    survey_title.short_description = 'Survey'
    survey_title.admin_order_field = 'survey__title'
    
    def created_by_display(self, obj):
        """Display created_by or 'Deleted User' for orphaned tokens"""
        if obj.created_by:
            return obj.created_by.email
        return 'Deleted User'
    created_by_display.short_description = 'Created By'
    created_by_display.admin_order_field = 'created_by__email'
