"""
Email Communication System Models
Follows project's Oracle compatibility patterns with hash-based indexing
"""
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import EmailValidator
import hashlib
import json

from .managers import (
    CostCenterManager,
    EmailTemplateManager,
    EmailDraftManager,
    EmailLogManager,
    EmailRecipientViewManager
)


class CostCenter(models.Model):
    """
    Cost Center model - represents organizational units with email recipients.
    Emails are stored in separate CostCenterEmail table for flexibility.
    """
    cost_center_code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_("Cost Center Code"),
        help_text=_("Unique identifier (e.g., CC-001)")
    )
    cost_center_code_hash = models.CharField(
        max_length=64,
        db_index=True,
        editable=False,
        help_text=_("SHA256 hash for database-portable queries")
    )
    cost_center_name = models.CharField(
        max_length=255,
        verbose_name=_("Cost Center Name")
    )
    cost_center_name_ar = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Cost Center Name (Arabic)")
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Description")
    )
    description_ar = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Description (Arabic)")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Is Active")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_cost_centers',
        verbose_name=_("Created By")
    )

    objects = CostCenterManager()

    class Meta:
        db_table = 'email_costcenter'
        ordering = ['cost_center_code']
        verbose_name = _("Cost Center")
        verbose_name_plural = _("Cost Centers")
        indexes = [
            models.Index(fields=['cost_center_code_hash'], name='idx_cc_code_hash'),
            models.Index(fields=['is_active'], name='idx_cc_active'),
        ]

    def save(self, *args, **kwargs):
        """Generate hash for Oracle-compatible queries"""
        if self.cost_center_code:
            self.cost_center_code_hash = hashlib.sha256(
                self.cost_center_code.encode()
            ).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cost_center_code} - {self.cost_center_name}"

    def get_recipient_emails(self):
        """Get list of recipient emails (TO field)"""
        return list(
            self.emails.filter(email_type='recipient')
            .values_list('email', flat=True)
        )

    def get_cc_emails(self):
        """Get list of CC emails"""
        return list(
            self.emails.filter(email_type='cc')
            .values_list('email', flat=True)
        )

    def get_all_emails(self):
        """Get all emails grouped by type"""
        return {
            'recipients': self.get_recipient_emails(),
            'cc': self.get_cc_emails()
        }


class CostCenterEmail(models.Model):
    """
    Cost Center Email model - stores multiple emails for each cost center.
    Each email can be either a recipient (TO) or CC.
    """
    EMAIL_TYPE_CHOICES = [
        ('recipient', _('Recipient (TO)')),
        ('cc', _('CC (Carbon Copy)')),
    ]
    
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.CASCADE,
        related_name='emails',
        verbose_name=_("Cost Center")
    )
    email = models.EmailField(
        max_length=255,
        verbose_name=_("Email Address"),
        validators=[EmailValidator()]
    )
    email_hash = models.CharField(
        max_length=64,
        db_index=True,
        editable=False,
        help_text=_("SHA256 hash for database-portable queries")
    )
    email_type = models.CharField(
        max_length=20,
        choices=EMAIL_TYPE_CHOICES,
        db_index=True,
        verbose_name=_("Email Type"),
        help_text=_("Type of email: recipient (TO) or cc")
    )
    display_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Display Name"),
        help_text=_("Optional display name for the email")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Is Active")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        db_table = 'email_costcenter_email'
        ordering = ['email_type', 'email']
        verbose_name = _("Cost Center Email")
        verbose_name_plural = _("Cost Center Emails")
        unique_together = [('cost_center', 'email', 'email_type')]
        indexes = [
            models.Index(fields=['email_hash'], name='idx_cc_email_hash'),
            models.Index(fields=['email_type'], name='idx_cc_email_type'),
            models.Index(fields=['cost_center', 'email_type'], name='idx_cc_emailtype'),
        ]

    def save(self, *args, **kwargs):
        """Generate hash for Oracle-compatible queries"""
        if self.email:
            self.email_hash = hashlib.sha256(
                self.email.lower().encode()
            ).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.email} ({self.get_email_type_display()}) - {self.cost_center.cost_center_code}"


