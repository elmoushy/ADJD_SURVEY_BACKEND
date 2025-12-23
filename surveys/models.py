"""
Models for the surveys service with encryption support and Oracle compatibility.

This module defines the database models for surveys, questions, responses,
and sharing with role-based access control, AES-256 encryption, and
Oracle-compatible hash fields for filtering.
"""

import hashlib
import logging
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from .encryption import surveys_data_encryption

logger = logging.getLogger(__name__)
User = get_user_model()

# Import Group model from authentication app
try:
    from authentication.models import Group
    from authentication.managers import OracleCompatibleSurveyManager, OracleCompatibleQuestionManager
except ImportError:
    # Handle case where authentication app is not available
    Group = None
    OracleCompatibleSurveyManager = models.Manager
    OracleCompatibleQuestionManager = models.Manager


# Import timezone utilities to maintain consistent UAE timezone handling
try:
    from .timezone_utils import ensure_uae_timezone, now_uae, is_currently_active_uae, get_status_uae
except ImportError:
    # Fallback to basic timezone functions if timezone_utils not available
    def ensure_uae_timezone(dt):
        return dt
    def now_uae():
        return timezone.now()
    def is_currently_active_uae(survey):
        return survey.is_currently_active()
    def get_status_uae(survey):
        return survey.get_status()


class EncryptedTextField(models.TextField):
    """Custom text field that automatically encrypts/decrypts data for surveys"""
    
    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return surveys_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt text field: {e}")
            return value
    
    def to_python(self, value):
        if not value:
            return value
        if isinstance(value, str):
            # Always decrypt string values to handle all scenarios
            try:
                return surveys_data_encryption.decrypt(value)
            except Exception as e:
                logger.error(f"Failed to decrypt text field in to_python: {e}")
                return value
        try:
            return surveys_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt text field in to_python: {e}")
            return value
    
    def get_prep_value(self, value):
        if not value:
            return value
        try:
            # Ensure value is a string before encryption
            if not isinstance(value, str):
                value = str(value)
            return surveys_data_encryption.encrypt(value)
        except Exception as e:
            logger.error(f"Failed to encrypt text field: {e}")
            return value


class EncryptedCharField(models.CharField):
    """Custom char field that automatically encrypts/decrypts data for surveys"""
    
    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return surveys_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt char field: {e}")
            return value
    
    def to_python(self, value):
        if not value:
            return value
        if isinstance(value, str):
            # Always decrypt string values to handle all scenarios
            try:
                return surveys_data_encryption.decrypt(value)
            except Exception as e:
                logger.error(f"Failed to decrypt char field in to_python: {e}")
                return value
        try:
            return surveys_data_encryption.decrypt(value)
        except Exception as e:
            logger.error(f"Failed to decrypt char field in to_python: {e}")
            return value
    
    def get_prep_value(self, value):
        if not value:
            return value
        try:
            # Ensure value is a string before encryption
            if not isinstance(value, str):
                value = str(value)
            return surveys_data_encryption.encrypt(value)
        except Exception as e:
            logger.error(f"Failed to encrypt char field: {e}")
            return value


