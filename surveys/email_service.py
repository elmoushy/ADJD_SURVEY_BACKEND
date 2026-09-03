"""
Survey Email Notification Service

Sends email notifications to users when a survey is shared with them.
Uses threading for non-blocking execution so the API endpoint responds quickly.
"""

import logging
import threading
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.html import escape

logger = logging.getLogger(__name__)
User = get_user_model()

import os

# Frontend base URL (configurable via env first, then settings)
FRONTEND_BASE_URL = os.environ.get(
    'FRONTEND_BASE_URL', 
    getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')
)


def _build_survey_email_html(
    survey_title: str,
    survey_url: str,
    sender_name: str,
    group_name: str = None,
) -> str:
    """
    Build RTL HTML email template for survey sharing notification.
    Contains a 'بدء الايضاح' button linking to the survey.

    When ``group_name`` is given the email is a *group* notification: the
    group members are in TO and the group managers are in CC, so the body names
    the group the survey was shared with.
    """
    safe_title = escape(survey_title)

    if group_name:
        # <bdi> isolates the group name's own bidi direction (it may be
        # Arabic, English, or mixed) so it can't reorder the surrounding RTL
        # sentence — without it, a Latin group name visually scrambles the
        # Arabic text around it.
        intro = (
            f'<p>تمت مشاركة ايضاح جديد مع مجموعة '
            f'<strong><bdi>{escape(group_name)}</bdi></strong> بواسطة '
            f'<strong>قسم التخطيط والموازنة - إدارة المالية</strong>.</p>'
        )
    else:
        intro = (
            '<p>تمت مشاركة ايضاح جديد معك بواسطة '
            '<strong>قسم التخطيط والموازنة - إدارة المالية</strong>.</p>'
        )

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
        {intro}
        <div class="survey-title">
            <span>{safe_title}</span>
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


def _build_survey_email_plain(
    survey_title: str,
    survey_url: str,
    sender_name: str,
    group_name: str = None,
) -> str:
    """Plain text fallback for email clients that don't support HTML."""
    if group_name:
        intro = f"تمت مشاركة ايضاح جديد مع مجموعة {_isolate_bidi(group_name)} بواسطة {sender_name}."
    else:
        intro = f"تمت مشاركة ايضاح جديد معك بواسطة {sender_name}."

    return (
        f"مرحباً،\n\n"
        f"{intro}\n\n"
        f"عنوان الايضاح: {survey_title}\n\n"
        f"للبدء، يرجى زيارة الرابط التالي:\n{survey_url}\n\n"
        f"---\n"
        f"نظام الايضاحات - إدارة المالية-دائرة القضاء"
    )


def _get_survey_url(survey_id: str) -> str:
    """Build the frontend URL for taking a survey."""
    base = FRONTEND_BASE_URL.rstrip('/')
    return f"{base}/surveys/take/{survey_id}"


def _normalize_email(email) -> str:
    """Trim an address; empty string when it is unusable."""
    return (email or '').strip()


def _isolate_bidi(text: str) -> str:
    """
    Wrap arbitrary text (e.g. a group name that may be Arabic, English, or
    mixed) in Unicode bidi isolates so it can't reorder the RTL sentence
    around it in plain-text emails — the HTML templates get the same
    protection from <bdi>, which isn't available outside markup.
    """
    return f"⁨{text}⁩"


def _collect_group_recipients(group_ids, exclude_emails=frozenset()):
    """
    Resolve one TO/CC bucket per group in a *single* database query.

    Reads the User↔Group through model directly with ``values_list`` so neither
    User nor Group instances are built and no per-group query is issued — the
    ``Group.get_members()`` / ``Group.get_admins()`` helpers would cost one
    query per group each (the classic N+1).

    Bucketing follows the product rule: a group's members are addressed in TO
    and its managers (``UserGroup.is_group_admin``) are copied in CC, so a
    manager who is also a member is listed once, in CC. A group whose only
    members are managers keeps them in TO — a message must have a real
    addressee.

    Args:
        group_ids: iterable of Group PKs.
        exclude_emails: lower-cased addresses to drop (e.g. the sender's).

    Returns:
        list[dict]: ``{'group_id', 'group_name', 'to': [...], 'cc': [...]}`` for
        every group with at least one deliverable address, ordered by group id
        for a stable send order.
    """
    from authentication.models import UserGroup

    group_ids = [gid for gid in (group_ids or []) if gid is not None]
    if not group_ids:
        return []

    rows = (
        UserGroup.objects
        .filter(group_id__in=group_ids, user__is_active=True)
        .exclude(user__email__isnull=True)
        .exclude(user__email='')
        # UserGroup.Meta orders by group__name/user__email; clearing it drops a
        # sort we don't need (the group name is already selected below).
        .order_by()
        .values_list('group_id', 'group__name', 'user__email', 'is_group_admin')
    )

    buckets = {}
    for group_id, group_name, email, is_group_admin in rows.iterator():
        email = _normalize_email(email)
        if not email:
            continue
        key = email.lower()
        if key in exclude_emails:
            continue

        bucket = buckets.get(group_id)
        if bucket is None:
            bucket = buckets[group_id] = {
                'group_id': group_id,
                'group_name': group_name,
                'to': [],
                'cc': [],
                '_seen': set(),
            }

        if key in bucket['_seen']:
            continue
        bucket['_seen'].add(key)
        bucket['cc' if is_group_admin else 'to'].append(email)

    result = []
    for group_id in sorted(buckets):
        bucket = buckets[group_id]
        bucket.pop('_seen', None)
        if not bucket['to']:
            if not bucket['cc']:
                continue
            # Managers-only group: address them directly instead of shipping a
            # message with an empty To header.
            bucket['to'], bucket['cc'] = bucket['cc'], []
        result.append(bucket)

    return result


