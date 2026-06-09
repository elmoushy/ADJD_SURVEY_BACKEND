"""
Email utilities for the authentication app.

Currently provides the password-reset email sender used by the
forgot-password flow.
"""

import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(user, code: str) -> bool:
    """
    Send a bilingual (Arabic + English) password-reset email containing
    a 6-digit one-time code.

    Args:
        user:  User instance (needs .email and .first_name attributes).
        code:  Plaintext 6-digit code string (e.g. '482031').

    Returns:
        True on success, False if the send failed.
    """
    subject = "إعادة تعيين كلمة المرور / Password Reset Code"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    display_name = user.first_name or user.email

    # ── Plain-text fallback ──────────────────────────────────────────────────
    plain_text = (
        f"مرحباً {display_name},\n\n"
        f"رمز إعادة تعيين كلمة المرور الخاص بك هو: {code}\n"
        f"صالح لمدة 10 دقائق فقط.\n\n"
        f"إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد الإلكتروني.\n\n"
        f"---\n\n"
        f"Hello {display_name},\n\n"
        f"Your password reset code is: {code}\n"
        f"Valid for 10 minutes only.\n\n"
        f"If you did not request a password reset, please ignore this email."
    )

    # ── HTML body ────────────────────────────────────────────────────────────
    html_body = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style type="text/css">
    body {{ direction: rtl; font-family: 'Cairo', 'Noto Kufi Arabic', 'Segoe UI', Tahoma, Arial, sans-serif; margin: 0; padding: 0; background-color: #F5F7FA; }}
    .container {{ max-width: 620px; margin: 30px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(35,31,32,0.12); border: 1px solid #E5E8E1; }}
    .header {{ background: linear-gradient(135deg, #B78A41 0%, #A17D23 100%); padding: 24px; text-align: center; }}
    .header h1 {{ color: #ffffff; margin: 0; font-size: 22px; }}
    .content {{ padding: 32px 24px; text-align: right; }}
    .content p {{ color: #4D4D4F; font-size: 15px; line-height: 1.8; margin: 12px 0; }}
    .code-box {{ background-color: #F8F6F0; border-right: 4px solid #B78A41; padding: 20px 16px; border-radius: 8px; margin: 20px 0; text-align: center; }}
    .code-label {{ font-size: 13px; color: #808285; margin-bottom: 10px; }}
    .code {{ font-size: 42px; font-weight: 700; letter-spacing: 10px; color: #B78A41; font-family: 'Courier New', monospace; }}
    .code-expiry {{ font-size: 13px; color: #808285; margin-top: 10px; }}
    .warning-box {{ background-color: #F8F6F0; border-right: 4px solid #B78A41; padding: 12px 16px; border-radius: 8px; margin: 20px 0; color: #4D4D4F; font-size: 14px; line-height: 1.8; }}
    .divider {{ border: none; border-top: 1px solid #E5E8E1; margin: 28px 0; }}
    .en-section {{ direction: ltr; text-align: left; color: #4D4D4F; font-size: 14px; line-height: 1.8; }}
    .footer {{ background-color: #F8F6F0; padding: 16px 24px; text-align: center; border-top: 1px solid #E5E8E1; }}
    .footer p {{ color: #808285; font-size: 12px; margin: 4px 0; }}
  </style>
</head>
<body>
  <div class="container">

    <div class="header">
      <h1>إعادة تعيين كلمة المرور</h1>
    </div>

    <div class="content">
      <p>مرحباً <strong>{display_name}</strong>،</p>
      <p>تلقينا طلباً لإعادة تعيين كلمة المرور الخاصة بحسابك في نظام الإيضاحات. استخدم الرمز أدناه:</p>

      <div class="code-box">
        <div class="code-label">رمز التحقق / Verification Code</div>
        <div class="code">{code}</div>
        <div class="code-expiry">صالح لمدة <strong>10 دقائق</strong> فقط &nbsp;|&nbsp; Valid for <strong>10 minutes</strong> only</div>
      </div>

      <div class="warning-box">
        إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد الإلكتروني. لن يتم إجراء أي تغيير على حسابك.
      </div>

      <hr class="divider">

      <div class="en-section">
        <p>Hello <strong>{display_name}</strong>,</p>
        <p>We received a request to reset your account password. Use the code above to proceed.</p>
        <p>If you did not request this, please ignore this email — your account remains secure.</p>
      </div>
    </div>

    <div class="footer">
      <p>هذه رسالة آلية من نظام الايضاحات - إدارة المالية - دائرة القضاء</p>
      <p>This is an automated email — please do not reply</p>
    </div>

  </div>
</body>
</html>"""

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            from_email=from_email,
            to=to_email,
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Password reset email sent to {user.email}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send password reset email to {user.email}: {exc}")
        return False