class Survey(models.Model):
    """
    Main survey model with four visibility levels:
    - PRIVATE: Creator + explicitly shared users only
    - AUTH: Any authenticated user with valid JWT
    - PUBLIC: Anonymous visitors can access
    - GROUPS: Shared with specific groups
    """
    
    VISIBILITY_CHOICES = [
        ("PRIVATE", "Creator & shared list"),
        ("AUTH", "All authenticated users"),
        ("PUBLIC", "Everyone, even anonymous"),
        ("GROUPS", "Shared with specific groups"),
    ]
    
    # Primary fields
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    title = EncryptedCharField(
        max_length=255,
        help_text='Survey title (encrypted)'
    )
    title_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA256 hash of title for search indexing'
    )
    description = EncryptedTextField(
        blank=True,
        help_text='Survey description (encrypted)'
    )
    
    # Ownership and sharing
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_surveys",
        help_text='User who created this survey'
    )
    visibility = models.CharField(
        max_length=8,
        choices=VISIBILITY_CHOICES,
        default="AUTH",
        help_text='Survey visibility level'
    )
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name="shared_surveys",
        help_text='Users who can access this private survey'
    )
    shared_with_groups = models.ManyToManyField(
        'authentication.Group',
        blank=True,
        related_name="shared_surveys_groups",
        help_text='Groups who can access this survey'
    )
    
    # Survey scheduling
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Survey start date/time. If not set, survey starts immediately when created.'
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Survey end date/time. If not set, survey runs indefinitely.'
    )
    
    # Survey settings
    is_locked = models.BooleanField(
        default=False,
        help_text='Whether survey is locked for editing'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether survey is active and accepting responses'
    )
    
    # Public survey access settings
    CONTACT_METHOD_CHOICES = [
        ('email', 'Email'),
        ('phone', 'Phone'),
    ]
    public_contact_method = models.CharField(
        max_length=5,
        choices=CONTACT_METHOD_CHOICES,
        default='email',
        help_text='Contact method required for public survey submissions (email or phone)'
    )
    
    # Per-device access control for PUBLIC surveys
    per_device_access = models.BooleanField(
        default=False,
        null=False,
        blank=False,
        help_text='If enabled, survey can only be filled once per device (no email/phone required)'
    )
    
    # Draft/Submit status
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ]
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        help_text='Survey status - draft surveys can be edited, submitted surveys are final'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Use Oracle-compatible manager
    objects = OracleCompatibleSurveyManager()
    
    class Meta:
        db_table = 'surveys_survey'
        verbose_name = 'Survey'
        verbose_name_plural = 'Surveys'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['title_hash'],
                name='surveys_title_hash_idx'
                # Removed condition for Oracle compatibility
            ),
        ]
        # Indexes are already created by migrations 0001_initial and 0006_survey_end_date_survey_start_date_and_more
    
    def __str__(self):
        return f"Survey: {self.title} ({self.visibility})"
    
    def soft_delete(self):
        """Soft delete the survey"""
        self.deleted_at = timezone.now()
        self.save()
    
    def is_currently_active(self):
        """Check if survey is currently active based on date range and is_active flag"""
        if not self.is_active or self.deleted_at is not None:
            return False
        
        now = timezone.now()
        
        # Check start date
        if self.start_date and now < self.start_date:
            return False
        
        # Check end date
        if self.end_date and now > self.end_date:
            return False
        
        return True
    
    def get_status(self):
        """Get current status of the survey"""
        if self.deleted_at is not None:
            return 'deleted'
        
        if not self.is_active:
            return 'inactive'
        
        now = timezone.now()
        
        if self.start_date and now < self.start_date:
            return 'scheduled'
        
        if self.end_date and now > self.end_date:
            return 'expired'
        
        return 'active'
    
    def can_be_edited(self):
        """
        Check if survey can be edited based on status, visibility, and responses.
        - Draft surveys: Always editable
        - Submitted surveys: Editable based on visibility settings and responses
          * PRIVATE surveys: Can be edited after submission
          * AUTH surveys: Can be edited after submission
          * PUBLIC surveys: Can be edited ONLY if no responses exist yet
          * GROUPS surveys: Can be edited after submission
        """
        if self.deleted_at is not None:
            return False
            
        if self.status == 'draft':
            return True
            
        if self.status == 'submitted':
            # PUBLIC surveys can only be edited if no one has responded yet
            if self.visibility == 'PUBLIC':
                return not self.responses.exists()
            
            # Other visibility types can be edited after submission
            return self.visibility in ['PRIVATE', 'AUTH', 'GROUPS']
            
        return False
    
    def submit(self):
        """Submit the survey - makes it final and non-editable"""
        self.status = 'submitted'
        self.save()
    
    def save(self, *args, **kwargs):
        """Override save to generate title hash and handle date logic with UAE timezone"""
        if self.title:
            self.title_hash = hashlib.sha256(self.title.encode('utf-8')).hexdigest()
        
        # Debug: Log the current per_device_access value
        logger.info(f"Survey.save() - per_device_access before check: {self.per_device_access} (type: {type(self.per_device_access)})")
        
        # Ensure per_device_access is never None - default to False
        if self.per_device_access is None:
            self.per_device_access = False
            logger.info(f"Survey.save() - Set per_device_access to False due to None value")
        
        # Debug: Log the final per_device_access value
        logger.info(f"Survey.save() - per_device_access final value: {self.per_device_access}")
        
        # If only end_date is provided, set start_date to created_at (or now if updating)
        if self.end_date and not self.start_date:
            if not self.pk:  # New survey
                self.start_date = now_uae()
            elif not self.start_date:  # Existing survey without start_date
                self.start_date = ensure_uae_timezone(self.created_at) if self.created_at else now_uae()
        
        # Ensure start_date and end_date are in UAE timezone
        if self.start_date:
            self.start_date = ensure_uae_timezone(self.start_date)
        if self.end_date:
            self.end_date = ensure_uae_timezone(self.end_date)
        
        # If no end_date is provided, survey runs indefinitely until deactivated
        # This is handled by the is_currently_active() method which only checks end_date if it exists
        
        super().save(*args, **kwargs)


