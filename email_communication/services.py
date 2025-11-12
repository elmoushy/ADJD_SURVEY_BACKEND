"""
Email Service - Business logic for email communication system
Handles email sending, draft management, and recipient tracking
"""
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from typing import List, Dict, Optional
import logging

from .models import (
    CostCenter,
    EmailTemplate,
    EmailDraft,
    EmailLog,
    EmailRecipientView
)

User = get_user_model()
logger = logging.getLogger(__name__)


def wrap_html_with_rtl(body_html: str) -> str:
    """
    Wrap HTML content with RTL (Right-to-Left) formatting.
    This ensures proper display for Arabic content in email clients.
    
    Args:
        body_html: Original HTML content
        
    Returns:
        HTML wrapped with RTL directives and proper styling
    """
    # Check if content already has <html> tag
    if '<html' in body_html.lower():
        # Content already has HTML structure, just ensure it has proper attributes
        return body_html
    
    # Wrap content in full RTL HTML structure with dir="rtl" for Outlook
    rtl_html = f'''<html dir="rtl">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<style type="text/css">
body {{ direction: rtl; }}
</style>
</head>
<body text="#404040" lang="EN-US" link="blue" vlink="purple" style="word-wrap:break-word; direction:rtl;">
<div class="WordSection1" dir="rtl">
{body_html}
</div>
</body>
</html>'''
    
    return rtl_html


