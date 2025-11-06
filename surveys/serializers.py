"""
Serializers for surveys with role-based field filtering and validation.

This module follows the established patterns from the authentication system
with comprehensive validation and encryption support.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Survey, Question, Response, Answer, SurveyTemplate, TemplateQuestion
from .timezone_utils import (
    serialize_datetime_uae, get_status_uae, is_currently_active_uae,
    ensure_gregorian_from_hijri, convert_hijri_string_to_gregorian
)
from weaponpowercloud_backend.security_utils import validate_and_sanitize_text_input, sanitize_html_input
import json
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class UAEDateTimeField(serializers.DateTimeField):
    """
    Custom DateTimeField that:
    1. Accepts Hijri dates and converts them to Gregorian
    2. Always serializes in UAE timezone (Gregorian calendar)
    
    Input formats:
    - Standard datetime object (Gregorian)
    - Hijri date dict: {'year': 1446, 'month': 4, 'day': 15, 'is_hijri': True}
    - Hijri date string with 'H' prefix: 'H1446-04-15' or 'H1446-04-15 10:30:00'
    """
    
    def to_representation(self, value):
        """Always serialize datetime in UAE timezone (Gregorian)"""
        return serialize_datetime_uae(value)
    
    def to_internal_value(self, data):
        """
        Accept both Gregorian and Hijri dates, convert Hijri to Gregorian.
        """
        if data is None:
            return None
        
        # Check if it's a Hijri date dictionary
        if isinstance(data, dict) and data.get('is_hijri'):
            gregorian_dt = ensure_gregorian_from_hijri(data)
            if gregorian_dt is None:
                raise serializers.ValidationError("Invalid Hijri date provided")
            return gregorian_dt
        
        # Check if it's a Hijri date string (starts with 'H')
        if isinstance(data, str) and data.startswith('H'):
            hijri_string = data[1:]  # Remove 'H' prefix
            gregorian_dt = convert_hijri_string_to_gregorian(hijri_string)
            if gregorian_dt is None:
                raise serializers.ValidationError("Invalid Hijri date string format")
            return gregorian_dt
        
        # Otherwise, treat as Gregorian and use parent class parsing
        return super().to_internal_value(data)


class OptionsField(serializers.CharField):
    """Custom field to handle options as JSON string in DB but list in API"""
    
    def to_representation(self, value):
        """Convert stored JSON string to list for API response"""
        if not value:
            return []
        
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse options: {value}")
                return []
        elif isinstance(value, list):
            return value
        
        return []
    
    def to_internal_value(self, data):
        """Convert list from API to JSON string for DB storage"""
        if data is None:
            return ""
        
        if isinstance(data, list):
            return json.dumps(data)
        elif isinstance(data, str):
            # Validate it's proper JSON
            try:
                parsed = json.loads(data)
                if isinstance(parsed, list):
                    return data
                else:
                    raise serializers.ValidationError("Options must be a list")
            except json.JSONDecodeError:
                raise serializers.ValidationError("Options must be valid JSON")
        
        raise serializers.ValidationError("Options must be a list")


class QuestionSerializer(serializers.ModelSerializer):
    """Serializer for survey questions with encrypted fields and analytics metadata"""
    
    options = OptionsField(allow_blank=True, required=False)
    
    # Read field for getting satisfaction values
    options_satisfaction_values = serializers.SerializerMethodField()
    
    # Write field for setting satisfaction values during create/update
    set_satisfaction_values = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=2),
        required=False,
        allow_null=True,
        help_text="List of satisfaction values (0=Dissatisfied, 1=Neutral, 2=Satisfied) for each option in order"
    )
    
    class Meta:
        model = Question
        fields = [
            'id', 'survey', 'text', 'question_type', 'options', 
            'is_required', 'order', 'validation_type',
            'NPS_Calculate', 'CSAT_Calculate', 'min_scale', 'max_scale', 'semantic_tag',
            'options_satisfaction_values', 'set_satisfaction_values',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'survey': {'required': False}  # Survey is set automatically when creating through SurveySerializer
        }
    
    def to_representation(self, instance):
        """Exclude set_satisfaction_values from output"""
        ret = super().to_representation(instance)
        ret.pop('set_satisfaction_values', None)
        return ret
    
    def get_options_satisfaction_values(self, obj):
        """
        Return satisfaction values for each option when CSAT_Calculate is True.
        Returns a list of integers matching the order of options.
        """
        # Only return satisfaction values if CSAT_Calculate is enabled
        if not obj.CSAT_Calculate:
            return None
        
        # Only applicable for single_choice and yes_no questions
        if obj.question_type not in ['single_choice', 'yes_no', 'اختيار واحد', 'نعم/لا']:
            return None
        
        # Get satisfaction values from QuestionOption model ordered by 'order' field
        from .models import QuestionOption
        
        option_objs = QuestionOption.objects.filter(question=obj).order_by('order')
        
        if not option_objs.exists():
            return None
        
        # Return satisfaction values in order
        satisfaction_values = [opt.satisfaction_value for opt in option_objs]
        
        return satisfaction_values
    
    def to_internal_value(self, data):
        """Handle set_satisfaction_values and options_satisfaction_values, converting from JSON strings if needed"""
        # Handle set_satisfaction_values
        if 'set_satisfaction_values' in data:
            value = data['set_satisfaction_values']
            if isinstance(value, str):
                try:
                    data['set_satisfaction_values'] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
            # Store for use in create/update
            data['options_satisfaction_values'] = data.get('set_satisfaction_values')
        
        # Handle options_satisfaction_values - convert from JSON string to list if needed
        if 'options_satisfaction_values' in data:
            value = data['options_satisfaction_values']
            if isinstance(value, str):
                try:
                    data['options_satisfaction_values'] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # If JSON parsing fails, leave as-is and let validation handle the error
                    pass
        
        return super().to_internal_value(data)
    
    def validate_text(self, value):
        """Validate and sanitize question text."""
        return validate_and_sanitize_text_input(value, max_length=500, field_name="Question text")
    
    def validate(self, data):
        """Cross-field validation for questions"""
        question_type = data.get('question_type')
        options = data.get('options')
        csat_calculate = data.get('CSAT_Calculate', False)
        nps_calculate = data.get('NPS_Calculate', False)
        options_satisfaction_values = data.get('options_satisfaction_values')
        
        # Validate NPS_Calculate flag
        if nps_calculate and question_type not in ['rating', 'تقييم']:
            raise serializers.ValidationError({
                'NPS_Calculate': 'NPS_Calculate can only be True for rating questions.'
            })
        
        # Validate CSAT_Calculate flag
        valid_csat_types = ['single_choice', 'rating', 'yes_no', 'اختيار واحد', 'تقييم', 'نعم/لا']
        if csat_calculate and question_type not in valid_csat_types:
            raise serializers.ValidationError({
                'CSAT_Calculate': 'CSAT_Calculate can only be True for single_choice, rating, or yes_no questions.'
            })
        
        # Validate options for choice questions
        if question_type in ['single_choice', 'multiple_choice', 'اختيار واحد', 'اختيار متعدد']:
            if not options:
                raise serializers.ValidationError(
                    "Choice questions must have options"
                )
            
            try:
                # At this point, options should be a JSON string from our custom field
                options_list = json.loads(options) if isinstance(options, str) else options
                
                if not isinstance(options_list, list) or len(options_list) < 2:
                    raise serializers.ValidationError(
                        "Choice questions must have at least 2 options"
                    )
                
                # Validate options_satisfaction_values if CSAT_Calculate is True
                if csat_calculate and options_satisfaction_values:
                    if len(options_satisfaction_values) != len(options_list):
                        raise serializers.ValidationError({
                            'options_satisfaction_values': f'Must provide satisfaction value for each option ({len(options_list)} options, {len(options_satisfaction_values)} values)'
                        })
                
                # Sanitize each option
                sanitized_options = []
                for option in options_list:
                    if isinstance(option, str):
                        sanitized_option = validate_and_sanitize_text_input(
                            option, max_length=200, field_name="Option"
                        )
                        sanitized_options.append(sanitized_option)
                    else:
                        sanitized_options.append(option)
                
                # Update the options with sanitized values
                data['options'] = json.dumps(sanitized_options) if sanitized_options else data.get('options')
                    
            except (json.JSONDecodeError, TypeError):
                raise serializers.ValidationError("Options must be valid JSON array")
        
        # Validate yes/no questions with CSAT_Calculate
        if question_type in ['yes_no', 'نعم/لا'] and csat_calculate:
            if options_satisfaction_values:
                if len(options_satisfaction_values) != 2:
                    raise serializers.ValidationError({
                        'options_satisfaction_values': 'Yes/No questions require exactly 2 satisfaction values [yes_value, no_value]'
                    })
        
        return data
    
    def create(self, validated_data):
        """Create question and QuestionOption records for satisfaction values"""
        from .models import QuestionOption
        import hashlib
        
        # Extract set_satisfaction_values and options_satisfaction_values before creating the question
        satisfaction_values = validated_data.pop('set_satisfaction_values', None) or validated_data.pop('options_satisfaction_values', None)
        
        # Create the question
        question = Question.objects.create(**validated_data)
        
        # Create QuestionOption records if satisfaction values provided
        if satisfaction_values and question.CSAT_Calculate:
            try:
                # Parse options
                options_list = json.loads(question.options) if isinstance(question.options, str) else question.options
                
                if options_list and len(satisfaction_values) == len(options_list):
                    for idx, (option_text, sat_value) in enumerate(zip(options_list, satisfaction_values)):
                        QuestionOption.objects.create(
                            question=question,
                            option_text=str(option_text),
                            satisfaction_value=sat_value,
                            order=idx
                        )
            except Exception as e:
                logger.error(f"Error creating QuestionOption records: {e}")
        
        return question
    
    def update(self, instance, validated_data):
        """Update question and QuestionOption records for satisfaction values"""
        from .models import QuestionOption
        import hashlib
        
        # Extract set_satisfaction_values and options_satisfaction_values before updating
        satisfaction_values = validated_data.pop('set_satisfaction_values', None) or validated_data.pop('options_satisfaction_values', None)
        
        # Update the question fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update QuestionOption records if satisfaction values provided
        if satisfaction_values and instance.CSAT_Calculate:
            # Delete existing QuestionOption records for this question
            QuestionOption.objects.filter(question=instance).delete()
            
            try:
                # Parse options
                options_list = json.loads(instance.options) if isinstance(instance.options, str) else instance.options
                
                if options_list and len(satisfaction_values) == len(options_list):
                    for idx, (option_text, sat_value) in enumerate(zip(options_list, satisfaction_values)):
                        QuestionOption.objects.create(
                            question=instance,
                            option_text=str(option_text),
                            satisfaction_value=sat_value,
                            order=idx
                        )
            except Exception as e:
                logger.error(f"Error updating QuestionOption records: {e}")
        
        return instance


class AnswerSerializer(serializers.ModelSerializer):
    """Serializer for survey answers with input sanitization"""
    
    class Meta:
        model = Answer
        fields = ['id', 'question', 'answer_text', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate_answer_text(self, value):
        """Validate and sanitize answer text."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=2000, field_name="Answer")