class Question(models.Model):
    """Survey question with encrypted content"""
    
    QUESTION_TYPES = [
        ('text', 'Text Input'),
        ('textarea', 'Long Text'),
        ('single_choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
        ('rating', 'Rating Scale'),
        ('yes_no', 'Yes/No'),
    ]
    
    # Validation types for text/textarea questions
    VALIDATION_TYPES = [
        ('none', 'No Validation'),
        ('email', 'Email Address'),
        ('phone', 'Phone Number'),
        ('number', 'Numeric Only'),
        ('url', 'URL'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    text = EncryptedTextField(help_text='Question text (encrypted)')
    text_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA256 hash of question text for search indexing'
    )
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES,
        default='text'
    )
    options = EncryptedTextField(
        blank=True,
        help_text='JSON array of options for choice questions (encrypted)'
    )
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    # Validation type for text/textarea questions
    validation_type = models.CharField(
        max_length=20,
        choices=VALIDATION_TYPES,
        default='none',
        help_text='Validation type for text input (auto-detected from question text or manually set)'
    )
    
    # Analytics calculation flags (PRIMARY approach for 100% accuracy)
    NPS_Calculate = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Indicates if this question is used for NPS calculation (only valid for rating questions)'
    )
    
    CSAT_Calculate = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Indicates if this question is used for CSAT calculation (only valid for single_choice, rating, yes_no)'
    )
    
    # Scale metadata for rating questions
    min_scale = models.IntegerField(
        null=True,
        blank=True,
        default=0,
        help_text='Minimum value for rating scale (default 0 for NPS, auto-detect for CSAT)'
    )
    
    max_scale = models.IntegerField(
        null=True,
        blank=True,
        default=5,
        help_text='Maximum value for rating scale (default 5 for NPS, auto-detect for CSAT)'
    )
    
    # OPTIONAL fallback: Semantic tag (for legacy/heuristic matching)
    SEMANTIC_TAG_CHOICES = [
        ('none', 'None'),
        ('nps', 'NPS'),
        ('csat', 'CSAT')
    ]
    semantic_tag = models.CharField(
        max_length=20,
        choices=SEMANTIC_TAG_CHOICES,
        default='none',
        db_index=True,
        help_text='Semantic tag for analytics optimization (fallback if Calculate flags not set)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Use Oracle-compatible manager
    objects = OracleCompatibleQuestionManager()
    
    class Meta:
        db_table = 'surveys_question'
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'
        ordering = ['survey', 'order']
        indexes = [
            models.Index(
                fields=['text_hash'],
                name='questions_text_hash_idx'
                # Removed condition for Oracle compatibility
            ),
        ]
    
    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}..."
    
    def clean(self):
        """Validate NPS_Calculate and CSAT_Calculate flags"""
        from django.core.exceptions import ValidationError
        super().clean()
        
        # Validate NPS_Calculate flag
        if self.NPS_Calculate and self.question_type not in ['rating', 'تقييم']:
            raise ValidationError({
                'NPS_Calculate': 'NPS_Calculate can only be True for rating questions.'
            })
        
        # Validate CSAT_Calculate flag
        valid_csat_types = ['single_choice', 'rating', 'yes_no', 'اختيار واحد', 'تقييم', 'نعم/لا']
        if self.CSAT_Calculate and self.question_type not in valid_csat_types:
            raise ValidationError({
                'CSAT_Calculate': 'CSAT_Calculate can only be True for single_choice, rating, or yes_no questions.'
            })
        
        # Validate scale ranges for rating questions
        if self.question_type in ['rating', 'تقييم']:
            if self.min_scale is None:
                self.min_scale = 0
            if self.max_scale is None:
                self.max_scale = 5
            if self.min_scale >= self.max_scale:
                raise ValidationError({
                    'min_scale': 'min_scale must be less than max_scale.'
                })
    
    def save(self, *args, **kwargs):
        """Override save to generate text hash and auto-detect validation type"""
        if self.text:
            self.text_hash = hashlib.sha256(self.text.encode('utf-8')).hexdigest()
            
            # Auto-detect validation type from question text if not manually set
            if self.validation_type == 'none' and self.question_type in ['text', 'textarea']:
                self.validation_type = self._detect_validation_type()
        
        super().save(*args, **kwargs)
    
    def _detect_validation_type(self):
        """
        Auto-detect validation type based on question text (supports Arabic and English).
        
        Returns:
            str: Detected validation type ('email', 'phone', 'number', 'url', or 'none')
        """
        if not self.text:
            return 'none'
        
        text_lower = self.text.lower()
        
        # Email detection (Arabic and English)
        email_keywords = [
            'بريد', 'ايميل', 'إيميل', 'البريد الإلكتروني', 'بريد إلكتروني',
            'email', 'e-mail', 'mail address', 'electronic mail'
        ]
        if any(keyword in text_lower for keyword in email_keywords):
            return 'email'
        
        # Phone detection (Arabic and English)
        phone_keywords = [
            'هاتف', 'جوال', 'موبايل', 'رقم الهاتف', 'رقم الجوال', 'تليفون',
            'phone', 'mobile', 'telephone', 'cell', 'contact number'
        ]
        if any(keyword in text_lower for keyword in phone_keywords):
            return 'phone'
        
        # Number detection (Arabic and English)
        number_keywords = [
            'رقم', 'عدد', 'كمية',
            'number', 'quantity', 'amount', 'count'
        ]
        # Only detect as number if it's not already detected as phone
        if any(keyword in text_lower for keyword in number_keywords):
            # Avoid false positives with phone
            if not any(keyword in text_lower for keyword in phone_keywords):
                return 'number'
        
        # URL detection (Arabic and English)
        url_keywords = [
            'رابط', 'موقع', 'لينك', 'url',
            'link', 'website', 'url', 'web address'
        ]
        if any(keyword in text_lower for keyword in url_keywords):
            return 'url'
        
        return 'none'
    
    def validate_csat_options(self):
        """
        Validate that CSAT questions have required QuestionOption mappings.
        
        Should be called after question is saved and options are created.
        Returns (is_valid, error_message) tuple.
        """
        if not self.CSAT_Calculate:
            return (True, None)
        
        if self.question_type in ['single_choice', 'اختيار واحد']:
            # Check all options have satisfaction_value
            options_count = self.option_mappings.count()
            options_with_value = self.option_mappings.filter(satisfaction_value__isnull=False).count()
            if options_count > 0 and options_with_value < options_count:
                return (False, f"CSAT single_choice questions require satisfaction_value for all options ({options_with_value}/{options_count} have values)")
        
        elif self.question_type in ['yes_no', 'نعم/لا']:
            # Check exactly 2 options exist with satisfaction_value
            options_count = self.option_mappings.count()
            if options_count != 2:
                return (False, f"CSAT yes/no questions require exactly 2 QuestionOption records (found {options_count})")
            options_with_value = self.option_mappings.filter(satisfaction_value__isnull=False).count()
            if options_with_value != 2:
                return (False, f"CSAT yes/no questions require satisfaction_value for both yes/no options ({options_with_value}/2 have values)")
        
        return (True, None)