def _send_share_emails(group_buckets: list, direct_emails: list, survey_title: str,
                       survey_id: str, sender_name: str):
    """
    Send every survey-share message over a **single** SMTP connection.

    One connection for the whole batch instead of Django's default
    connect-per-``send()``, and one rendered body per distinct group (plus one
    shared body for all direct shares) — the templates are pure functions of
    (title, url, sender, group_name). Each message is still handed to the server
    individually so a rejected recipient is logged and skipped without aborting
    the rest of the batch.

    Runs in a background thread — never call this on the request path.
    """
    survey_url = _get_survey_url(survey_id)
    subject = f"ايضاح جديد: {survey_title}"
    from_email = settings.DEFAULT_FROM_EMAIL

    messages = []

    for bucket in group_buckets:
        group_name = bucket['group_name']
        msg = EmailMultiAlternatives(
            subject=subject,
            body=_build_survey_email_plain(survey_title, survey_url, sender_name, group_name),
            from_email=from_email,
            to=list(bucket['to']),
            cc=list(bucket['cc']),
        )
        msg.attach_alternative(
            _build_survey_email_html(survey_title, survey_url, sender_name, group_name),
            "text/html",
        )
        messages.append((f"group '{group_name}'", msg))

    if direct_emails:
        plain_body = _build_survey_email_plain(survey_title, survey_url, sender_name)
        html_body = _build_survey_email_html(survey_title, survey_url, sender_name)
        for email in direct_emails:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=from_email,
                to=[email],
            )
            msg.attach_alternative(html_body, "text/html")
            messages.append((email, msg))

    if not messages:
        return

    success_count = 0
    fail_count = 0
    connection = None

    try:
        connection = get_connection()
        connection.open()
        for label, msg in messages:
            msg.connection = connection
            try:
                msg.send()
                success_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to send survey notification to {label}: {e}")
    except Exception as e:
        fail_count = len(messages) - success_count
        logger.error(f"SMTP failure while notifying survey {survey_id}: {e}")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    recipient_count = sum(
        len(b['to']) + len(b['cc']) for b in group_buckets
    ) + len(direct_emails)
    logger.info(
        f"Survey share notification for '{survey_title}' (ID: {survey_id}): "
        f"messages_sent={success_count}, messages_failed={fail_count}, "
        f"groups={len(group_buckets)}, direct={len(direct_emails)}, "
        f"recipients={recipient_count}"
    )


def notify_survey_shared(survey, sender_user, user_ids=None, group_ids=None):
    """
    Send email notifications to users when a survey is shared with them.
    Runs in a background thread to avoid blocking the API response.

    Each group receives **one** message: its members in TO and its managers in
    CC, so a manager can see that the whole group was assigned the survey.
    Directly-shared users get an individual message, and anyone already reached
    by a group message is skipped so nobody is emailed twice.

    Callers must pass only the *newly added* users/groups — re-saving the share
    dialog must not re-notify an audience that was already notified.

    Args:
        survey: Survey model instance
        sender_user: The user who shared the survey
        user_ids: List of user IDs newly shared with directly
        group_ids: List of group IDs newly shared with
    """
    try:
        # The sender never notifies themselves — neither in TO nor in CC.
        sender_email = _normalize_email(getattr(sender_user, 'email', None))
        exclude_emails = {sender_email.lower()} if sender_email else frozenset()

        # One query for every group, bucketed into TO/CC per group.
        group_buckets = _collect_group_recipients(group_ids, exclude_emails)

        # Addresses a group message already TO's. Only TO counts as "covered" —
        # a manager who is CC'd on their group's message (informational: "your
        # group was assigned this survey") still needs their own personal
        # invite if they were *also* directly shared, so CC never suppresses
        # a direct send.
        covered = {
            email.lower()
            for bucket in group_buckets
            for email in bucket['to']
        }

        # One query for the direct shares, minus anyone a group message covers.
        direct_emails = []
        if user_ids:
            seen = set(covered)
            direct_rows = (
                User.objects
                .filter(id__in=user_ids, is_active=True)
                .exclude(email__isnull=True)
                .exclude(email='')
                .order_by()
                .values_list('email', flat=True)
            )
            for email in direct_rows:
                email = _normalize_email(email)
                key = email.lower()
                if not email or key in seen or key in exclude_emails:
                    continue
                seen.add(key)
                direct_emails.append(email)

        if not group_buckets and not direct_emails:
            logger.info(f"No recipients to notify for survey {survey.id}")
            return

        survey_title = survey.title or "ايضاح"
        survey_id = str(survey.id)
        sender_name = (
            f"{sender_user.first_name} {sender_user.last_name}".strip()
            or sender_user.email
        )

        thread = threading.Thread(
            target=_send_share_emails,
            args=(group_buckets, direct_emails, survey_title, survey_id, sender_name),
            daemon=True,
        )
        thread.start()

        logger.info(
            f"Started background email notification for survey {survey_id}: "
            f"{len(group_buckets)} group message(s), "
            f"{len(direct_emails)} direct message(s)"
        )

    except Exception as e:
        logger.error(f"Error initiating survey share notification: {e}")


