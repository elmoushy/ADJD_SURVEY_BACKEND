"""
Django Admin Configuration for Email Communication System
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CostCenter,
    CostCenterEmail,
    EmailTemplate,
    EmailDraft,
    EmailLog,
    EmailRecipientView
)


class CostCenterEmailInline(admin.TabularInline):
    """Inline admin for cost center emails"""
    model = CostCenterEmail
    extra = 1
    fields = ['email', 'email_type', 'display_name', 'is_active']
    readonly_fields = []


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ['cost_center_code', 'cost_center_name', 'is_active', 'email_count', 'recipient_count', 'cc_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['cost_center_code', 'cost_center_name', 'cost_center_name_ar']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    inlines = [CostCenterEmailInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('cost_center_code', 'cost_center_name', 'cost_center_name_ar', 'is_active')
        }),
        ('Description', {
            'fields': ('description', 'description_ar'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def email_count(self, obj):
        return obj.emails.count()
    email_count.short_description = 'Total Emails'
    
    def recipient_count(self, obj):
        return obj.emails.filter(email_type='recipient').count()
    recipient_count.short_description = 'Recipients'
    
    def cc_count(self, obj):
        return obj.emails.filter(email_type='cc').count()
    cc_count.short_description = 'CC Emails'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CostCenterEmail)
class CostCenterEmailAdmin(admin.ModelAdmin):
    list_display = ['email', 'cost_center', 'email_type', 'is_active', 'created_at']
    list_filter = ['email_type', 'is_active', 'created_at']
    search_fields = ['email', 'display_name', 'cost_center__cost_center_code', 'cost_center__cost_center_name']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Email Information', {
            'fields': ('cost_center', 'email', 'email_type', 'display_name', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'is_active', 'created_by', 'created_at']
    list_filter = ['is_active', 'category', 'created_at']
    search_fields = ['name', 'name_ar', 'subject']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'name_ar', 'category', 'is_active')
        }),
        ('English Content', {
            'fields': ('subject', 'body_html', 'body_text')
        }),
        ('Arabic Content', {
            'fields': ('subject_ar', 'body_html_ar'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(EmailDraft)
class EmailDraftAdmin(admin.ModelAdmin):
    list_display = ['subject_preview', 'user', 'send_type', 'draft_name', 'is_deleted', 'updated_at']
    list_filter = ['send_type', 'is_deleted', 'created_at']
    search_fields = ['subject', 'draft_name', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Draft Information', {
            'fields': ('user', 'draft_name', 'send_type', 'template')
        }),
        ('Email Content', {
            'fields': ('subject', 'body_html')
        }),
        ('Configuration', {
            'fields': ('cost_center_ids', 'is_deleted')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['subject_preview', 'user', 'email_type', 'send_type', 'email_status', 'sent_at']
    list_filter = ['email_type', 'send_type', 'email_status', 'sent_at']
    search_fields = ['subject', 'user__email', 'recipient_emails']
    readonly_fields = ['sent_at']
    date_hierarchy = 'sent_at'
    
    fieldsets = (
        ('Email Information', {
            'fields': ('user', 'cost_center', 'template', 'draft')
        }),
        ('Type & Status', {
            'fields': ('email_type', 'send_type', 'email_status', 'email_error')
        }),
        ('Content', {
            'fields': ('subject', 'body_html')
        }),
        ('Recipients', {
            'fields': ('recipient_emails', 'cc_emails')
        }),
        ('Metadata', {
            'fields': ('metadata', 'sent_at'),
            'classes': ('collapse',)
        }),
    )
    
    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'
    
    def has_add_permission(self, request):
        # Email logs are created programmatically
        return False


@admin.register(EmailRecipientView)
class EmailRecipientViewAdmin(admin.ModelAdmin):
    list_display = ['email_subject', 'recipient_user', 'is_to', 'is_read', 'is_starred', 'is_archived', 'read_at']
    list_filter = ['is_read', 'is_starred', 'is_archived', 'is_to', 'read_at']
    search_fields = ['recipient_user__email', 'email_log__subject']
    readonly_fields = ['read_at']
    date_hierarchy = 'email_log__sent_at'
    
    fieldsets = (
        ('Email & Recipient', {
            'fields': ('email_log', 'recipient_user', 'is_to')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'is_starred', 'is_archived')
        }),
    )
    
    def email_subject(self, obj):
        return obj.email_log.subject[:50]
    email_subject.short_description = 'Email Subject'
    
    def has_add_permission(self, request):
        # Recipient views are created programmatically
        return False