class QuestionCondition(models.Model):
    """
    Defines conditional logic for questions to appear based on previous answers.
    
    This model creates a trigger-action relationship where:
    - trigger_question: The question whose answer determines visibility
    - trigger_answer_value: The specific answer that triggers the conditional question
    - dependent_question: The question that should appear when condition is met
    
    Example:
    Q1: "Do you own a car?" (Yes/No)
    Q2: "What is your car's brand?" (Text) - Only shows if Q1 = "Yes"
    
    Rules:
    - trigger_question must appear before dependent_question (order validation)
    - Only yes_no and single_choice questions can be triggers
    - Multiple conditions can trigger the same dependent_question (OR logic)
    - Circular dependencies are not allowed
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    trigger_question = models.ForeignKey(
        'Question',
        on_delete=models.CASCADE,
        related_name='triggers_for',
        help_text='The question whose answer triggers this condition'
    )
    
    trigger_answer_value = models.CharField(
        max_length=255,
        help_text='The exact answer value that triggers the condition (not encrypted for efficient matching)'
    )
    
    dependent_question = models.ForeignKey(
        'Question',
        on_delete=models.CASCADE,
        related_name='conditional_on',
        help_text='The question that appears when the condition is met'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'surveys_question_condition'
        verbose_name = 'Question Condition'
        verbose_name_plural = 'Question Conditions'
        # Ensure no duplicate conditions
        unique_together = ['trigger_question', 'trigger_answer_value', 'dependent_question']
        indexes = [
            models.Index(fields=['trigger_question'], name='qcond_trigger_q_idx'),
            models.Index(fields=['dependent_question'], name='qcond_dependent_q_idx'),
            models.Index(fields=['trigger_question', 'trigger_answer_value'], name='qcond_trigger_ans_idx'),
        ]
    
    def __str__(self):
        return f"If Q{self.trigger_question.order} = '{self.trigger_answer_value}' → Show Q{self.dependent_question.order}"
    
    def clean(self):
        """Validate conditional question rules"""
        from django.core.exceptions import ValidationError
        super().clean()
        
        # Rule 1: Questions must be in the same survey
        if self.trigger_question.survey != self.dependent_question.survey:
            raise ValidationError(
                "Trigger and dependent questions must be in the same survey."
            )
        
        # Rule 2: Trigger question must come before dependent question
        if self.trigger_question.order >= self.dependent_question.order:
            raise ValidationError(
                "Trigger question must appear before the dependent question (lower order number)."
            )
        
        # Rule 3: Only yes_no and single_choice can be triggers
        valid_trigger_types = ['yes_no', 'single_choice', 'نعم/لا', 'اختيار واحد']
        if self.trigger_question.question_type not in valid_trigger_types:
            raise ValidationError(
                f"Only yes/no and single choice questions can be triggers. Got: {self.trigger_question.question_type}"
            )
        
        # Rule 4: No circular dependencies 
        # Check if dependent_question (directly or indirectly) triggers the trigger_question
        # This requires checking the full dependency chain
        def creates_cycle(current_q, target_q, visited=None):
            """Check if current_q eventually triggers target_q"""
            if visited is None:
                visited = set()
            
            if current_q.id in visited:
                return False  # Already checked this branch
            
            visited.add(current_q.id)
            
            # Get all questions that current_q triggers
            triggered_by_current = QuestionCondition.objects.filter(
                trigger_question=current_q
            ).select_related('dependent_question')
            
            for condition in triggered_by_current:
                if condition.dependent_question.id == target_q.id:
                    return True  # Direct cycle found
                
                # Check transitive dependencies
                if creates_cycle(condition.dependent_question, target_q, visited):
                    return True
            
            return False
        
        # Check if this new condition would create a cycle
        if creates_cycle(self.dependent_question, self.trigger_question):
            raise ValidationError(
                "Circular dependency detected: dependent question cannot trigger its own trigger question."
            )
    
    def save(self, *args, **kwargs):
        """Override save to call clean validation"""
        self.clean()
        super().save(*args, **kwargs)


class QuestionOption(models.Model):
    """
    Individual option for single_choice/multiple_choice/yes_no questions with CSAT satisfaction mapping.
    
    This model stores metadata for each option separately from the encrypted options JSON,
    allowing for efficient CSAT classification without decrypting all answers.
    
    For yes/no questions:
    - Create 2 options: one for "Yes" and one for "No"
    - Map each to appropriate satisfaction_value based on question context
    - Example: "Did you experience problems?" - Yes=Dissatisfied(0), No=Satisfied(2)
    - Example: "Are you satisfied?" - Yes=Satisfied(2), No=Dissatisfied(0)
    """
    
    SATISFACTION_CHOICES = [
        (2, 'Satisfied'),     # ممتاز، جيد، مرضي
        (1, 'Neutral'),       # عادي، محايد، مقبول
        (0, 'Dissatisfied')   # سيئ، غير مرضي
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='option_mappings'
    )
    option_text = EncryptedCharField(
        max_length=255,
        help_text='Option text (encrypted). For yes/no: "yes", "no", "نعم", "لا"'
    )
    option_text_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text='SHA256 hash of option text for efficient matching'
    )
    satisfaction_value = models.IntegerField(
        null=True,
        blank=True,
        choices=SATISFACTION_CHOICES,
        db_index=True,
        help_text='CSAT satisfaction mapping (required when question.CSAT_Calculate=True for single_choice/yes_no)'
    )
    order = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'surveys_question_option'
        verbose_name = 'Question Option'
        verbose_name_plural = 'Question Options'
        ordering = ['question', 'order']
        indexes = [
            models.Index(fields=['option_text_hash'], name='option_text_hash_idx'),
            models.Index(fields=['satisfaction_value'], name='option_satisfaction_idx'),
        ]
        # Unique constraint on question + option_text_hash to prevent duplicates
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'option_text_hash'],
                name='unique_question_option_hash'
            )
        ]
    
    def __str__(self):
        satisfaction_str = dict(self.SATISFACTION_CHOICES).get(self.satisfaction_value, 'Unset')
        return f"{self.option_text[:30]} ({satisfaction_str})"
    
    def save(self, *args, **kwargs):
        """Override save to generate option_text hash"""
        if self.option_text:
            self.option_text_hash = hashlib.sha256(self.option_text.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)


class Response(models.Model):
    """Survey response with encrypted answers"""
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='responses'
    )
    respondent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='survey_responses',
        help_text='Null for anonymous responses'
    )
    respondent_email = models.EmailField(
        null=True,
        blank=True,
        help_text='Email for anonymous responses (when respondent is null)'
    )
    respondent_phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text='Phone for anonymous responses (when respondent is null)'
    )
    
    # Response metadata
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_complete = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'surveys_response'
        verbose_name = 'Response'
        verbose_name_plural = 'Responses'
        ordering = ['-submitted_at']
        # Indexes are already created by migrations 0001_initial and 0005_add_unique_response_constraints
        # Note: Oracle doesn't support unique constraints with conditions
        # We'll handle uniqueness validation in the model's clean() method instead
    
    def __str__(self):
        user_info = self.respondent.email if self.respondent else "Anonymous"
        return f"Response to {self.survey.title} by {user_info}"
    
    def clean(self):
        """Custom validation to handle uniqueness constraints that Oracle doesn't support."""
        from django.core.exceptions import ValidationError
        
        # Check for authenticated user duplicate responses
        if self.respondent:
            existing = Response.objects.filter(
                survey=self.survey, 
                respondent=self.respondent
            ).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError("You have already submitted a response to this survey.")
        
        # For per-device access surveys, device tracking is handled separately
        # The validation will be done in the views before creating the response
        
        # Check for anonymous user duplicate responses (same email or phone based on survey settings)
        elif not self.survey.per_device_access and (self.respondent_email or self.respondent_phone):
            # Only check email/phone duplicates if not using per-device access
            # Determine which contact method to check based on survey settings
            if self.survey.public_contact_method == 'email' and self.respondent_email:
                existing = Response.objects.filter(
                    survey=self.survey,
                    respondent__isnull=True,
                    respondent_email=self.respondent_email
                ).exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError("A response has already been submitted with this email address.")
            elif self.survey.public_contact_method == 'phone' and self.respondent_phone:
                existing = Response.objects.filter(
                    survey=self.survey,
                    respondent__isnull=True,
                    respondent_phone=self.respondent_phone
                ).exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError("A response has already been submitted with this phone number.")

    def save(self, *args, **kwargs):
        """Override save to call clean validation."""
        self.clean()
        super().save(*args, **kwargs)


