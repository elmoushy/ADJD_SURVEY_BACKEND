"""
Email Service - Business logic for email communication system
Handles email sending, draft management, and recipient tracking
"""
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.db import transaction, connections
from django.utils import timezone
from django.contrib.auth import get_user_model
from typing import List, Dict, Optional
import logging
import threading

from .models import (
    CostCenter,
    EmailTemplate,
    EmailDraft,
    EmailLog,
    EmailRecipientView,
    EmailAttachment,
    EmailLogAttachment,
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
.ql-align-right {{ text-align: right !important; }}
.ql-align-center {{ text-align: center !important; }}
.ql-align-left {{ text-align: left !important; }}
.ql-align-justify {{ text-align: justify !important; }}
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
    def _load_attachment_payloads(attachment_ids) -> List[Dict]:
        """
        Read attachment blobs once into memory so they can be attached to every
        outgoing message and copied into the immutable sent record.

        Returns a list of dicts: {'id', 'filename', 'content', 'mime_type'}.
        Oracle returns BinaryField as a LOB/memoryview, so convert to bytes.
        """
        if not attachment_ids:
            return []
        payloads = []
        for att in EmailAttachment.objects.filter(id__in=attachment_ids):
            raw = att.file_data
            file_bytes = raw.read() if hasattr(raw, 'read') else bytes(raw)
            payloads.append({
                'id': str(att.id),
                'filename': att.original_filename,
                'content': file_bytes,
                'mime_type': att.mime_type,
            })
        return payloads

    @staticmethod
    def _persist_sent_attachments(sent_log, received_logs, att_payloads):
        """
        Create one immutable EmailAttachment copy per file owned by the SENT log,
        then link it to the SENT log and every RECEIVED log so the same blob is
        shared (not duplicated per recipient) across outbox/inbox views.
        """
        for p in att_payloads:
            copy = EmailAttachment.objects.create(
                file_data=p['content'],
                original_filename=p['filename'],
                file_size=len(p['content']),
                mime_type=p['mime_type'],
                sent_log=sent_log,
                uploaded_by=sent_log.user,
            )
            EmailLogAttachment.objects.create(email_log=sent_log, attachment=copy)
            for received_log in received_logs:
                EmailLogAttachment.objects.create(email_log=received_log, attachment=copy)

    @staticmethod
    def _cleanup_orphan_attachments(attachment_ids):
        """Delete source attachments that were never owned by a template/draft."""
        if not attachment_ids:
            return
        EmailAttachment.objects.filter(
            id__in=attachment_ids,
            template__isnull=True,
            draft__isnull=True,
            sent_log__isnull=True,
        ).delete()

    @staticmethod
    def send_email(
        user,
        send_type: str,
        subject: str,
        body_html: str,
        cost_center_ids: Optional[List[int]] = None,
        template_id: Optional[int] = None,
        draft_id: Optional[int] = None,
        attachment_ids: Optional[List[str]] = None
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
            attachment_ids: List of EmailAttachment ids to attach (optional)

        Returns:
            Dict with success status and details. Email delivery (SMTP) runs in a
            background thread; records are persisted as PENDING and flipped to
            SUCCESS/FAILED once the thread finishes, so the API responds instantly.
        """
        try:
            with transaction.atomic():
                # Read attachment blobs once (shared across all recipients)
                att_payloads = EmailService._load_attachment_payloads(attachment_ids)
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

                cost_centers = list(cost_centers)
                if not cost_centers:
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

                # Sender's outbox entry (PENDING until the background send finishes)
                sent_log = EmailService._create_sent_log(
                    user=user,
                    send_type=send_type,
                    subject=subject,
                    body_html=body_html,
                    cost_centers=cost_centers,
                    template=template,
                    draft=draft,
                    status='PENDING',
                    error=None
                )

                # Create per-cost-center records synchronously (fast), and build the
                # list of SMTP jobs to run in the background.
                results = []
                received_logs = []   # for attachment linking
                send_jobs = []       # [{received_log_id, to_emails, cc_emails}]
                queued = 0
                failed = 0

                for cost_center in cost_centers:
                    to_emails = cost_center.get_recipient_emails()
                    cc_emails = cost_center.get_cc_emails()

                    if not to_emails:
                        results.append({
                            'success': False,
                            'cost_center': cost_center.cost_center_code,
                            'error': 'No users in cost center'
                        })
                        failed += 1
                        continue

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
                        email_status='PENDING',
                        email_error=None
                    )
                    received_logs.append(received_log)

                    # Populate recipients' inbox immediately (status follows the log)
                    EmailService._create_recipient_tracking(
                        email_log=received_log,
                        to_emails=to_emails,
                        cc_emails=cc_emails
                    )

                    send_jobs.append({
                        'received_log_id': received_log.id,
                        'to_emails': to_emails,
                        'cc_emails': cc_emails,
                    })
                    results.append({
                        'success': True,
                        'cost_center': cost_center.cost_center_code,
                        'recipients_count': len(to_emails),
                        'log_id': received_log.id,
                        'queued': True
                    })
                    queued += 1

                # Persist immutable sent copies and link to outbox + inboxes
                if att_payloads:
                    EmailService._persist_sent_attachments(
                        sent_log, received_logs, att_payloads
                    )
                # Remove leftover orphan uploads (not owned by a template/draft)
                EmailService._cleanup_orphan_attachments(attachment_ids)

                sent_log_id = sent_log.id

                if send_jobs:
                    # Start the SMTP send only after the DB transaction commits, so
                    # the background thread sees the freshly created rows.
                    transaction.on_commit(
                        lambda: EmailService._dispatch_send_jobs(
                            send_jobs, att_payloads, subject, body_html, sent_log_id
                        )
                    )
                else:
                    # Nothing deliverable — mark the outbox entry failed now
                    sent_log.email_status = 'FAILED'
                    sent_log.email_error = 'No recipients in selected cost centers'
                    sent_log.save(update_fields=['email_status', 'email_error'])

                return {
                    'success': queued > 0,
                    'queued': True,
                    'sent_count': queued,
                    'failed_count': failed,
                    'total_cost_centers': len(cost_centers),
                    'details': results,
                    'sent_log_id': sent_log_id
                }

        except Exception as e:
            logger.error(f"Error sending email: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def _dispatch_send_jobs(send_jobs, att_payloads, subject, body_html, sent_log_id):
        """Spawn a daemon thread that performs the actual SMTP delivery."""
        thread = threading.Thread(
            target=EmailService._process_send_jobs,
            args=(send_jobs, att_payloads, subject, body_html, sent_log_id),
            daemon=True
        )
        thread.start()
        logger.info(
            "Started background email send: %s job(s), outbox log %s",
            len(send_jobs), sent_log_id
        )

    @staticmethod
    def _process_send_jobs(send_jobs, att_payloads, subject, body_html, sent_log_id):
        """
        Background worker: send each cost center's email over SMTP and update the
        corresponding log status. Runs in its own thread, so it manages (and closes)
        its own database connection.
        """
        from_email = settings.DEFAULT_FROM_EMAIL
        any_success = False
        try:
            for job in send_jobs:
                sent = EmailService._send_actual_email(
                    subject=subject,
                    body_html=body_html,
                    to_emails=job['to_emails'],
                    cc_emails=job['cc_emails'],
                    from_email=from_email,
                    attachments=att_payloads
                )
                EmailLog.objects.filter(id=job['received_log_id']).update(
                    email_status='SUCCESS' if sent else 'FAILED',
                    email_error=None if sent else 'Email sending failed'
                )
                if sent:
                    any_success = True

            EmailLog.objects.filter(id=sent_log_id).update(
                email_status='SUCCESS' if any_success else 'FAILED',
                email_error=None if any_success else 'Email sending failed'
            )
            logger.info(
                "Background email send finished: outbox log %s (success=%s)",
                sent_log_id, any_success
            )
        except Exception as e:
            logger.error(f"Background email send failed: {str(e)}", exc_info=True)
            EmailLog.objects.filter(id=sent_log_id).update(
                email_status='FAILED',
                email_error=str(e)
            )
        finally:
            # Release the thread-local DB connection
            connections.close_all()

    @staticmethod
    def _send_actual_email(
        subject: str,
        body_html: str,
        to_emails: List[str],
        cc_emails: List[str],
        from_email: str,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """
        Send actual email via Django email backend.
        Wraps content in RTL format before sending and attaches any files.
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

            # Attach files (documents only)
            for att in (attachments or []):
                msg.attach(att['filename'], att['content'], att['mime_type'])

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

            # Carry the draft's own attachments into the send
            draft_attachment_ids = [str(a.id) for a in draft.attachments.all()]

            # Send email
            result = EmailService.send_email(
                user=user,
                send_type=draft.send_type,
                subject=subject,
                body_html=body_html,
                cost_center_ids=draft.get_cost_center_list() if draft.send_type == 'SPECIFIC' else None,
                template_id=draft.template_id,
                draft_id=draft.id,
                attachment_ids=draft_attachment_ids or None
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