class ResponseSerializer(serializers.ModelSerializer):
    """Serializer for survey responses with nested answers and UAE timezone"""
    
    answers = AnswerSerializer(many=True, read_only=True)
    respondent_email = serializers.SerializerMethodField()
    
    # Use UAE timezone for datetime fields
    submitted_at = UAEDateTimeField(read_only=True)
    created_at = UAEDateTimeField(read_only=True)
    updated_at = UAEDateTimeField(read_only=True)
    
    class Meta:
        model = Response
        fields = [
            'id', 'survey', 'respondent', 'respondent_email',
            'submitted_at', 'is_complete', 'answers'
        ]
        read_only_fields = ['id', 'submitted_at', 'respondent_email']
    
    def get_respondent_email(self, obj):
        """Get respondent email - either from user, stored email field, or phone"""
        if obj.respondent:
            return obj.respondent.email
        elif obj.respondent_phone:
            return obj.respondent_phone
        elif obj.respondent_email:
            return obj.respondent_email
        else:
            return "Anonymous"


class SurveySerializer(serializers.ModelSerializer):
    """
    Main survey serializer with role-based field filtering and UAE timezone handling.
    Follows the same patterns as authentication serializers.
    """
    
    questions = QuestionSerializer(many=True, required=False)
    creator_email = serializers.SerializerMethodField()
    response_count = serializers.SerializerMethodField()
    shared_with_emails = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    is_currently_active = serializers.SerializerMethodField()
    can_be_edited = serializers.SerializerMethodField()
    
    # Use custom UAE timezone fields for date/time serialization
    start_date = UAEDateTimeField(required=False, allow_null=True)
    end_date = UAEDateTimeField(required=False, allow_null=True)
    created_at = UAEDateTimeField(read_only=True)
    updated_at = UAEDateTimeField(read_only=True)
    
    class Meta:
        model = Survey
        fields = [
            'id', 'title', 'description', 'visibility', 'shared_with',
            'creator', 'creator_email', 'is_locked', 'is_active',
            'start_date', 'end_date', 'status', 'status_display', 'is_currently_active',
            'can_be_edited', 'public_contact_method', 'per_device_access', 'questions', 'response_count', 
            'shared_with_emails', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'creator', 'created_at', 'updated_at', 'status_display', 'is_currently_active', 'can_be_edited']
    
    def get_creator_email(self, obj):
        """Get creator email"""
        return obj.creator.email if obj.creator else None
    
    def get_response_count(self, obj):
        """Get total response count"""
        return obj.responses.count()
    
    def get_shared_with_emails(self, obj):
        """Get emails of users survey is shared with"""
        return [user.email for user in obj.shared_with.all()]
    
    def get_status_display(self, obj):
        """Get current status of the survey using UAE timezone"""
        return get_status_uae(obj)
    
    def get_is_currently_active(self, obj):
        """Check if survey is currently active based on dates using UAE timezone"""
        return is_currently_active_uae(obj)
    
    def get_can_be_edited(self, obj):
        """Check if survey can be edited (only drafts can be edited)"""
        return obj.can_be_edited()
    
    def validate_title(self, value):
        """Validate and sanitize survey title."""
        return validate_and_sanitize_text_input(value, max_length=255, field_name="Survey title")
    
    def validate_description(self, value):
        """Validate and sanitize survey description."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description")
    
    def validate_public_contact_method(self, value):
        """Validate and sanitize public contact method."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=255, field_name="Contact method")
    
    def validate(self, data):
        """Validate survey data including date logic"""
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # If both dates are provided, ensure start_date is before end_date
        if start_date and end_date and start_date >= end_date:
            raise serializers.ValidationError(
                "Start date must be before end date."
            )
        
        return data
    
    def to_representation(self, instance):
        """Role-based field filtering following established patterns"""
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        if not request or not request.user:
            # Anonymous users - minimal data for public surveys only
            if instance.visibility == 'PUBLIC':
                return {
                    'id': data['id'],
                    'title': data['title'],
                    'description': data['description'],
                    'visibility': data['visibility'],
                    'status': data['status'],
                    'status_display': data.get('status_display'),
                    'is_active': data['is_active'],
                    'questions': data['questions'],
                    'response_count': data['response_count'],
                    'creator_email': data['creator_email'],
                    'created_at': data['created_at']
                }
            return {}
        
        user = request.user
        
        # Handle orphaned surveys (creator is None) - super admins can manage them
        if instance.creator is None:
            if user.role == 'super_admin':
                return data  # Super admins see all fields for orphaned surveys
            elif user.role in ['admin', 'manager']:
                # Admins see limited fields for orphaned surveys
                return {
                    'id': data['id'],
                    'title': data['title'],
                    'description': data['description'],
                    'visibility': data['visibility'],
                    'status': data['status'],
                    'status_display': data.get('status_display'),
                    'is_active': data['is_active'],
                    'questions': data['questions'],
                    'response_count': data['response_count'],
                    'creator_email': data['creator_email'],
                    'created_at': data['created_at']
                }
            else:
                # Regular users see minimal fields for orphaned public surveys
                if instance.visibility == 'PUBLIC':
                    return {
                        'id': data['id'],
                        'title': data['title'],
                        'description': data['description'],
                        'visibility': data['visibility'],
                        'status': data['status'],
                        'status_display': data.get('status_display'),
                        'is_active': data['is_active'],
                        'questions': data['questions'],
                        'response_count': data['response_count'],
                        'creator_email': data['creator_email'],
                        'created_at': data['created_at']
                    }
                return {}
        
        # Creators see everything
        if user == instance.creator:
            return data
        
        # Admin/Manager users see most fields
        if user.role in ['admin', 'manager']:
            return data
        
        # Regular users see limited fields
        if instance.visibility in ['AUTH', 'PUBLIC'] or user in instance.shared_with.all():
            return {
                'id': data['id'],
                'title': data['title'],
                'description': data['description'],
                'visibility': data['visibility'],
                'status': data['status'],
                'status_display': data.get('status_display'),
                'is_active': data['is_active'],
                'questions': data['questions'],
                'response_count': data['response_count'],
                'creator_email': data['creator_email'],
                'created_at': data['created_at']
            }
        
        return {}
    
    def to_internal_value(self, data):
        """Ensure per_device_access always has a value and preserve satisfaction values in nested questions"""
        # Ensure per_device_access is never None and defaults to False
        if 'per_device_access' not in data:
            data['per_device_access'] = False
        elif data.get('per_device_access') is None:
            data['per_device_access'] = False
        
        # Preserve and convert options_satisfaction_values in nested questions data
        # Convert from JSON string to list if needed
        if 'questions' in data and isinstance(data['questions'], list):
            for question_data in data['questions']:
                if 'options_satisfaction_values' in question_data:
                    value = question_data['options_satisfaction_values']
                    # Convert from JSON string to list if needed
                    if isinstance(value, str):
                        try:
                            question_data['options_satisfaction_values'] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    # Store it temporarily to preserve through validation
                    question_data['_temp_satisfaction_values'] = question_data['options_satisfaction_values']
        
        result = super().to_internal_value(data)
        
        # Restore satisfaction values after validation
        if 'questions' in result:
            questions_list = result['questions']
            if 'questions' in data and isinstance(data['questions'], list):
                for idx, question_data in enumerate(data['questions']):
                    if '_temp_satisfaction_values' in question_data and idx < len(questions_list):
                        questions_list[idx]['options_satisfaction_values'] = question_data['_temp_satisfaction_values']
        
        return result
    
    def validate(self, data):
        """Enhanced validation with security checks"""
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required")
        
        # Check if survey is locked for updates
        if self.instance and self.instance.is_locked:
            raise serializers.ValidationError("Cannot modify locked survey")
        
        # Validate visibility and shared_with relationship
        visibility = data.get('visibility', 'PRIVATE')
        shared_with = data.get('shared_with', [])
        
        if visibility != 'PRIVATE' and shared_with:
            raise serializers.ValidationError(
                "Cannot share survey when visibility is not PRIVATE"
            )
        
        # Validate per_device_access - only available for PUBLIC surveys
        per_device_access = data.get('per_device_access', False)
        if per_device_access and visibility != 'PUBLIC':
            raise serializers.ValidationError(
                "Per-device access is only available for PUBLIC surveys"
            )
        
        # Validate date logic
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # If both dates are provided, ensure start_date is before end_date
        if start_date and end_date and start_date >= end_date:
            raise serializers.ValidationError(
                "Start date must be before end date."
            )
        
        return data
    
    def create(self, validated_data):
        """Create survey with creator set to current user and handle nested questions"""
        from .models import QuestionOption
        import hashlib
        
        request = self.context.get('request')
        validated_data['creator'] = request.user
        
        # Ensure per_device_access is never None
        if 'per_device_access' not in validated_data:
            validated_data['per_device_access'] = False
        elif validated_data['per_device_access'] is None:
            validated_data['per_device_access'] = False
            
        # Debug: Log the validated data in serializer create
        logger.info(f"Serializer create - per_device_access: {validated_data.get('per_device_access')}")
        logger.info(f"Serializer create - all validated_data keys: {list(validated_data.keys())}")
        
        # Extract questions data before creating survey
        questions_data = validated_data.pop('questions', [])
        
        # Handle shared_with separately
        shared_with = validated_data.pop('shared_with', [])
        
        # Debug: Log data just before Survey.objects.create
        logger.info(f"About to create survey with data: {validated_data}")
        survey = Survey.objects.create(**validated_data)
        
        if validated_data.get('visibility') == 'PRIVATE':
            survey.shared_with.set(shared_with)
        
        # Create questions if provided
        for question_data in questions_data:
            # Extract satisfaction values before creating question
            # Check both field names since they might come from different sources
            options_satisfaction_values = question_data.pop('options_satisfaction_values', None) or question_data.pop('set_satisfaction_values', None)
            
            question = Question.objects.create(survey=survey, **question_data)
            
            # Create QuestionOption records if satisfaction values provided
            if options_satisfaction_values and question.CSAT_Calculate:
                question_type = question.question_type
                
                if question_type in ['single_choice', 'اختيار واحد']:
                    # Parse options JSON
                    options_list = json.loads(question.options) if isinstance(question.options, str) else question.options
                    
                    for idx, option_text in enumerate(options_list):
                        if idx < len(options_satisfaction_values):
                            QuestionOption.objects.create(
                                question=question,
                                option_text=option_text,
                                satisfaction_value=options_satisfaction_values[idx],
                                order=idx
                            )
                
                elif question_type in ['yes_no', 'نعم/لا']:
                    # For yes/no questions, use options from the question if provided,
                    # otherwise use default yes/no options
                    if question.options:
                        try:
                            options_list = json.loads(question.options) if isinstance(question.options, str) else question.options
                        except (json.JSONDecodeError, TypeError):
                            # If parsing fails, use default yes/no options
                            options_list = ["yes", "no"]
                    else:
                        # Default yes/no options
                        options_list = ["yes", "no"]
                    
                    # Create option records for each yes/no option
                    for idx, option_text in enumerate(options_list):
                        if idx < len(options_satisfaction_values):
                            QuestionOption.objects.create(
                                question=question,
                                option_text=option_text,
                                satisfaction_value=options_satisfaction_values[idx],
                                order=idx
                            )
        
        logger.info(f"Survey created: {survey.id} with {len(questions_data)} questions by {request.user.email}")
        return survey
    
    def update(self, instance, validated_data):
        """Update survey and handle nested questions"""
        from .models import QuestionOption
        import hashlib
        
        # Ensure per_device_access is never None
        if 'per_device_access' in validated_data and validated_data['per_device_access'] is None:
            validated_data['per_device_access'] = False
        
        # Extract questions data before updating survey
        questions_data = validated_data.pop('questions', None)
        
        # Handle shared_with separately
        shared_with = validated_data.pop('shared_with', None)
        
        # Update survey fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Handle shared_with if provided
        if shared_with is not None:
            if instance.visibility == 'PRIVATE':
                instance.shared_with.set(shared_with)
            else:
                instance.shared_with.clear()
        
        # Handle questions if provided
        if questions_data is not None:
            # Delete existing questions (cascade will delete QuestionOption records)
            instance.questions.all().delete()
            
            # Create new questions
            for question_data in questions_data:
                # Extract satisfaction values before creating question
                options_satisfaction_values = question_data.pop('options_satisfaction_values', None)
                
                question = Question.objects.create(survey=instance, **question_data)
                
                # Create QuestionOption records if satisfaction values provided
                if options_satisfaction_values and question.CSAT_Calculate:
                    question_type = question.question_type
                    
                    if question_type in ['single_choice', 'اختيار واحد']:
                        # Parse options JSON
                        options_list = json.loads(question.options) if isinstance(question.options, str) else question.options
                        
                        for idx, option_text in enumerate(options_list):
                            if idx < len(options_satisfaction_values):
                                QuestionOption.objects.create(
                                    question=question,
                                    option_text=option_text,
                                    satisfaction_value=options_satisfaction_values[idx],
                                    order=idx
                                )
                    
                    elif question_type in ['yes_no', 'نعم/لا']:
                        # For yes/no questions, use options from the question if provided,
                        # otherwise use default yes/no options
                        if question.options:
                            try:
                                options_list = json.loads(question.options) if isinstance(question.options, str) else question.options
                            except (json.JSONDecodeError, TypeError):
                                # If parsing fails, use default yes/no options
                                options_list = ["yes", "no"]
                        else:
                            # Default yes/no options
                            options_list = ["yes", "no"]
                        
                        # Create option records for each yes/no option
                        for idx, option_text in enumerate(options_list):
                            if idx < len(options_satisfaction_values):
                                QuestionOption.objects.create(
                                    question=question,
                                    option_text=option_text,
                                    satisfaction_value=options_satisfaction_values[idx],
                                    order=idx
                                )
        
        logger.info(f"Survey updated: {instance.id} with {len(questions_data) if questions_data else 0} questions")
        return instance