def notify_survey_published(survey, sender_user):
    """
    Notify a survey's whole explicit audience the moment it goes live.

    Sharing a *draft* deliberately sends no email — nobody should get a live
    "start the survey" link to an unfinished survey — so the audience attached
    while the survey was a draft has never heard about it. This is the one
    notification they get: called on the draft → submitted transition, it emails
    every group already in ``shared_with_groups`` (members in TO, managers in
    CC) and every user in ``shared_with``.

    Only meaningful for PRIVATE/GROUPS surveys — PUBLIC/AUTH audiences are not
    an explicit recipient list and are handled by the broadcast notification
    service instead.

    Safe to call on any transition: it no-ops when the visibility has no
    explicit audience or the audience is empty.
    """
    try:
        if getattr(survey, 'visibility', None) not in ('PRIVATE', 'GROUPS'):
            return

        # Two id-only queries; the recipient resolution itself stays a single
        # query per side inside notify_survey_shared().
        group_ids = list(survey.shared_with_groups.values_list('id', flat=True))
        user_ids = list(survey.shared_with.values_list('id', flat=True))

        if not group_ids and not user_ids:
            return

        notify_survey_shared(
            survey=survey,
            sender_user=sender_user,
            user_ids=user_ids,
            group_ids=group_ids,
        )
    except Exception as e:
        logger.error(f"Error notifying audience of published survey {survey.id}: {e}")


# ---------------------------------------------------------------------------
# Reminder notifications (sent to assigned users who have NOT responded)
# ---------------------------------------------------------------------------

def resolve_survey_assigned_users(survey):
    """
    Resolve the set of users a survey is *assigned* to.

    Single source of truth for "who is supposed to answer this survey", shared by
    the reminder emails below and by the assigned-users panel in the survey
    preview (SurveyViewSet.assigned_users).

    Assignment rules per visibility:
      - AUTH   : every active authenticated user is considered assigned.
      - PRIVATE: users in shared_with  ∪  non-manager members of shared_with_groups.
      - GROUPS : non-manager members of shared_with_groups.
      - PUBLIC : not applicable (anonymous respondents) → empty set.

    A group *manager* (``UserGroup.is_group_admin``) is not expected to answer
    on behalf of their group — they're informed by email (CC'd) instead — so
    membership that is admin-only does not make someone assigned. A manager who
    is *also* directly in ``shared_with`` is assigned like anyone else: direct
    sharing always means "you must respond," regardless of any manager role.

    Returns:
        tuple[str, QuerySet]: (mode, users) where mode is one of
        'public' | 'all_authenticated' | 'explicit'. For 'public' the queryset is
        empty.
    """
    visibility = getattr(survey, 'visibility', None)

    if visibility == 'PUBLIC':
        return 'public', User.objects.none()

    if visibility == 'AUTH':
        return 'all_authenticated', User.objects.filter(is_active=True)

    if visibility in ('PRIVATE', 'GROUPS'):
        from authentication.models import UserGroup

        assigned_user_ids = set(survey.shared_with.values_list('id', flat=True))
        group_member_ids = set(
            UserGroup.objects.filter(
                group__in=survey.shared_with_groups.all(),
                is_group_admin=False,
                user__is_active=True,
            ).values_list('user_id', flat=True)
        )
        all_ids = assigned_user_ids | group_member_ids
        return 'explicit', User.objects.filter(id__in=all_ids, is_active=True)

    return 'explicit', User.objects.none()


def get_survey_non_responder_emails(survey, exclude_user=None):
    """
    Resolve the set of *assigned* users who have NOT yet responded to a survey.

    Assignment is delegated to resolve_survey_assigned_users() so this function and
    the preview panel can never disagree about who an audience is.

    A user is a "non-responder" if they have no Response row (respondent FK)
    for this survey. Anonymous/email-only responses are not mapped back to
    assigned users (there is no reliable identity link), so only authenticated
    respondents are treated as having responded.

   
    The survey creator and the acting user (exclude_user) are always excluded,
    and users without a usable email address are dropped.

    Returns:
        list[str]: de-duplicated recipient email addresses.
    """
    from .models import Response  # local import to avoid circular imports

    mode, assigned_qs = resolve_survey_assigned_users(survey)
    if mode == 'public':
        return []

    # Users who already submitted an (authenticated) response
    responded_ids = set(
        Response.objects.filter(
            survey=survey, respondent__isnull=False
        ).values_list('respondent_id', flat=True)
    )

    # Exclude responders, the creator, and the acting user
    exclude_ids = set(responded_ids)
    creator_id = getattr(survey, 'creator_id', None)
    if creator_id:
        exclude_ids.add(creator_id)
    if exclude_user is not None and getattr(exclude_user, 'id', None):
        exclude_ids.add(exclude_user.id)

    non_responders = (
        assigned_qs.exclude(id__in=exclude_ids)
        # .exclude(role__in=['admin', 'super_admin'])  # never remind staff accounts
        .exclude(email__isnull=True)
        .exclude(email='')
    )

    # De-duplicate while preserving valid emails
    emails = {e for e in non_responders.values_list('email', flat=True) if e}
    return list(emails)