class DeviceResponse(models.Model):
    """
    Track survey responses by device fingerprint for per-device access control.
    This model stores device fingerprints to prevent multiple submissions from the same device.
    Primary device identifier is MAC address; IP address kept for legacy/backward compatibility.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='device_responses',
        help_text='Survey this device response belongs to'
    )
    device_fingerprint = models.CharField(
        max_length=64,
        help_text='SHA256 hash of device fingerprint (MAC Address + User-Agent + Screen Resolution + Timezone + Platform)'
    )
    mac_address = models.CharField(
        max_length=17,
        null=True,
        blank=True,
        help_text='MAC address of the device (primary device identifier)'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='IP address of the device (kept for backward compatibility, not used for tracking)'
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        help_text='User agent string from the device'
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    # Link to the actual response if created
    response = models.OneToOneField(
        'Response',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='device_tracking',
        help_text='Associated response object'
    )
    
    class Meta:
        db_table = 'surveys_device_response'
        verbose_name = 'Device Response'
        verbose_name_plural = 'Device Responses'
        unique_together = ['survey', 'device_fingerprint']
        indexes = [
            models.Index(fields=['survey', 'device_fingerprint'], name='surveys_device_survey_fp_idx'),
            models.Index(fields=['device_fingerprint'], name='surveys_device_fp_idx'),
            models.Index(fields=['mac_address'], name='surveys_device_mac_idx'),
        ]
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"Device response to {self.survey.title} ({self.device_fingerprint[:12]}...)"
    
    @classmethod
    def generate_device_fingerprint(cls, request):
        """
        Generate a device fingerprint from request data.
        Now uses MAC address as the primary identifier.
        
        Args:
            request: Django request object
            
        Returns:
            str: SHA256 hash of device characteristics
        """
        # Get MAC address from custom header (primary identifier)
        mac_address = request.META.get('HTTP_X_MAC_ADDRESS', '')
        
        # Get basic device information from request
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
        
        # Get additional device info from custom headers (if provided by frontend)
        screen_resolution = request.META.get('HTTP_X_SCREEN_RESOLUTION', '')
        timezone = request.META.get('HTTP_X_TIMEZONE', '')
        platform = request.META.get('HTTP_X_PLATFORM', '')
        
        # Combine all available device characteristics with MAC as primary
        device_info = f"{mac_address}|{user_agent}|{accept_language}|{accept_encoding}|{screen_resolution}|{timezone}|{platform}"
        
        # Generate SHA256 hash
        return hashlib.sha256(device_info.encode('utf-8')).hexdigest()
    
    @classmethod
    def has_device_submitted(cls, survey, request):
        """
        Check if a device has already submitted a response to this survey.
        
        Args:
            survey: Survey instance
            request: Django request object
            
        Returns:
            bool: True if device has already submitted, False otherwise
        """
        device_fingerprint = cls.generate_device_fingerprint(request)
        return cls.objects.filter(
            survey=survey,
            device_fingerprint=device_fingerprint
        ).exists()
    
    @classmethod
    def create_device_tracking(cls, survey, request, response=None):
        """
        Create a device tracking record.
        
        Args:
            survey: Survey instance
            request: Django request object
            response: Response instance (optional)
            
        Returns:
            DeviceResponse: Created device response record
        """
        device_fingerprint = cls.generate_device_fingerprint(request)
        mac_address = request.META.get('HTTP_X_MAC_ADDRESS', '')
        ip_address = request.META.get('REMOTE_ADDR')  # Kept for backward compatibility
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        return cls.objects.create(
            survey=survey,
            device_fingerprint=device_fingerprint,
            mac_address=mac_address if mac_address else None,
            ip_address=ip_address,
            user_agent=user_agent,
            response=response
        )


class Answer(models.Model):
    """Individual answer to a survey question with encryption"""
    
    id = models.AutoField(primary_key=True)  # Integer PK for better performance
    response = models.ForeignKey(
        Response,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    answer_text = EncryptedTextField(
        help_text='Answer content (encrypted)'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'surveys_answer'
        verbose_name = 'Answer'
        verbose_name_plural = 'Answers'
        unique_together = ['response', 'question']
        # Indexes are already created by migration 0001_initial
    
    def __str__(self):
        return f"Answer to {self.question.text[:30]}..."


class PublicAccessToken(models.Model):
    """
    Public access tokens for surveys to enable anonymous access.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name="public_tokens",
        help_text='Survey this token provides access to'
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        help_text='Unique token string for public access'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text='Token expiration date'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tokens",
        help_text='User who created this token'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether token is active'
    )
    # Password protection fields
    password = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text='Password for accessing the survey via this token'
    )
    restricted_email = models.TextField(
        blank=True,
        null=True,
        help_text='Comma-separated list of emails that can use the token'
    )
    restricted_phone = models.TextField(
        blank=True,
        null=True,
        help_text='Comma-separated list of phone numbers that can use the token'
    )
    
    class Meta:
        db_table = 'surveys_public_access_token'
        verbose_name = 'Public Access Token'
        verbose_name_plural = 'Public Access Tokens'
        ordering = ['-created_at']
        # Indexes are already created by migration 0002_publicaccesstoken
    
    def __str__(self):
        return f"Token for {self.survey.title} (expires {self.expires_at})"
    
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if token is valid (active and not expired)"""
        return self.is_active and not self.is_expired()
    
    def is_password_protected(self):
        """Check if token requires a password"""
        return bool(self.password)
    
    def is_contact_restricted(self):
        """Check if token is restricted to specific emails or phones"""
        return bool(self.get_restricted_emails() or self.get_restricted_phones())
    
    def get_restricted_emails(self):
        """Get list of restricted emails"""
        if not self.restricted_email:
            return []
        return [email.strip() for email in self.restricted_email.split(',') if email.strip()]
    
    def set_restricted_emails(self, email_list):
        """Set restricted emails from a list"""
        if email_list:
            self.restricted_email = ','.join(email_list)
        else:
            self.restricted_email = ''
    
    def get_restricted_phones(self):
        """Get list of restricted phones"""
        if not self.restricted_phone:
            return []
        return [phone.strip() for phone in self.restricted_phone.split(',') if phone.strip()]
    
    def set_restricted_phones(self, phone_list):
        """Set restricted phones from a list"""
        if phone_list:
            self.restricted_phone = ','.join(phone_list)
        else:
            self.restricted_phone = ''
    
    def validate_password(self, password):
        """Validate the provided password against the token's password"""
        if not self.is_password_protected():
            return True  # No password required
        return self.password == password
    
    def validate_contact(self, email=None, phone=None):
        """Validate the provided contact info against restrictions"""
        if not self.is_contact_restricted():
            return True  # No contact restrictions
        
        # Get the restricted lists
        restricted_emails = self.get_restricted_emails()
        restricted_phones = self.get_restricted_phones()
        
        # If there are restricted emails, check email validation
        if restricted_emails:
            if email and email.lower() in [e.lower() for e in restricted_emails]:
                return True  # Email matches restriction
            elif not restricted_phones:
                # Only emails are restricted and email doesn't match
                return False
        
        # If there are restricted phones, check phone validation
        if restricted_phones:
            if phone and phone in restricted_phones:
                return True  # Phone matches restriction
            elif not restricted_emails:
                # Only phones are restricted and phone doesn't match
                return False
        
        # If both emails and phones are restricted, at least one must match
        if restricted_emails and restricted_phones:
            email_valid = email and email.lower() in [e.lower() for e in restricted_emails]
            phone_valid = phone and phone in restricted_phones
            return email_valid or phone_valid
        
        return False
    
    @classmethod
    def generate_token(cls):
        """Generate a unique token string"""
        import secrets
        return secrets.token_urlsafe(32)
    
    @classmethod
    def generate_password(cls):
        """Generate a random password"""
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(8))