class SurveySubmissionSerializer(serializers.Serializer):
    """Serializer for survey response submission"""
    
    answers = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False
    )
    
    def validate_answers(self, value):
        """Validate submitted answers with per-question-type validation"""
        if not value:
            raise serializers.ValidationError("At least one answer is required")
        
        for answer in value:
            if 'question_id' not in answer or 'answer_text' not in answer:
                raise serializers.ValidationError(
                    "Each answer must have question_id and answer_text"
                )
            
            # Get question for validation (this will be checked again in the view)
            question_id = answer.get('question_id')
            answer_text = answer.get('answer_text')
            
            # Basic validation - detailed validation happens in the view with DB access
            if not question_id or not answer_text:
                raise serializers.ValidationError(
                    "Question ID and answer text are required"
                )
        
        return value


class ResponseSubmissionSerializer(serializers.Serializer):
    """
    Enhanced serializer for the new survey response submission endpoint.
    Supports different access levels and validation.
    """
    
    survey_id = serializers.UUIDField(required=True)
    token = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    answers = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False
    )
    
    def validate_answers(self, value):
        """Validate submitted answers"""
        if not value:
            raise serializers.ValidationError("At least one answer is required")
        
        for answer in value:
            if 'question_id' not in answer or 'answer' not in answer:
                raise serializers.ValidationError(
                    "Each answer must have question_id and answer"
                )
            
            question_id = answer.get('question_id')
            answer_text = answer.get('answer')
            
            if not question_id or not answer_text:
                raise serializers.ValidationError(
                    "Question ID and answer are required"
                )
        
        return value
    
    def validate(self, data):
        """Cross-field validation based on survey access requirements"""
        survey_id = data.get('survey_id')
        token = data.get('token')
        email = data.get('email')
        phone = data.get('phone')
        
        if not survey_id:
            raise serializers.ValidationError("Survey ID is required")
        
        # Basic validation to ensure email and phone are not both provided
        if email and phone:
            raise serializers.ValidationError("Please provide either email or phone, not both")
        
        # We'll validate survey access and required contact method in the view 
        # since we need database access to check survey settings
        
        return data