def _build_reminder_email_html(survey_title: str, survey_url: str, group_name: str = None) -> str:
    """
    RTL HTML reminder email — matches the gold-header theme of this module.

    When ``group_name`` is given this is a *group* reminder: the late members
    are in TO and the group's managers are in CC, so the body names the group
    and tells the managers why they were copied.
    """
    safe_title = escape(survey_title)

    if group_name:
        intro = (
            f'<p>نودّ تذكيركم بأنه لم يتم تسجيل ردكم بعد على الإيضاح التالي '
            f'الموجّه لمجموعة <strong><bdi>{escape(group_name)}</bdi></strong>. '
            f'نأمل أن تخصصوا بعض الوقت لإكماله.</p>'
        )
    else:
        intro = (
            '<p>نودّ تذكيرك بأنه لم يتم تسجيل ردك على الإيضاح التالي بعد. '
            'نأمل أن تخصص بعض الوقت لإكماله.</p>'
        )

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
        <h1>تذكير بالرد على الإيضاح</h1>
    </div>
    <div class="content">
        <p>مرحباً،</p>
        {intro}
        <div class="survey-title">
            <span>{safe_title}</span>
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


def _build_reminder_email_plain(survey_title: str, survey_url: str, group_name: str = None) -> str:
    """Plain-text fallback for the reminder email."""
    if group_name:
        intro = (
            f"نودّ تذكيركم بأنه لم يتم تسجيل ردكم بعد على الإيضاح التالي "
            f"الموجّه لمجموعة {_isolate_bidi(group_name)}."
        )
    else:
        intro = "نودّ تذكيرك بأنه لم يتم تسجيل ردك على الإيضاح التالي بعد."

    return (
        f"مرحباً،\n\n"
        f"{intro}\n\n"
        f"عنوان الإيضاح: {survey_title}\n\n"
        f"للبدء، يرجى زيارة الرابط التالي:\n{survey_url}\n\n"
        f"---\n"
        f"نظام الايضاحات - إدارة المالية - دائرة القضاء"
    )


def _collect_group_reminder_recipients(survey, to_exclude_ids, cc_exclude_emails=frozenset()):
    """
    Resolve one TO/CC reminder bucket per group in a *single* query.

    Mirrors ``_collect_group_recipients`` (the share-email version) but TO is
    restricted to non-responders: a group's late, non-manager members are the
    addressees, and its managers are copied so they know their group has
    stragglers — a manager's own response status never affects whether they're
    CC'd, since they were never expected to respond.

    A group with no late members produces nothing: no message, and its
    managers are not bothered.

    Args:
        survey: Survey instance.
        to_exclude_ids: user ids to drop from TO (responders, creator, the
            user triggering the reminder).
        cc_exclude_emails: lower-cased addresses to drop from CC (just the
            triggering user's own address, so nobody emails themselves).

    Returns:
        list[dict]: ``{'group_id', 'group_name', 'to': [...], 'cc': [...]}``
        for every group with at least one late member, ordered by group id.
    """
    from authentication.models import UserGroup

    group_ids = list(survey.shared_with_groups.values_list('id', flat=True))
    if not group_ids:
        return []

    rows = (
        UserGroup.objects
        .filter(group_id__in=group_ids, user__is_active=True)
        .exclude(user__email__isnull=True)
        .exclude(user__email='')
        .order_by()
        .values_list('group_id', 'group__name', 'user_id', 'user__email', 'is_group_admin')
    )

    buckets = {}
    for group_id, group_name, user_id, email, is_group_admin in rows.iterator():
        email = _normalize_email(email)
        if not email:
            continue

        bucket = buckets.get(group_id)
        if bucket is None:
            bucket = buckets[group_id] = {
                'group_id': group_id,
                'group_name': group_name,
                'to': [],
                'cc': [],
                '_seen_to': set(),
                '_seen_cc': set(),
            }

        key = email.lower()
        if is_group_admin:
            if key in cc_exclude_emails or key in bucket['_seen_cc']:
                continue
            bucket['_seen_cc'].add(key)
            bucket['cc'].append(email)
        else:
            if user_id in to_exclude_ids or key in bucket['_seen_to']:
                continue
            bucket['_seen_to'].add(key)
            bucket['to'].append(email)

    result = []
    for group_id in sorted(buckets):
        bucket = buckets[group_id]
        bucket.pop('_seen_to', None)
        bucket.pop('_seen_cc', None)
        if not bucket['to']:
            # Nobody late in this group — no message, managers not bothered.
            continue
        result.append(bucket)

    return result