class SurveyTemplate(models.Model):
    """
    Survey template model for predefined and user-created templates.
    Supports both system-defined templates and custom user templates.
    """
    
    CATEGORY_CHOICES = [
        ('contact', 'Contact Information'),
        ('event', 'Event'),
        ('feedback', 'Feedback'),
        ('registration', 'Registration'),
        ('custom', 'Custom'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = EncryptedCharField(
        max_length=200,
        help_text='Template name (encrypted)'
    )
    name_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text='SHA256 hash of name for search indexing'
    )
    name_ar = EncryptedCharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Template name in Arabic (encrypted)'
    )
    description = EncryptedTextField(
        help_text='Template description (encrypted)'
    )
    description_ar = EncryptedTextField(
        null=True,
        blank=True,
        help_text='Template description in Arabic (encrypted)'
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='custom'
    )
    icon = models.CharField(
        max_length=50,
        default='fa-star',
        help_text='FontAwesome icon class'
    )
    preview_image = models.URLField(
        null=True,
        blank=True,
        help_text='Preview image URL'
    )
    is_predefined = models.BooleanField(
        default=False,
        help_text='Whether this is a system predefined template'
    )
    usage_count = models.IntegerField(
        default=0,
        help_text='Number of times this template has been used'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='created_templates',
        help_text='User who created this template (null for predefined templates)'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'surveys_template'
        verbose_name = 'Survey Template'
        verbose_name_plural = 'Survey Templates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name_hash'], name='surveys_tmpl_name_hash_idx'),
            models.Index(fields=['category'], name='surveys_tmpl_category_idx'),
            models.Index(fields=['is_predefined'], name='surveys_tmpl_predef_idx'),
        ]
    
    def __str__(self):
        return f"Template: {self.name}"
    
    def save(self, *args, **kwargs):
        """Override save to generate name hash"""
        if self.name:
            self.name_hash = hashlib.sha256(self.name.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)
    
    def increment_usage(self):
        """Increment the usage count"""
        self.usage_count += 1
        self.save(update_fields=['usage_count'])


