"""
Survey Email Notification Service

Sends email notifications to users when a survey is shared with them.
Uses threading for non-blocking execution so the API endpoint responds quickly.
"""

import logging
import threading
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

# Frontend base URL (configurable via settings or env)
FRONTEND_BASE_URL = getattr(
    settings, 'FRONTEND_BASE_URL',
    settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else 'http://localhost:5173'
)


def _build_survey_email_html(survey_title: str, survey_url: str, sender_name: str) -> str:
    """
    Build RTL HTML email template for survey sharing notification.
    Contains a 'بدء الايضاح' button linking to the survey.
    """
    return f'''<html dir="rtl">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<style type="text/css">
body {{ direction: rtl; font-family: 'Cairo', 'Noto Kufi Arabic', 'Segoe UI', Tahoma, Arial, sans-serif; margin: 0; padding: 0; background-color: #F5F7FA; }}
.container {{ max-width: 620px; margin: 30px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(35,31,32,0.12); border: 1px solid #E5E8E1; }}
.header {{ background: linear-gradient(135deg, #B78A41 0%, #A17D23 100%); padding: 24px; text-align: center; }}
.header h1 {{ color: #ffffff; margin: 0; font-size: 22px; }}
.content {{ padding: 32px 24px; text-align: right; }}
.content p {{ color: #4D4D4F; font-size: 15px; line-height: 1.8; margin: 12px 0; }}
.survey-title {{ background-color: #F8F6F0; border-right: 4px solid #B78A41; padding: 12px 16px; border-radius: 8px; margin: 20px 0; }}
.survey-title span {{ font-weight: bold; color: #231F20; font-size: 16px; }}
.btn-container {{ text-align: center; margin: 32px 0; }}
.btn {{ display: inline-block; background: linear-gradient(135deg, #B78A41 0%, #A17D23 100%); color: #ffffff; text-decoration: none; padding: 14px 40px; border-radius: 8px; font-size: 16px; font-weight: bold; }}
.footer {{ background-color: #F8F6F0; padding: 16px 24px; text-align: center; border-top: 1px solid #E5E8E1; }}
.footer p {{ color: #808285; font-size: 12px; margin: 4px 0; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>ايضاح جديد</h1>
    </div>
    <div class="content">
        <p>مرحباً،</p>
        <p>تمت مشاركة ايضاح جديد معك بواسطة <strong>قسم التخطيط والموازنة - إدارة المالية</strong>.</p>
        <div class="survey-title">
            <span>{survey_title}</span>
        </div>
        <p>يرجى الضغط على الزر أدناه للبدء:</p>
        <div class="btn-container">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto; border-collapse: separate;">
                <tr>
                    <td align="center" bgcolor="#B78A41" style="border-radius: 8px; mso-padding-alt: 0;">
                        <a href="{survey_url}" class="btn" style="display: inline-block; padding: 14px 40px; font-size: 16px; font-weight: bold; color: #ffffff; text-decoration: none; background: #B78A41; border: 1px solid #A17D23; border-radius: 8px; line-height: 1.2;">
                            بدء الإيضاح
                        </a>
                    </td>
                </tr>
            </table>
        </div>
    </div>
    <div class="footer">
        <p>هذه رسالة آلية من نظام الايضاحات - إدارة المالية - دائرة القضاء</p>
    </div>
</div>
</body>
</html>'''


def _build_survey_email_plain(survey_title: str, survey_url: str, sender_name: str) -> str:
    """Plain text fallback for email clients that don't support HTML."""
    return (
        f"مرحباً،\n\n"
        f"تمت مشاركة ايضاح جديد معك بواسطة {sender_name}.\n\n"
        f"عنوان الايضاح: {survey_title}\n\n"
        f"للبدء، يرجى زيارة الرابط التالي:\n{survey_url}\n\n"
        f"---\n"
        f"نظام الايضاحات - إدارة المالية-دائرة القضاء"
    )


def _get_survey_url(survey_id: str) -> str:
    """Build the frontend URL for taking a survey."""
    base = FRONTEND_BASE_URL.rstrip('/')
    return f"{base}/surveys/take/{survey_id}"


def _send_emails_to_users(user_emails: list, survey_title: str, survey_id: str, sender_name: str):
    """
    Send survey notification emails to a list of user emails.
    This runs in a background thread.
    """
    survey_url = _get_survey_url(survey_id)
    subject = f"ايضاح جديد: {survey_title}"
    html_body = _build_survey_email_html(survey_title, survey_url, sender_name)
    plain_body = _build_survey_email_plain(survey_title, survey_url, sender_name)
    from_email = settings.DEFAULT_FROM_EMAIL

    success_count = 0
    fail_count = 0

    for email in user_emails:
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=from_email,
                to=[email]
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send survey notification to {email}: {e}")

    logger.info(
        f"Survey share notification for '{survey_title}' (ID: {survey_id}): "
        f"sent={success_count}, failed={fail_count}, total={len(user_emails)}"
    )


def notify_survey_shared(survey, sender_user, user_ids=None, group_ids=None):
    """
    Send email notifications to users when a survey is shared with them.
    Runs in a background thread to avoid blocking the API response.

    Args:
        survey: Survey model instance
        sender_user: The user who shared the survey
        user_ids: List of user IDs directly shared with
        group_ids: List of group IDs shared with
    """
    try:
        # Collect all recipient emails
        recipient_emails = set()

        # Direct user shares
        if user_ids:
            direct_users = User.objects.filter(
                id__in=user_ids, is_active=True
            ).values_list('email', flat=True)
            recipient_emails.update(direct_users)

        # Group member shares
        if group_ids:
            group_member_emails = User.objects.filter(
                user_groups__group_id__in=group_ids,
                is_active=True
            ).values_list('email', flat=True)
            recipient_emails.update(group_member_emails)

        # Exclude the sender from receiving the notification
        sender_email = getattr(sender_user, 'email', None)
        if sender_email:
            recipient_emails.discard(sender_email)

        if not recipient_emails:
            logger.info(f"No recipients to notify for survey {survey.id}")
            return

        # Prepare data for the thread
        survey_title = survey.title or "ايضاح"
        survey_id = str(survey.id)
        sender_name = f"{sender_user.first_name} {sender_user.last_name}".strip() or sender_user.email
        emails_list = list(recipient_emails)

        # Send in background thread
        thread = threading.Thread(
            target=_send_emails_to_users,
            args=(emails_list, survey_title, survey_id, sender_name),
            daemon=True
        )
        thread.start()

        logger.info(
            f"Started background email notification for survey {survey_id} "
            f"to {len(emails_list)} recipients"
        )

    except Exception as e:
        logger.error(f"Error initiating survey share notification: {e}")