class EmailTemplate(models.Model):
    """
    Email Template model - pre-defined email formats that users can edit before sending.
    Templates are starting points, not final content.
    """
    CATEGORY_CHOICES = [
        ('GENERAL', _('General')),
        ('ANNOUNCEMENT', _('Announcement')),
        ('NOTIFICATION', _('Notification')),
        ('REMINDER', _('Reminder')),
        ('REPORT', _('Report')),
        ('OTHER', _('Other')),
    ]

    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name=_("Template Name")
    )
    name_ar = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Template Name (Arabic)")
    )
    subject = models.CharField(
        max_length=500,
        verbose_name=_("Default Subject"),
        help_text=_("Users can edit before sending")
    )
    subject_ar = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name=_("Default Subject (Arabic)")
    )
    body_html = models.TextField(
        verbose_name=_("Default HTML Body"),
        help_text=_("Users can edit before sending")
    )
    body_html_ar = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Default HTML Body (Arabic)")
    )
    body_text = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Plain Text Body"),
        help_text=_("Auto-generated fallback")
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Is Active"),
        help_text=_("Only active templates shown to users")
    )
    category = models.CharField(
        max_length=100,
        choices=CATEGORY_CHOICES,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Category")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_email_templates',
        verbose_name=_("Created By")
    )

    objects = EmailTemplateManager()

    class Meta:
        db_table = 'email_template'
        ordering = ['-created_at']
        verbose_name = _("Email Template")
        verbose_name_plural = _("Email Templates")
        indexes = [
            models.Index(fields=['is_active'], name='idx_tmpl_active'),
            models.Index(fields=['category'], name='idx_tmpl_category'),
        ]

    def __str__(self):
        return self.name


class EmailDraft(models.Model):
    """
    Email Draft model - stores draft emails before sending.
    """
    SEND_TYPE_CHOICES = [
        ('ANNOUNCEMENT', _('Announcement (All Cost Centers)')),
        ('SPECIFIC', _('Specific Cost Centers')),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_drafts',
        verbose_name=_("Draft Owner")
    )
    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='drafts',
        verbose_name=_("Template Used")
    )
    send_type = models.CharField(
        max_length=20,
        choices=SEND_TYPE_CHOICES,
        verbose_name=_("Send Type")
    )
    subject = models.CharField(
        max_length=500,
        verbose_name=_("Email Subject")
    )
    body_html = models.TextField(
        verbose_name=_("Email Body (HTML)")
    )
    cost_center_ids = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Cost Center IDs"),
        help_text=_("Comma-separated IDs for SPECIFIC send type")
    )
    draft_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Draft Name"),
        help_text=_("Optional name for organizing drafts")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At")
    )
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Is Deleted"),
        help_text=_("Soft delete flag")
    )

    objects = EmailDraftManager()

    class Meta:
        db_table = 'email_draft'
        ordering = ['-updated_at']
        verbose_name = _("Email Draft")
        verbose_name_plural = _("Email Drafts")
        indexes = [
            models.Index(fields=['user', 'is_deleted'], name='idx_draft_user_del'),
            models.Index(fields=['created_at'], name='idx_draft_created'),
        ]

    def __str__(self):
        return f"Draft by {self.user.email}: {self.subject[:50]}"

    def get_cost_center_list(self):
        """Parse cost center IDs from text field"""
        if not self.cost_center_ids:
            return []
        return [int(id.strip()) for id in self.cost_center_ids.split(',') if id.strip()]

    def set_cost_center_list(self, ids):
        """Set cost center IDs as comma-separated string"""
        self.cost_center_ids = ','.join(str(id) for id in ids)


