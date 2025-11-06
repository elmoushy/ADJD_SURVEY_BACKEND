"""
DRF Serializers for Email Communication System
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    CostCenter,
    CostCenterEmail,
    EmailTemplate,
    EmailDraft,
    EmailLog,
    EmailRecipientView
)

User = get_user_model()


class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal user info for nested serialization"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']


class CostCenterEmailSerializer(serializers.ModelSerializer):
    """Serializer for cost center emails"""
    class Meta:
        model = CostCenterEmail
        fields = ['id', 'email', 'email_type', 'display_name', 'is_active']
        

class CostCenterListSerializer(serializers.ModelSerializer):
    """List serializer for cost centers"""
    email_count = serializers.SerializerMethodField()
    recipient_count = serializers.SerializerMethodField()
    cc_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CostCenter
        fields = [
            'id',
            'cost_center_code',
            'cost_center_name',
            'cost_center_name_ar',
            'is_active',
            'email_count',
            'recipient_count',
            'cc_count',
            'created_at'
        ]
    
    def get_email_count(self, obj):
        return obj.emails.count()
    
    def get_recipient_count(self, obj):
        return obj.emails.filter(email_type='recipient').count()
    
    def get_cc_count(self, obj):
        return obj.emails.filter(email_type='cc').count()


class CostCenterDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for cost centers with emails"""
    emails = CostCenterEmailSerializer(many=True, read_only=True)
    recipient_emails = serializers.ListField(
        child=serializers.EmailField(),
        write_only=True,
        required=False,
        help_text="List of recipient emails (TO field)"
    )
    cc_emails = serializers.ListField(
        child=serializers.EmailField(),
        write_only=True,
        required=False,
        help_text="List of CC emails"
    )
    created_by = UserMinimalSerializer(read_only=True)
    
    # Read-only convenience fields for frontend
    recipients = serializers.SerializerMethodField()
    ccs = serializers.SerializerMethodField()
    
    class Meta:
        model = CostCenter
        fields = [
            'id',
            'cost_center_code',
            'cost_center_name',
            'cost_center_name_ar',
            'description',
            'description_ar',
            'is_active',
            'emails',
            'recipient_emails',
            'cc_emails',
            'recipients',
            'ccs',
            'created_by',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_recipients(self, obj):
        """Get list of recipient email addresses"""
        return obj.get_recipient_emails()
    
    def get_ccs(self, obj):
        """Get list of CC email addresses"""
        return obj.get_cc_emails()
    
    def create(self, validated_data):
        recipient_emails = validated_data.pop('recipient_emails', [])
        cc_emails = validated_data.pop('cc_emails', [])
        validated_data['created_by'] = self.context['request'].user
        
        cost_center = CostCenter.objects.create(**validated_data)
        
        # Create recipient emails
        for email in recipient_emails:
            CostCenterEmail.objects.create(
                cost_center=cost_center,
                email=email.strip().lower(),
                email_type='recipient'
            )
        
        # Create CC emails
        for email in cc_emails:
            CostCenterEmail.objects.create(
                cost_center=cost_center,
                email=email.strip().lower(),
                email_type='cc'
            )
        
        return cost_center
    
    def update(self, instance, validated_data):
        recipient_emails = validated_data.pop('recipient_emails', None)
        cc_emails = validated_data.pop('cc_emails', None)
        
        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update recipient emails if provided
        if recipient_emails is not None:
            # Remove old recipient emails
            instance.emails.filter(email_type='recipient').delete()
            # Create new recipient emails
            for email in recipient_emails:
                CostCenterEmail.objects.create(
                    cost_center=instance,
                    email=email.strip().lower(),
                    email_type='recipient'
                )
        
        # Update CC emails if provided
        if cc_emails is not None:
            # Remove old CC emails
            instance.emails.filter(email_type='cc').delete()
            # Create new CC emails
            for email in cc_emails:
                CostCenterEmail.objects.create(
                    cost_center=instance,
                    email=email.strip().lower(),
                    email_type='cc'
                )
        
        return instance


class EmailTemplateListSerializer(serializers.ModelSerializer):
    """List serializer for email templates"""
    created_by = UserMinimalSerializer(read_only=True)
    
    class Meta:
        model = EmailTemplate
        fields = [
            'id',
            'name',
            'name_ar',
            'category',
            'is_active',
            'created_by',
            'created_at',
            'updated_at'
        ]


class EmailTemplateDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for email templates"""
    created_by = UserMinimalSerializer(read_only=True)
    
    class Meta:
        model = EmailTemplate
        fields = [
            'id',
            'name',
            'name_ar',
            'subject',
            'subject_ar',
            'body_html',
            'body_html_ar',
            'body_text',
            'is_active',
            'category',
            'created_by',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return EmailTemplate.objects.create(**validated_data)


class EmailDraftListSerializer(serializers.ModelSerializer):
    """List serializer for email drafts"""
    class Meta:
        model = EmailDraft
        fields = [
            'id',
            'send_type',
            'subject',
            'draft_name',
            'template',
            'created_at',
            'updated_at'
        ]


class EmailDraftDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for email drafts"""
    template = EmailTemplateListSerializer(read_only=True)
    template_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    cost_center_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True
    )
    
    class Meta:
        model = EmailDraft
        fields = [
            'id',
            'send_type',
            'subject',
            'body_html',
            'cost_center_ids',
            'draft_name',
            'template',
            'template_id',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def create(self, validated_data):
        cost_center_ids = validated_data.pop('cost_center_ids', None)
        template_id = validated_data.pop('template_id', None)
        
        validated_data['user'] = self.context['request'].user
        if template_id:
            try:
                validated_data['template'] = EmailTemplate.objects.get(id=template_id)
            except EmailTemplate.DoesNotExist:
                pass
        
        draft = EmailDraft.objects.create(**validated_data)
        if cost_center_ids:
            draft.set_cost_center_list(cost_center_ids)
            draft.save()
        
        return draft
    
    def update(self, instance, validated_data):
        cost_center_ids = validated_data.pop('cost_center_ids', None)
        template_id = validated_data.pop('template_id', None)
        
        if template_id:
            try:
                instance.template = EmailTemplate.objects.get(id=template_id)
            except EmailTemplate.DoesNotExist:
                instance.template = None
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if cost_center_ids is not None:
            instance.set_cost_center_list(cost_center_ids)
        
        instance.save()
        return instance
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Convert cost_center_ids from string to list
        data['cost_center_ids'] = instance.get_cost_center_list()
        return data


class EmailLogListSerializer(serializers.ModelSerializer):
    """List serializer for email logs"""
    user = UserMinimalSerializer(read_only=True)
    cost_center = CostCenterListSerializer(read_only=True)
    recipient_count = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailLog
        fields = [
            'id',
            'user',
            'cost_center',
            'send_type',
            'email_type',
            'subject',
            'email_status',
            'recipient_count',
            'sent_at'
        ]
    
    def get_recipient_count(self, obj):
        return len(obj.get_recipient_list())


class EmailLogDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for email logs"""
    user = UserMinimalSerializer(read_only=True)
    cost_center = CostCenterListSerializer(read_only=True)
    template = EmailTemplateListSerializer(read_only=True)
    recipient_emails = serializers.SerializerMethodField()
    cc_emails = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailLog
        fields = [
            'id',
            'user',
            'cost_center',
            'template',
            'send_type',
            'email_type',
            'subject',
            'body_html',
            'recipient_emails',
            'cc_emails',
            'email_status',
            'email_error',
            'sent_at',
            'metadata'
        ]
    
    def get_recipient_emails(self, obj):
        return obj.get_recipient_list()
    
    def get_cc_emails(self, obj):
        return obj.get_cc_list()
    
    def get_metadata(self, obj):
        return obj.get_metadata()


class EmailRecipientViewListSerializer(serializers.ModelSerializer):
    """List serializer for inbox emails"""
    email = EmailLogListSerializer(source='email_log', read_only=True)
    sender = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailRecipientView
        fields = [
            'id',
            'email',
            'sender',
            'is_to',
            'is_read',
            'read_at',
            'is_starred',
            'is_archived'
        ]
    
    def get_sender(self, obj):
        if obj.email_log.user:
            return UserMinimalSerializer(obj.email_log.user).data
        return None


class EmailRecipientViewDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for inbox email"""
    email = EmailLogDetailSerializer(source='email_log', read_only=True)
    sender = serializers.SerializerMethodField()
    
    class Meta:
        model = EmailRecipientView
        fields = [
            'id',
            'email',
            'sender',
            'is_to',
            'is_read',
            'read_at',
            'is_starred',
            'is_archived'
        ]
    
    def get_sender(self, obj):
        if obj.email_log.user:
            return UserMinimalSerializer(obj.email_log.user).data
        return None


class SendEmailSerializer(serializers.Serializer):
    """Serializer for sending emails"""
    send_type = serializers.ChoiceField(choices=['ANNOUNCEMENT', 'SPECIFIC'])
    cost_center_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_null=True
    )
    template_id = serializers.IntegerField(required=False, allow_null=True)
    subject = serializers.CharField(max_length=500)
    body_html = serializers.CharField()
    
    def validate(self, data):
        if data['send_type'] == 'SPECIFIC' and not data.get('cost_center_ids'):
            raise serializers.ValidationError({
                'cost_center_ids': 'Required for SPECIFIC send type'
            })
        return data


class SendDraftSerializer(serializers.Serializer):
    """Serializer for sending from draft with optional overrides"""
    subject = serializers.CharField(max_length=500, required=False)
    body_html = serializers.CharField(required=False)