class TemplateQuestion(models.Model):
    """
    Question template associated with a survey template.
    """
    
    QUESTION_TYPES = [
        ('text', 'Short Text'),
        ('textarea', 'Long Text'),
        ('single_choice', 'Single Choice'),
        ('multiple_choice', 'Multiple Choice'),
        ('rating', 'Rating'),
        ('yes_no', 'Yes/No'),
    ]
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    template = models.ForeignKey(
        SurveyTemplate,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    text = EncryptedTextField(
        help_text='Question text (encrypted)'
    )
    text_ar = EncryptedTextField(
        null=True,
        blank=True,
        help_text='Question text in Arabic (encrypted)'
    )
    question_type = models.CharField(
        max_length=50,
        choices=QUESTION_TYPES,
        default='text'
    )
    options = models.JSONField(
        null=True,
        blank=True,
        help_text='Options for choice questions (stored as JSON)'
    )
    is_required = models.BooleanField(default=False)
    order = models.IntegerField(default=1)
    placeholder = EncryptedCharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Placeholder text (encrypted)'
    )
    placeholder_ar = EncryptedCharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Placeholder text in Arabic (encrypted)'
    )
    
    # Analytics calculation flags (for templates to specify default analytics behavior)
    NPS_Calculate = models.BooleanField(
        default=False,
        help_text='Default NPS calculation flag when creating survey from template'
    )
    
    CSAT_Calculate = models.BooleanField(
        default=False,
        help_text='Default CSAT calculation flag when creating survey from template'
    )
    
    # Scale metadata for rating questions in templates
    min_scale = models.IntegerField(
        null=True,
        blank=True,
        help_text='Minimum value for rating scale (applied when creating survey from template)'
    )
    
    max_scale = models.IntegerField(
        null=True,
        blank=True,
        help_text='Maximum value for rating scale (applied when creating survey from template)'
    )
    
    class Meta:
        db_table = 'surveys_template_question'
        verbose_name = 'Template Question'
        verbose_name_plural = 'Template Questions'
        ordering = ['template', 'order']
        indexes = [
            models.Index(fields=['template', 'order'], name='surveys_tmpl_q_order_idx'),
        ]
    
    def __str__(self):
        return f"Template Q{self.order}: {self.text[:50]}..."