class EmailLog(models.Model):
    """
    Email Log model - tracks all sent and received emails.
    Creates TWO records per send: one SENT (for sender's outbox) and one RECEIVED per cost center.
    """
    SEND_TYPE_CHOICES = [
        ('ANNOUNCEMENT', _('Announcement')),
        ('SPECIFIC', _('Specific Cost Centers')),
    ]
    EMAIL_TYPE_CHOICES = [
        ('SENT', _('Sent Email')),
        ('RECEIVED', _('Received Email')),
    ]
    STATUS_CHOICES = [
        ('SUCCESS', _('Success')),
        ('FAILED', _('Failed')),
        ('PENDING', _('Pending')),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='email_logs',
        verbose_name=_("User")
    )
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
        verbose_name=_("Cost Center")
    )
    template = models.ForeignKey(
        EmailTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_logs',
        verbose_name=_("Template Used")
    )
    draft = models.ForeignKey(
        EmailDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_emails',
        verbose_name=_("Draft Sent From")
    )
    send_type = models.CharField(
        max_length=20,
        choices=SEND_TYPE_CHOICES,
        db_index=True,
        verbose_name=_("Send Type")
    )
    email_type = models.CharField(
        max_length=20,
        choices=EMAIL_TYPE_CHOICES,
        db_index=True,
        verbose_name=_("Email Type"),
        help_text=_("SENT for outbox, RECEIVED for inbox")
    )
    subject = models.CharField(
        max_length=500,
        verbose_name=_("Email Subject")
    )
    body_html = models.TextField(
        verbose_name=_("Email Body (HTML)")
    )
    recipient_emails = models.TextField(
        verbose_name=_("Recipient Emails (TO)"),
        help_text=_("Comma-separated TO emails")
    )
    cc_emails = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("CC Emails"),
        help_text=_("Comma-separated CC emails")
    )
    email_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True,
        verbose_name=_("Email Status")
    )
    email_error = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Error Message")
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_("Sent At")
    )
    metadata = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Metadata (JSON)"),
        help_text=_("Additional data as JSON string")
    )

    objects = EmailLogManager()

    class Meta:
        db_table = 'email_log'
        ordering = ['-sent_at']
        verbose_name = _("Email Log")
        verbose_name_plural = _("Email Logs")
        indexes = [
            models.Index(fields=['user', 'email_type'], name='idx_log_user_type'),
            models.Index(fields=['email_status'], name='idx_log_status'),
            models.Index(fields=['sent_at'], name='idx_log_sent_at'),
            models.Index(fields=['cost_center'], name='idx_log_cc'),
        ]

    def __str__(self):
        return f"{self.email_type}: {self.subject[:50]} - {self.email_status}"

    def get_recipient_list(self):
        """Parse recipient emails from text field"""
        if not self.recipient_emails:
            return []
        return [e.strip() for e in self.recipient_emails.split(',') if e.strip()]

    def set_recipient_list(self, emails):
        """Set recipient emails as comma-separated string"""
        self.recipient_emails = ','.join(emails)

    def get_cc_list(self):
        """Parse CC emails from text field"""
        if not self.cc_emails:
            return []
        return [e.strip() for e in self.cc_emails.split(',') if e.strip()]

    def set_cc_list(self, emails):
        """Set CC emails as comma-separated string"""
        self.cc_emails = ','.join(emails)

    def get_metadata(self):
        """Parse metadata JSON"""
        if not self.metadata:
            return {}
        try:
            return json.loads(self.metadata)
        except json.JSONDecodeError:
            return {}

    def set_metadata(self, data):
        """Set metadata as JSON string"""
        self.metadata = json.dumps(data)


class EmailRecipientView(models.Model):
    """
    Email Recipient View model - tracks which users received each email.
    Used for inbox functionality with per-recipient read/star/archive status.
    """
    email_log = models.ForeignKey(
        EmailLog,
        on_delete=models.CASCADE,
        related_name='recipient_views',
        verbose_name=_("Email Log")
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_emails',
        verbose_name=_("Recipient User")
    )
    is_to = models.BooleanField(
        default=True,
        verbose_name=_("Is TO Recipient"),
        help_text=_("True if in TO field, False if in CC")
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Is Read")
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Read At")
    )
    is_starred = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Is Starred")
    )
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Is Archived")
    )

    objects = EmailRecipientViewManager()

    class Meta:
        db_table = 'email_recipient_view'
        ordering = ['-email_log__sent_at']
        verbose_name = _("Email Recipient View")
        verbose_name_plural = _("Email Recipient Views")
        unique_together = [['email_log', 'recipient_user']]
        indexes = [
            models.Index(fields=['recipient_user', 'is_read'], name='idx_recip_user_read'),
            models.Index(fields=['recipient_user', 'is_starred'], name='idx_recip_user_star'),
            models.Index(fields=['recipient_user', 'is_archived'], name='idx_recip_user_arch'),
        ]

    def __str__(self):
        return f"{self.recipient_user.email} - {self.email_log.subject[:30]}"

    def mark_as_read(self):
        """Mark email as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def toggle_starred(self):
        """Toggle starred status"""
        self.is_starred = not self.is_starred
        self.save(update_fields=['is_starred'])

    def toggle_archived(self):
        """Toggle archived status"""
        self.is_archived = not self.is_archived
        self.save(update_fields=['is_archived'])