class TemplateQuestionSerializer(serializers.ModelSerializer):
    """Serializer for template questions with encrypted fields"""
    
    class Meta:
        model = TemplateQuestion
        fields = [
            'id', 'text', 'text_ar', 'question_type', 'options',
            'is_required', 'order', 'placeholder', 'placeholder_ar',
            'NPS_Calculate', 'CSAT_Calculate', 'min_scale', 'max_scale'
        ]
        read_only_fields = ['id']
    
    def validate_text(self, value):
        """Validate and sanitize question text."""
        return validate_and_sanitize_text_input(value, max_length=500, field_name="Question text")
    
    def validate_text_ar(self, value):
        """Validate and sanitize Arabic question text."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=500, field_name="Question text (Arabic)")
    
    def validate(self, data):
        """Cross-field validation for template questions"""
        question_type = data.get('question_type')
        options = data.get('options')
        
        # Validate options for choice questions
        if question_type in ['single_choice', 'multiple_choice']:
            if not options:
                raise serializers.ValidationError(
                    "Choice questions must have options"
                )
            
            if not isinstance(options, list) or len(options) < 2:
                raise serializers.ValidationError(
                    "Choice questions must have at least 2 options"
                )
        
        return data


class SurveyTemplateSerializer(serializers.ModelSerializer):
    """Serializer for survey templates with encrypted fields"""
    
    questions = TemplateQuestionSerializer(many=True, read_only=True)
    created_by_email = serializers.SerializerMethodField()
    
    # Use UAE timezone for datetime fields
    created_at = UAEDateTimeField(read_only=True)
    updated_at = UAEDateTimeField(read_only=True)
    
    class Meta:
        model = SurveyTemplate
        fields = [
            'id', 'name', 'name_ar', 'description', 'description_ar',
            'category', 'icon', 'preview_image', 'is_predefined',
            'usage_count', 'created_by', 'created_by_email',
            'created_at', 'updated_at', 'questions'
        ]
        read_only_fields = ['id', 'usage_count', 'created_by', 'created_at', 'updated_at']
    
    def get_created_by_email(self, obj):
        """Get creator email"""
        return obj.created_by.email if obj.created_by else None
    
    def validate_name(self, value):
        """Validate and sanitize template name."""
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Template name")
    
    def validate_name_ar(self, value):
        """Validate and sanitize Arabic template name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Template name (Arabic)")
    
    def validate_description(self, value):
        """Validate and sanitize template description."""
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description")
    
    def validate_description_ar(self, value):
        """Validate and sanitize Arabic template description."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description (Arabic)")


class CreateTemplateSerializer(serializers.Serializer):
    """Serializer for creating a template from a survey"""
    
    name = serializers.CharField(max_length=200, required=True)
    name_ar = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(max_length=1000, required=True)
    description_ar = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    category = serializers.ChoiceField(
        choices=['contact', 'event', 'feedback', 'registration', 'custom'],
        required=True
    )
    survey_id = serializers.UUIDField(required=True)
    
    def validate_name(self, value):
        """Validate and sanitize template name."""
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Template name")
    
    def validate_name_ar(self, value):
        """Validate and sanitize Arabic template name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Template name (Arabic)")
    
    def validate_description(self, value):
        """Validate and sanitize template description."""
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description")
    
    def validate_description_ar(self, value):
        """Validate and sanitize Arabic template description."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description (Arabic)")


class CreateSurveyFromTemplateSerializer(serializers.Serializer):
    """Serializer for creating a survey from a template"""
    
    template_id = serializers.UUIDField(required=True)
    title = serializers.CharField(max_length=200, required=True)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    visibility = serializers.ChoiceField(
        choices=['PUBLIC', 'PRIVATE', 'AUTH', 'GROUPS'],
        default='PRIVATE'
    )
    
    def validate_title(self, value):
        """Validate and sanitize survey title."""
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Survey title")
    
    def validate_description(self, value):
        """Validate and sanitize survey description."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Survey description")