def _send_reminder_batch(group_buckets: list, direct_emails: list, survey_title: str, survey_id: str):
    """
    Send every reminder message over a **single** SMTP connection — mirrors
    ``_send_share_emails``. Runs in a background thread.
    """
    survey_url = _get_survey_url(survey_id)
    subject = f"تذكير: لم تقم بالرد على الإيضاح بعد - {survey_title}"
    from_email = settings.DEFAULT_FROM_EMAIL

    messages = []

    for bucket in group_buckets:
        group_name = bucket['group_name']
        msg = EmailMultiAlternatives(
            subject=subject,
            body=_build_reminder_email_plain(survey_title, survey_url, group_name),
            from_email=from_email,
            to=list(bucket['to']),
            cc=list(bucket['cc']),
        )
        msg.attach_alternative(
            _build_reminder_email_html(survey_title, survey_url, group_name),
            "text/html",
        )
        messages.append((f"group '{group_name}'", msg))

    if direct_emails:
        plain_body = _build_reminder_email_plain(survey_title, survey_url)
        html_body = _build_reminder_email_html(survey_title, survey_url)
        for email in direct_emails:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=from_email,
                to=[email],
            )
            msg.attach_alternative(html_body, "text/html")
            messages.append((email, msg))

    if not messages:
        return

    success_count = 0
    fail_count = 0
    connection = None

    try:
        connection = get_connection()
        connection.open()
        for label, msg in messages:
            msg.connection = connection
            try:
                msg.send()
                success_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to send survey reminder to {label}: {e}")
    except Exception as e:
        fail_count = len(messages) - success_count
        logger.error(f"SMTP failure while sending reminders for survey {survey_id}: {e}")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    recipient_count = sum(len(b['to']) + len(b['cc']) for b in group_buckets) + len(direct_emails)
    logger.info(
        f"Survey reminder for '{survey_title}' (ID: {survey_id}): "
        f"messages_sent={success_count}, messages_failed={fail_count}, "
        f"groups={len(group_buckets)}, direct={len(direct_emails)}, "
        f"recipients={recipient_count}"
    )


def notify_survey_reminder(survey, exclude_user=None):
    """
    Remind every assigned non-responder — group-manager-only accounts are
    never included, since resolve_survey_assigned_users() excludes them (they
    aren't expected to respond).

    Each group with late members gets **one** message: its late, non-manager
    members in TO and its managers in CC, informing them their group has
    stragglers. Directly-shared non-responders get an individual reminder,
    minus anyone already covered by a group message's TO. A manager who is
    *also* directly shared and late still gets that personal reminder — being
    CC'd for their managed group never substitutes for it (see the same rule
    in notify_survey_shared).

    Runs the actual sending in a background thread; returns synchronously so
    the caller can report a count immediately.

    Args:
        survey: Survey model instance.
        exclude_user: the user triggering the reminder (e.g. the creator) —
            never reminded and never CC'd on their own action.

    Returns:
        int: number of non-responders the reminder was queued for (TO
        addresses only — CC'd managers aren't counted, matching the
        assigned-user total, which excludes them too).
    """
    from .models import Response  # local import to avoid circular imports

    try:
        mode, assigned_qs = resolve_survey_assigned_users(survey)
        if mode == 'public':
            return 0

        responded_ids = set(
            Response.objects.filter(
                survey=survey, respondent__isnull=False
            ).values_list('respondent_id', flat=True)
        )
        exclude_ids = set(responded_ids)
        creator_id = getattr(survey, 'creator_id', None)
        if creator_id:
            exclude_ids.add(creator_id)
        if exclude_user is not None and getattr(exclude_user, 'id', None):
            exclude_ids.add(exclude_user.id)

        if mode == 'all_authenticated':
            # AUTH has no group structure to bucket by — every non-responder
            # gets an individual reminder, same as before.
            group_buckets = []
            rows = (
                assigned_qs.exclude(id__in=exclude_ids)
                .exclude(email__isnull=True)
                .exclude(email='')
                .order_by()
                .values_list('email', flat=True)
            )
            seen = set()
            direct_emails = []
            for email in rows:
                email = _normalize_email(email)
                key = email.lower()
                if not email or key in seen:
                    continue
                seen.add(key)
                direct_emails.append(email)
        else:
            sender_email = _normalize_email(getattr(exclude_user, 'email', None))
            cc_exclude_emails = {sender_email.lower()} if sender_email else frozenset()

            group_buckets = _collect_group_reminder_recipients(survey, exclude_ids, cc_exclude_emails)

            covered = {email.lower() for bucket in group_buckets for email in bucket['to']}

            direct_rows = (
                assigned_qs
                .filter(id__in=survey.shared_with.values_list('id', flat=True))
                .exclude(id__in=exclude_ids)
                .exclude(email__isnull=True)
                .exclude(email='')
                .order_by()
                .values_list('email', flat=True)
            )
            seen = set(covered)
            direct_emails = []
            for email in direct_rows:
                email = _normalize_email(email)
                key = email.lower()
                if not email or key in seen:
                    continue
                seen.add(key)
                direct_emails.append(email)

        if not group_buckets and not direct_emails:
            logger.info(f"No non-responders to remind for survey {survey.id}")
            return 0

        survey_title = survey.title or "ايضاح"
        survey_id = str(survey.id)

        thread = threading.Thread(
            target=_send_reminder_batch,
            args=(group_buckets, direct_emails, survey_title, survey_id),
            daemon=True,
        )
        thread.start()

        recipient_count = sum(len(b['to']) for b in group_buckets) + len(direct_emails)
        logger.info(
            f"Queued reminder for survey {survey_id}: "
            f"{len(group_buckets)} group message(s), {len(direct_emails)} direct message(s), "
            f"{recipient_count} non-responder(s) total"
        )
        return recipient_count

    except Exception as e:
        logger.error(f"Error initiating survey reminder notification: {e}")
        return 0