class EmailService:
    """
    Central service for email operations.
    Handles sending emails, creating logs, and tracking recipients.
    """
    
    @staticmethod
    def send_email(
        user,
        send_type: str,
        subject: str,
        body_html: str,
        cost_center_ids: Optional[List[int]] = None,
        template_id: Optional[int] = None,
        draft_id: Optional[int] = None
    ) -> Dict:
        """
        Send email to cost centers.
        
        Args:
            user: Sender user
            send_type: 'ANNOUNCEMENT' or 'SPECIFIC'
            subject: Email subject (user-edited)
            body_html: Email body HTML (user-edited)
            cost_center_ids: List of cost center IDs (for SPECIFIC)
            template_id: Template reference (optional)
            draft_id: Draft reference (optional)
            
        Returns:
            Dict with success status and details
        """
        try:
            with transaction.atomic():
                # Determine target cost centers
                if send_type == 'ANNOUNCEMENT':
                    cost_centers = CostCenter.objects.active()
                elif send_type == 'SPECIFIC':
                    if not cost_center_ids:
                        return {
                            'success': False,
                            'error': 'Cost center IDs required for SPECIFIC send type'
                        }
                    cost_centers = CostCenter.objects.filter(
                        id__in=cost_center_ids,
                        is_active=True
                    )
                else:
                    return {
                        'success': False,
                        'error': 'Invalid send type'
                    }
                
                if not cost_centers.exists():
                    return {
                        'success': False,
                        'error': 'No active cost centers found'
                    }
                
                # Get template and draft references
                template = None
                draft = None
                if template_id:
                    try:
                        template = EmailTemplate.objects.get(id=template_id)
                    except EmailTemplate.DoesNotExist:
                        pass
                
                if draft_id:
                    try:
                        draft = EmailDraft.objects.get(id=draft_id, user=user)
                    except EmailDraft.DoesNotExist:
                        pass
                
                # Send to each cost center
                results = []
                sent_log = None  # For sender's outbox
                
                for cost_center in cost_centers:
                    result = EmailService._send_to_cost_center(
                        user=user,
                        cost_center=cost_center,
                        send_type=send_type,
                        subject=subject,
                        body_html=body_html,
                        template=template,
                        draft=draft
                    )
                    results.append(result)
                    
                    # Create sender's outbox entry (once)
                    if sent_log is None:
                        sent_log = EmailService._create_sent_log(
                            user=user,
                            send_type=send_type,
                            subject=subject,
                            body_html=body_html,
                            cost_centers=list(cost_centers),
                            template=template,
                            draft=draft,
                            status='SUCCESS' if result['success'] else 'FAILED',
                            error=result.get('error')
                        )
                
                # Summary
                successful = sum(1 for r in results if r['success'])
                failed = len(results) - successful
                
                return {
                    'success': successful > 0,
                    'sent_count': successful,
                    'failed_count': failed,
                    'total_cost_centers': len(results),
                    'details': results,
                    'sent_log_id': sent_log.id if sent_log else None
                }
                
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def _send_to_cost_center(
        user,
        cost_center: CostCenter,
        send_type: str,
        subject: str,
        body_html: str,
        template: Optional[EmailTemplate] = None,
        draft: Optional[EmailDraft] = None
    ) -> Dict:
        """Send email to a single cost center and create logs"""
        try:
            # Get recipients
            to_emails = cost_center.get_recipient_emails()
            cc_emails = cost_center.get_cc_emails()
            
            if not to_emails:
                return {
                    'success': False,
                    'cost_center': cost_center.cost_center_code,
                    'error': 'No users in cost center'
                }
            
            # Send actual email
            email_sent = EmailService._send_actual_email(
                subject=subject,
                body_html=body_html,
                to_emails=to_emails,
                cc_emails=cc_emails,
                from_email=settings.DEFAULT_FROM_EMAIL
            )
            
            # Create received log (for recipients' inbox)
            received_log = EmailLog.objects.create(
                user=user,
                cost_center=cost_center,
                template=template,
                draft=draft,
                send_type=send_type,
                email_type='RECEIVED',
                subject=subject,
                body_html=body_html,
                recipient_emails=','.join(to_emails),
                cc_emails=','.join(cc_emails) if cc_emails else None,
                email_status='SUCCESS' if email_sent else 'FAILED',
                email_error=None if email_sent else 'Email sending failed'
            )
            
            # Create recipient tracking records
            if email_sent:
                EmailService._create_recipient_tracking(
                    email_log=received_log,
                    to_emails=to_emails,
                    cc_emails=cc_emails
                )
            
            return {
                'success': email_sent,
                'cost_center': cost_center.cost_center_code,
                'recipients_count': len(to_emails),
                'log_id': received_log.id
            }
            
        except Exception as e:
            logger.error(
                f"Error sending to cost center {cost_center.cost_center_code}: {str(e)}",
                exc_info=True
            )
            return {
                'success': False,
                'cost_center': cost_center.cost_center_code,
                'error': str(e)
            }
    
    @staticmethod
    def _send_actual_email(
        subject: str,
        body_html: str,
        to_emails: List[str],
        cc_emails: List[str],
        from_email: str
    ) -> bool:
        """
        Send actual email via Django email backend.
        Wraps content in RTL format before sending.
        Returns True if successful, False otherwise.
        """
        try:
            # Wrap HTML content with RTL formatting for proper Arabic display
            rtl_body_html = wrap_html_with_rtl(body_html)
            
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body_html,  # Plain text fallback (without RTL wrapper)
                from_email=from_email,
                to=to_emails,
                cc=cc_emails if cc_emails else None
            )
            msg.attach_alternative(rtl_body_html, "text/html")
            msg.send()
            return True
        except Exception as e:
            logger.error(f"Email sending failed: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def _create_sent_log(
        user,
        send_type: str,
        subject: str,
        body_html: str,
        cost_centers: List[CostCenter],
        template: Optional[EmailTemplate],
        draft: Optional[EmailDraft],
        status: str,
        error: Optional[str] = None
    ) -> EmailLog:
        """Create sender's outbox log entry"""
        # Aggregate all recipients
        all_to_emails = []
        all_cc_emails = []
        for cc in cost_centers:
            all_to_emails.extend(cc.get_recipient_emails())
            all_cc_emails.extend(cc.get_cc_emails())
        
        return EmailLog.objects.create(
            user=user,
            cost_center=None,  # Outbox doesn't link to specific cost center
            template=template,
            draft=draft,
            send_type=send_type,
            email_type='SENT',
            subject=subject,
            body_html=body_html,
            recipient_emails=','.join(all_to_emails),
            cc_emails=','.join(all_cc_emails) if all_cc_emails else None,
            email_status=status,
            email_error=error
        )
    
    @staticmethod
    def _create_recipient_tracking(
        email_log: EmailLog,
        to_emails: List[str],
        cc_emails: List[str]
    ):
        """Create EmailRecipientView records for each recipient"""
        # Map emails to users
        to_users = User.objects.filter(email__in=to_emails)
        cc_users = User.objects.filter(email__in=cc_emails) if cc_emails else []
        
        # Create tracking for TO recipients
        for user in to_users:
            EmailRecipientView.objects.create(
                email_log=email_log,
                recipient_user=user,
                is_to=True,
                is_read=False
            )
        
        # Create tracking for CC recipients
        for user in cc_users:
            # Avoid duplicates if user is in both TO and CC
            if not EmailRecipientView.objects.filter(
                email_log=email_log,
                recipient_user=user
            ).exists():
                EmailRecipientView.objects.create(
                    email_log=email_log,
                    recipient_user=user,
                    is_to=False,
                    is_read=False
                )
    
    @staticmethod
    def save_draft(
        user,
        send_type: str,
        subject: str,
        body_html: str,
        cost_center_ids: Optional[List[int]] = None,
        template_id: Optional[int] = None,
        draft_name: Optional[str] = None,
        draft_id: Optional[int] = None
    ) -> Dict:
        """
        Save or update email draft.
        
        Args:
            user: Draft owner
            send_type: 'ANNOUNCEMENT' or 'SPECIFIC'
            subject: Email subject
            body_html: Email body HTML
            cost_center_ids: List of cost center IDs (for SPECIFIC)
            template_id: Template reference (optional)
            draft_name: Optional name for draft
            draft_id: If updating existing draft
            
        Returns:
            Dict with success status and draft data
        """
        try:
            template = None
            if template_id:
                try:
                    template = EmailTemplate.objects.get(id=template_id)
                except EmailTemplate.DoesNotExist:
                    pass
            
            if draft_id:
                # Update existing draft
                try:
                    draft = EmailDraft.objects.get(id=draft_id, user=user)
                    draft.send_type = send_type
                    draft.subject = subject
                    draft.body_html = body_html
                    draft.template = template
                    draft.draft_name = draft_name
                    if cost_center_ids:
                        draft.set_cost_center_list(cost_center_ids)
                    draft.save()
                except EmailDraft.DoesNotExist:
                    return {
                        'success': False,
                        'error': 'Draft not found'
                    }
            else:
                # Create new draft
                draft = EmailDraft.objects.create(
                    user=user,
                    template=template,
                    send_type=send_type,
                    subject=subject,
                    body_html=body_html,
                    draft_name=draft_name
                )
                if cost_center_ids:
                    draft.set_cost_center_list(cost_center_ids)
                    draft.save()
            
            return {
                'success': True,
                'draft': draft
            }
            
        except Exception as e:
            logger.error(f"Error saving draft: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def send_from_draft(user, draft_id: int, overrides: Optional[Dict] = None) -> Dict:
        """
        Send email from saved draft.
        
        Args:
            user: Sender user
            draft_id: Draft ID
            overrides: Optional dict with 'subject' and 'body_html' overrides
            
        Returns:
            Dict with success status and details
        """
        try:
            draft = EmailDraft.objects.get(id=draft_id, user=user)
            
            # Use overrides if provided
            subject = overrides.get('subject', draft.subject) if overrides else draft.subject
            body_html = overrides.get('body_html', draft.body_html) if overrides else draft.body_html
            
            # Send email
            result = EmailService.send_email(
                user=user,
                send_type=draft.send_type,
                subject=subject,
                body_html=body_html,
                cost_center_ids=draft.get_cost_center_list() if draft.send_type == 'SPECIFIC' else None,
                template_id=draft.template_id,
                draft_id=draft.id
            )
            
            return result
            
        except EmailDraft.DoesNotExist:
            return {
                'success': False,
                'error': 'Draft not found'
            }
        except Exception as e:
            logger.error(f"Error sending from draft: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