class CreatePredefinedTemplateSerializer(serializers.Serializer):
    """Serializer for creating predefined templates with questions (similar to draft endpoint)"""
    
    name = serializers.CharField(max_length=200, required=True)
    name_ar = serializers.CharField(max_length=200, required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(max_length=1000, required=True)
    description_ar = serializers.CharField(max_length=1000, required=False, allow_blank=True, allow_null=True)
    category = serializers.ChoiceField(
        choices=['contact', 'event', 'feedback', 'registration', 'custom'],
        required=True
    )
    icon = serializers.CharField(max_length=50, default='fa-star')
    preview_image = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    is_predefined = serializers.BooleanField(default=True)
    questions = TemplateQuestionSerializer(many=True, required=False)
    
    def validate_name(self, value):
        """Validate and sanitize template name."""
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Template name")
    
    def validate_name_ar(self, value):
        """Validate and sanitize Arabic template name."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=200, field_name="Template name (Arabic)")
    
    def validate_description(self, value):
        """Validate and sanitize template description."""
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description")
    
    def validate_description_ar(self, value):
        """Validate and sanitize Arabic template description."""
        if not value:
            return value
        return validate_and_sanitize_text_input(value, max_length=1000, field_name="Description (Arabic)")


class RecentSurveySerializer(serializers.ModelSerializer):
    """Serializer for recent surveys with minimal fields"""
    
    questions_count = serializers.SerializerMethodField()
    response_count = serializers.SerializerMethodField()
    can_use_as_template = serializers.SerializerMethodField()
    
    # Use UAE timezone for datetime fields
    created_at = UAEDateTimeField(read_only=True)
    updated_at = UAEDateTimeField(read_only=True)
    
    class Meta:
        model = Survey
        fields = [
            'id', 'title', 'description', 'created_at', 'updated_at',
            'questions_count', 'response_count', 'visibility', 'status',
            'can_use_as_template'
        ]
        read_only_fields = fields
    
    def get_questions_count(self, obj):
        """Get total questions count"""
        return obj.questions.count()
    
    def get_response_count(self, obj):
        """Get total response count"""
        return obj.responses.count()
    
    def get_can_use_as_template(self, obj):
        """Check if survey can be used as template"""
        # Only draft or submitted surveys can be used as templates
        return obj.status in ['draft', 'submitted']
