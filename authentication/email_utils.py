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
  <style>
    body {{
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      background-color: #f5f5f5;
      margin: 0; padding: 0;
      direction: rtl;
    }}
    .wrapper {{
      max-width: 560px;
      margin: 40px auto;
      background: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }}
    .header {{
      background: linear-gradient(135deg, #AE5D5A, #CFA365);
      padding: 32px 24px;
      text-align: center;
    }}
    .header h1 {{
      color: #ffffff;
      margin: 0;
      font-size: 22px;
      letter-spacing: 0.5px;
    }}
    .body {{
      padding: 32px 28px;
      color: #333333;
    }}
    .greeting {{
      font-size: 16px;
      margin-bottom: 16px;
    }}
    .code-box {{
      background: #f9f1e8;
      border: 2px dashed #CFA365;
      border-radius: 10px;
      text-align: center;
      padding: 20px;
      margin: 24px 0;
    }}
    .code-label {{
      font-size: 13px;
      color: #888888;
      margin-bottom: 8px;
    }}
    .code {{
      font-size: 42px;
      font-weight: 700;
      letter-spacing: 10px;
      color: #AE5D5A;
    }}
    .expiry {{
      font-size: 13px;
      color: #888888;
      margin-top: 10px;
    }}
    .warning {{
      background: #fff8e1;
      border-left: 4px solid #CFA365;
      border-right: 4px solid #CFA365;
      padding: 12px 16px;
      border-radius: 6px;
      font-size: 13px;
      color: #666;
      margin-top: 20px;
    }}
    .divider {{
      border: none;
      border-top: 1px solid #eeeeee;
      margin: 28px 0;
    }}
    .en-section {{
      direction: ltr;
      text-align: left;
      color: #555555;
      font-size: 14px;
    }}
    .footer {{
      background: #f5f5f5;
      text-align: center;
      padding: 16px;
      font-size: 12px;
      color: #999999;
    }}
  </style>
</head>
<body>
  <div class="wrapper">

    <div class="header">
      <h1>🔐 إعادة تعيين كلمة المرور</h1>
    </div>

    <div class="body">
      <!-- Arabic section -->
      <p class="greeting">مرحباً <strong>{display_name}</strong>،</p>
      <p>لقد تلقينا طلباً لإعادة تعيين كلمة المرور الخاصة بحسابك. استخدم الرمز التالي:</p>

      <div class="code-box">
        <div class="code-label">رمز التحقق</div>
        <div class="code">{code}</div>
        <div class="expiry">⏱ صالح لمدة <strong>10 دقائق</strong> فقط</div>
      </div>

      <div class="warning">
        ⚠️ إذا لم تطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد الإلكتروني.
        لن يتم تغيير أي شيء في حسابك.
      </div>

      <hr class="divider">

      <!-- English section -->
      <div class="en-section">
        <p>Hello <strong>{display_name}</strong>,</p>
        <p>We received a request to reset the password for your account. Use the code above.</p>
        <p>⚠️ If you did not request a password reset, please ignore this email. Your account remains secure.</p>
      </div>
    </div>

    <div class="footer">
      هذا البريد الإلكتروني مرسل تلقائياً — يرجى عدم الرد عليه<br>
      This is an automated email — please do not reply
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