# ---------------------------------------------------------------------------
# Follow-up email notifications
# ---------------------------------------------------------------------------

def _get_followup_url(thread_id: str) -> str:
    """Build the frontend URL for a follow-up thread."""
    base = FRONTEND_BASE_URL.rstrip('/')
    return f"{base}/my-follow-ups/{thread_id}"


def _build_followup_email_html(
    heading: str,
    body_paragraphs: list[str],
    button_label: str,
    button_url: str,
    survey_title: str | None = None,
) -> str:
    """
    Reusable RTL HTML email template for follow-up notifications.
    Matches the survey sharing email theme (gold header, same fonts/colors).
    """
    survey_block = ''
    if survey_title:
        survey_block = f'''
        <div class="survey-title">
            <span>{survey_title}</span>
        </div>'''

    body_html = ''.join(f'<p>{p}</p>' for p in body_paragraphs)

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
.message-box {{ background-color: #F8F6F0; border-right: 4px solid #B78A41; padding: 14px 16px; border-radius: 8px; margin: 20px 0; color: #4D4D4F; font-size: 14px; line-height: 1.8; white-space: pre-wrap; }}
.btn-container {{ text-align: center; margin: 32px 0; }}
.btn {{ display: inline-block; background: linear-gradient(135deg, #B78A41 0%, #A17D23 100%); color: #ffffff; text-decoration: none; padding: 14px 40px; border-radius: 8px; font-size: 16px; font-weight: bold; }}
.footer {{ background-color: #F8F6F0; padding: 16px 24px; text-align: center; border-top: 1px solid #E5E8E1; }}
.footer p {{ color: #808285; font-size: 12px; margin: 4px 0; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{heading}</h1>
    </div>
    <div class="content">
        {body_html}
        {survey_block}
        <div class="btn-container">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto; border-collapse: separate;">
                <tr>
                    <td align="center" bgcolor="#B78A41" style="border-radius: 8px; mso-padding-alt: 0;">
                        <a href="{button_url}" class="btn" style="display: inline-block; padding: 14px 40px; font-size: 16px; font-weight: bold; color: #ffffff; text-decoration: none; background: #B78A41; border: 1px solid #A17D23; border-radius: 8px; line-height: 1.2;">
                            {button_label}
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


def _build_followup_email_plain(paragraphs: list[str], button_label: str, button_url: str) -> str:
    """Plain text fallback for follow-up emails."""
    text = '\n'.join(paragraphs)
    return f"{text}\n\n{button_label}: {button_url}\n\n---\nنظام الايضاحات - إدارة المالية - دائرة القضاء"


def _send_followup_email(to_email: str, subject: str, html_body: str, plain_body: str):
    """Send a single follow-up email (runs in background thread)."""
    from_email = settings.DEFAULT_FROM_EMAIL
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[to_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()
        logger.info(f"Follow-up email sent to {to_email}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send follow-up email to {to_email}: {e}")


def _send_followup_email_async(to_email: str, subject: str, html_body: str, plain_body: str):
    """Send follow-up email in background thread."""
    thread = threading.Thread(
        target=_send_followup_email,
        args=(to_email, subject, html_body, plain_body),
        daemon=True,
    )
    thread.start()


def notify_followup_opened(thread, admin_user):
    """
    Email the respondent when an admin opens a new follow-up on their response.
    """
    try:
        respondent = thread.response.respondent
        if not respondent or not respondent.email:
            return

        survey_title = thread.response.survey.title or 'ايضاح'
        thread_url = _get_followup_url(str(thread.id))
        first_message = thread.messages.first()
        message_preview = first_message.body[:300] if first_message else ''

        subject = f"متابعة جديدة على ردك: {survey_title}"
        paragraphs = [
            'مرحباً،',
            f'تم فتح متابعة جديدة على ردك في ايضاح <strong>{survey_title}</strong> بواسطة <strong>قسم التخطيط والموازنة - إدارة المالية</strong>.',
        ]

        html_body = _build_followup_email_html(
            heading='متابعة جديدة',
            body_paragraphs=paragraphs,
            button_label='عرض المتابعة',
            button_url=thread_url,
        )
        # Insert message preview box before the button
        if message_preview:
            preview_block = f'<div class="message-box">{message_preview}</div>'
            html_body = html_body.replace(
                '<div class="btn-container">',
                f'{preview_block}\n        <div class="btn-container">',
            )

        plain_paragraphs = [
            'مرحباً،',
            f'تم فتح متابعة جديدة على ردك في ايضاح "{survey_title}".',
            f'الرسالة: {message_preview}' if message_preview else '',
        ]
        plain_body = _build_followup_email_plain(
            [p for p in plain_paragraphs if p],
            'عرض المتابعة',
            thread_url,
        )

        _send_followup_email_async(respondent.email, subject, html_body, plain_body)
    except Exception as e:
        logger.error(f"Error sending follow-up opened email: {e}")


def notify_followup_reply(thread, message, sender_user):
    """
    Email notification when a message is posted in a follow-up thread.
    - If respondent replies → email the admin who opened the thread.
    - If admin sends a message → email the respondent.
    """
    try:
        respondent = thread.response.respondent
        is_respondent = (
            respondent and sender_user.pk == respondent.pk
        )

        if is_respondent:
            # Respondent replied → email the admin who opened the thread
            recipient = thread.opened_by or thread.response.survey.creator
            if not recipient or not recipient.email:
                return
            to_email = recipient.email
            survey_title = thread.response.survey.title or 'ايضاح'
            thread_url = _get_followup_url(str(thread.id))

            subject = f"رد جديد على المتابعة: {survey_title}"
            paragraphs = [
                'مرحباً،',
                f'قام <strong>{respondent.email}</strong> بالرد على المتابعة الخاصة بايضاح <strong>{survey_title}</strong>.',
            ]
            heading = 'رد جديد على المتابعة'
            button_label = 'عرض المتابعة'
        else:
            # Admin sent a message → email the respondent
            if not respondent or not respondent.email:
                return
            to_email = respondent.email
            survey_title = thread.response.survey.title or 'ايضاح'
            thread_url = _get_followup_url(str(thread.id))

            subject = f"رسالة جديدة في المتابعة: {survey_title}"
            paragraphs = [
                'مرحباً،',
                f'لديك رسالة جديدة في المتابعة الخاصة بايضاح <strong>{survey_title}</strong> من <strong>قسم التخطيط والموازنة - إدارة المالية</strong>.',
            ]
            heading = 'رسالة جديدة في المتابعة'
            button_label = 'عرض المتابعة'

        message_preview = message.body[:300] if message.body else ''

        html_body = _build_followup_email_html(
            heading=heading,
            body_paragraphs=paragraphs,
            button_label=button_label,
            button_url=thread_url,
            # survey_title=survey_title,
        )
        if message_preview:
            preview_block = f'<div class="message-box">{message_preview}</div>'
            html_body = html_body.replace(
                '<div class="btn-container">',
                f'{preview_block}\n        <div class="btn-container">',
            )

        plain_paragraphs = [p.replace('<strong>', '').replace('</strong>', '') for p in paragraphs]
        if message_preview:
            plain_paragraphs.append(f'الرسالة: {message_preview}')
        plain_body = _build_followup_email_plain(plain_paragraphs, button_label, thread_url)

        _send_followup_email_async(to_email, subject, html_body, plain_body)
    except Exception as e:
        logger.error(f"Error sending follow-up reply email: {e}")


def notify_followup_decision(thread):
    """
    Email the respondent when the admin accepts or rejects the follow-up.
    """
    try:
        respondent = thread.response.respondent
        if not respondent or not respondent.email:
            return

        survey_title = thread.response.survey.title or 'ايضاح'
        thread_url = _get_followup_url(str(thread.id))
        decision = thread.status  # 'accepted' or 'rejected'
        reason = thread.decision_reason or ''

        if decision == 'accepted':
            subject = f"تم قبول إجابتك: {survey_title}"
            heading = 'تم قبول إجابتك'
            paragraphs = [
                'مرحباً،',
                f'تم <strong>قبول</strong> إجابتك في المتابعة الخاصة بايضاح <strong>{survey_title}</strong>.',
            ]
        else:
            subject = f"تم رفض إجابتك: {survey_title}"
            heading = 'تم رفض إجابتك'
            paragraphs = [
                'مرحباً،',
                f'تم <strong>رفض</strong> إجابتك في المتابعة الخاصة بايضاح <strong>{survey_title}</strong>.',
            ]

        if reason:
            paragraphs.append(f'السبب: {reason}')

        html_body = _build_followup_email_html(
            heading=heading,
            body_paragraphs=paragraphs,
            button_label='عرض المتابعة',
            button_url=thread_url,
            # survey_title=survey_title,
        )
        plain_paragraphs = [p.replace('<strong>', '').replace('</strong>', '') for p in paragraphs]
        plain_body = _build_followup_email_plain(plain_paragraphs, 'عرض المتابعة', thread_url)

        _send_followup_email_async(respondent.email, subject, html_body, plain_body)
    except Exception as e:
        logger.error(f"Error sending follow-up decision email: {e}")


# ---------------------------------------------------------------------------
# New-response notification (sent to survey creator on every submission)
# ---------------------------------------------------------------------------

def _get_responses_url(survey_id: str) -> str:
    """Build the frontend admin URL for viewing survey responses."""
    base = FRONTEND_BASE_URL.rstrip('/')
    return f"{base}/control/surveys/{survey_id}/responses"


def _build_response_notification_html(
    survey_title: str,
    respondent_label: str,
    answer_count: int,
    responses_url: str,
    creator_name: str,
) -> str:
    """
    RTL HTML email notifying the survey creator that a new response was submitted.
    Matches the existing gold-header theme used throughout this module.
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
.meta-row {{ display: flex; justify-content: space-between; background-color: #F8F6F0; border-radius: 8px; padding: 10px 16px; margin: 8px 0; font-size: 14px; color: #4D4D4F; }}
.meta-label {{ color: #808285; font-size: 13px; }}
.meta-value {{ font-weight: 600; color: #231F20; }}
.btn-container {{ text-align: center; margin: 32px 0; }}
.btn {{ display: inline-block; background: linear-gradient(135deg, #B78A41 0%, #A17D23 100%); color: #ffffff; text-decoration: none; padding: 14px 40px; border-radius: 8px; font-size: 16px; font-weight: bold; }}
.footer {{ background-color: #F8F6F0; padding: 16px 24px; text-align: center; border-top: 1px solid #E5E8E1; }}
.footer p {{ color: #808285; font-size: 12px; margin: 4px 0; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>رد جديد على الإيضاح</h1>
    </div>
    <div class="content">
        <p>مرحباً : {creator_name}</p>
        <p>تم استلام رد جديد على الإيضاح</p>
        <div class="survey-title">
            <span>{survey_title}</span>
        </div>
        <table width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse: collapse; margin: 16px 0;">
            <tr>
                <td style="background-color: #F8F6F0; border-radius: 8px 8px 0 0; padding: 10px 16px; border-bottom: 1px solid #E5E8E1;">
                    <span class="meta-label">المشارك</span><br>
                    <span class="meta-value">{respondent_label}</span>
                </td>
            </tr>
            <tr>
                <td style="background-color: #F8F6F0; border-radius: 0 0 8px 8px; padding: 10px 16px;">
                    <span class="meta-label">عدد الإجابات</span><br>
                    <span class="meta-value">{answer_count}</span>
                </td>
            </tr>
        </table>
        <div class="btn-container">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto; border-collapse: separate;">
                <tr>
                    <td align="center" bgcolor="#B78A41" style="border-radius: 8px; mso-padding-alt: 0;">
                        <a href="{responses_url}" class="btn" style="display: inline-block; padding: 14px 40px; font-size: 16px; font-weight: bold; color: #ffffff; text-decoration: none; background: #B78A41; border: 1px solid #A17D23; border-radius: 8px; line-height: 1.2;">
                            عرض الردود
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


def _build_response_notification_plain(
    survey_title: str,
    respondent_label: str,
    answer_count: int,
    responses_url: str,
) -> str:
    """Plain-text fallback for the new-response notification email."""
    return (
        f"مرحباً،\n\n"
        f"تم استلام رد جديد على الإيضاح: {survey_title}\n\n"
        f"المشارك: {respondent_label}\n"
        f"عدد الإجابات: {answer_count}\n\n"
        f"لعرض الردود: {responses_url}\n\n"
        f"---\n"
        f"نظام الايضاحات - إدارة المالية - دائرة القضاء"
    )


def _send_response_notification(
    creator_email: str,
    creator_name: str,
    survey_title: str,
    respondent_label: str,
    answer_count: int,
    responses_url: str,
) -> None:
    """Send a single new-response notification email (runs in background thread)."""
    subject = f"رد جديد على الإيضاح: {survey_title}"
    html_body = _build_response_notification_html(
        survey_title, respondent_label, answer_count, responses_url, creator_name
    )
    plain_body = _build_response_notification_plain(
        survey_title, respondent_label, answer_count, responses_url
    )
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[creator_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()
        logger.info(f"New-response notification sent to creator {creator_email} for survey '{survey_title}'")
    except Exception as e:
        logger.error(f"Failed to send new-response notification to {creator_email}: {e}")


def notify_creator_of_new_response(survey, survey_response) -> None:
    """
    Fire-and-forget: email the survey creator when a new response is submitted.
    Runs in a daemon thread so the submission endpoint returns immediately.

    Skipped if:
    - The survey has no creator or creator has no email address.
    - The creator submitted their own survey (no self-notification noise).
    """
    try:
        creator = getattr(survey, 'creator', None)
        if not creator or not getattr(creator, 'email', None):
            return

        # Skip self-submissions
        respondent = getattr(survey_response, 'respondent', None)
        if respondent and respondent.pk == creator.pk:
            return

        survey_title = survey.title or 'ايضاح'
        survey_id = str(survey.id)
        creator_name = getattr(creator, 'full_name', '') or creator.email

        # Build a human-readable respondent label
        if survey_response.is_group_submission:
            group = getattr(survey_response, 'submitted_via_group', None)
            group_name = group.name if group else ''
            respondent_label = f"مستخدم مسجل{' - ' + group_name if group_name else ''}"
        elif respondent:
            full_name = getattr(respondent, 'full_name', '') or ''
            respondent_label = full_name if full_name and full_name != respondent.email else respondent.email
        else:
            respondent_label = (
                getattr(survey_response, 'respondent_email', None)
                or getattr(survey_response, 'respondent_phone', None)
                or 'مستخدم مجهول'
            )

        answer_count = survey_response.answers.count()
        responses_url = _get_responses_url(survey_id)

        thread = threading.Thread(
            target=_send_response_notification,
            args=(creator.email, creator_name, survey_title, respondent_label, answer_count, responses_url),
            daemon=True,
        )
        thread.start()

        logger.info(
            f"Queued new-response notification to creator {creator.email} "
            f"for survey {survey_id}"
        )
    except Exception as e:
        logger.error(f"Error queuing new-response notification: {e}")
