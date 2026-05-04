"""
Follow-up thread ViewSet for admin ↔ respondent conversations.
Endpoint prefix: /api/surveys/follow-ups/
"""

import logging
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response as DRFResponse

from .models import Response as SurveyResponse, ResponseFollowUp, FollowUpMessage
from .permissions import IsFollowUpParticipant
from .followup_presets import PRESETS
from .views import can_user_manage_survey

logger = logging.getLogger(__name__)

ADMIN_ROLES = ('admin', 'manager', 'super_admin')


def _notify(recipient, notification_type, title_ar, title_en, body_text, metadata, sender=None):
    """Fire a notification without blocking the response if it fails."""
    try:
        from notifications.services import NotificationService
        from notifications.models import Notification
        NotificationService.create_notification(
            recipient=recipient,
            title={'ar': title_ar, 'en': title_en},
            body={'ar': body_text, 'en': body_text},
            notification_type=notification_type,
            sender=sender,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.warning("Follow-up notification failed: %s", exc)


class FollowUpSerializer:
    """Lightweight dict-based serializer (avoids importing DRF serializers at module level)."""

    @staticmethod
    def thread(thread: ResponseFollowUp) -> dict:
        messages = [
            {
                'id': str(m.id),
                'sender_email': m.sender.email if m.sender else None,
                'sender_role': m.sender_role,
                'body': m.body,
                'is_preset': m.is_preset,
                'preset_key': m.preset_key,
                'created_at': m.created_at.isoformat(),
                'read_at': m.read_at.isoformat() if m.read_at else None,
            }
            for m in thread.messages.all()
        ]
        return {
            'id': str(thread.id),
            'response_id': str(thread.response_id),
            'response_summary': {
                'survey_title': thread.response.survey.title,
                'submitted_at': thread.response.submitted_at.isoformat(),
            },
            'opened_by': thread.opened_by.email if thread.opened_by else None,
            'status': thread.status,
            'decision_reason': thread.decision_reason,
            'decided_by': thread.decided_by.email if thread.decided_by else None,
            'decided_at': thread.decided_at.isoformat() if thread.decided_at else None,
            'created_at': thread.created_at.isoformat(),
            'updated_at': thread.updated_at.isoformat(),
            'messages': messages,
        }

    @staticmethod
    def message(msg: FollowUpMessage) -> dict:
        return {
            'id': str(msg.id),
            'sender_email': msg.sender.email if msg.sender else None,
            'sender_role': msg.sender_role,
            'body': msg.body,
            'is_preset': msg.is_preset,
            'preset_key': msg.preset_key,
            'created_at': msg.created_at.isoformat(),
            'read_at': msg.read_at.isoformat() if msg.read_at else None,
        }


class FollowUpViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    """
    Follow-up threads between admin and authenticated respondents.

    Routes:
      GET    /follow-ups/                              list (scoped by role)
      GET    /follow-ups/{id}/                         retrieve
      POST   /follow-ups/open-on-response/{rid}/       open new thread
      POST   /follow-ups/{id}/messages/                send message
      POST   /follow-ups/{id}/decision/                admin accept / reject
      POST   /follow-ups/{id}/mark-read/               mark messages read
      GET    /follow-ups/presets/                      preset library
    """

    permission_classes = [IsAuthenticated, IsFollowUpParticipant]

    def get_queryset(self):
        user = self.request.user
        qs = ResponseFollowUp.objects.select_related(
            'response__survey', 'response__respondent',
            'opened_by', 'decided_by',
        ).prefetch_related('messages__sender')

        role = getattr(user, 'role', None)
        if role == 'super_admin':
            pass
        elif role in ('admin', 'manager'):
            qs = qs.filter(response__survey__creator=user)
        else:
            qs = qs.filter(response__respondent=user)

        status_params = self.request.query_params.getlist('status')
        if status_params:
            qs = qs.filter(status__in=status_params)

        return qs.order_by('-updated_at')

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        data = [FollowUpSerializer.thread(t) for t in qs]
        return DRFResponse({'results': data, 'count': len(data)})

    def retrieve(self, request, *args, **kwargs):
        thread = get_object_or_404(self.get_queryset(), pk=kwargs['pk'])
        self.check_object_permissions(request, thread)
        return DRFResponse(FollowUpSerializer.thread(thread))

    @action(detail=False, methods=['post'], url_path=r'open-on-response/(?P<response_id>[^/.]+)')
    def open_on_response(self, request, response_id=None):
        """Admin opens a new follow-up thread on an authenticated response."""
        survey_response = get_object_or_404(
            SurveyResponse.objects.select_related('survey', 'respondent'),
            pk=response_id,
        )

        # Only authenticated respondents can receive follow-ups
        if not survey_response.respondent_id:
            return DRFResponse(
                {'error': 'anonymous_responder_not_supported'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only admins who can manage the survey may open threads
        if not can_user_manage_survey(request.user, survey_response.survey):
            return DRFResponse({'error': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)

        body = request.data.get('initial_message', '').strip()
        preset_key = request.data.get('preset_key', '')
        if not body:
            return DRFResponse({'error': 'message_required'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            thread = ResponseFollowUp.objects.create(
                response=survey_response,
                opened_by=request.user,
                status=ResponseFollowUp.STATUS_PENDING_REPLY,
            )
            FollowUpMessage.objects.create(
                thread=thread,
                sender=request.user,
                sender_role=FollowUpMessage.SENDER_ADMIN,
                body=body,
                is_preset=bool(preset_key),
                preset_key=preset_key,
            )

        _notify(
            recipient=survey_response.respondent,
            notification_type='followup_opened',
            title_ar='ADJD Team طلب توضيحاً على ردك',
            title_en='ADJD Team requested clarification on your response',
            body_text=body[:200],
            metadata={'thread_id': str(thread.id), 'response_id': str(survey_response.id)},
            sender=request.user,
        )

        thread.refresh_from_db()
        return DRFResponse(FollowUpSerializer.thread(thread), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='messages')
    def post_message(self, request, pk=None):
        """Send a message within an existing thread."""
        thread = get_object_or_404(
            ResponseFollowUp.objects.select_related('response__survey', 'response__respondent'),
            pk=pk,
        )
        self.check_object_permissions(request, thread)

        if thread.status in (
            ResponseFollowUp.STATUS_ACCEPTED,
            ResponseFollowUp.STATUS_REJECTED,
            ResponseFollowUp.STATUS_CLOSED,
        ):
            return DRFResponse({'error': 'thread_closed'}, status=status.HTTP_409_CONFLICT)

        body = request.data.get('body', '').strip()
        if not body:
            return DRFResponse({'error': 'message_required'}, status=status.HTTP_400_BAD_REQUEST)

        role = getattr(request.user, 'role', None)
        is_admin = role in ADMIN_ROLES
        sender_role = FollowUpMessage.SENDER_ADMIN if is_admin else FollowUpMessage.SENDER_RESPONDER

        with transaction.atomic():
            msg = FollowUpMessage.objects.create(
                thread=thread,
                sender=request.user,
                sender_role=sender_role,
                body=body,
            )
            if sender_role == FollowUpMessage.SENDER_RESPONDER and thread.status == ResponseFollowUp.STATUS_PENDING_REPLY:
                thread.status = ResponseFollowUp.STATUS_REPLIED
                thread.save(update_fields=['status', 'updated_at'])

        # Notify the other party
        if is_admin:
            recipient = thread.response.respondent
            title_ar = 'رسالة جديدة من فريق ADJD في متابعة'
            title_en = 'New message from ADJD Team in your follow-up'
        else:
            recipient = thread.response.survey.creator
            title_ar = 'رسالة جديدة في متابعة'
            title_en = 'New message in follow-up thread'

        if recipient:
            _notify(
                recipient=recipient,
                notification_type='followup_message',
                title_ar=title_ar,
                title_en=title_en,
                body_text=body[:200],
                metadata={'thread_id': str(thread.id)},
                sender=request.user,
            )

        return DRFResponse(FollowUpSerializer.message(msg), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='decision')
    def decision(self, request, pk=None):
        """Admin accepts or rejects a follow-up thread."""
        thread = get_object_or_404(
            ResponseFollowUp.objects.select_related('response__respondent'),
            pk=pk,
        )
        self.check_object_permissions(request, thread)

        role = getattr(request.user, 'role', None)
        if role not in ADMIN_ROLES:
            return DRFResponse({'error': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)

        if thread.status not in (ResponseFollowUp.STATUS_REPLIED, ResponseFollowUp.STATUS_PENDING_REPLY):
            return DRFResponse(
                {'error': 'cannot_decide_in_current_state', 'state': thread.status},
                status=status.HTTP_409_CONFLICT,
            )

        decision = request.data.get('decision')
        reason = request.data.get('reason', '')
        if decision not in ('accepted', 'rejected'):
            return DRFResponse({'error': 'invalid_decision'}, status=status.HTTP_400_BAD_REQUEST)

        thread.status = decision
        thread.decision_reason = reason
        thread.decided_by = request.user
        thread.decided_at = timezone.now()
        thread.save(update_fields=['status', 'decision_reason', 'decided_by', 'decided_at', 'updated_at'])

        respondent = thread.response.respondent
        if respondent:
            if decision == 'accepted':
                title_ar, title_en = 'تم قبول إجابتك', 'Your response has been accepted'
            else:
                title_ar, title_en = 'تم رفض إجابتك', 'Your response has been rejected'
            _notify(
                recipient=respondent,
                notification_type=f'followup_{decision}',
                title_ar=title_ar,
                title_en=title_en,
                body_text=reason[:200] if reason else '',
                metadata={'thread_id': str(thread.id)},
                sender=request.user,
            )

        thread.refresh_from_db()
        return DRFResponse(FollowUpSerializer.thread(thread))

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        """Mark messages from the other party as read."""
        thread = get_object_or_404(ResponseFollowUp, pk=pk)
        self.check_object_permissions(request, thread)

        role = getattr(request.user, 'role', None)
        other_role = (
            FollowUpMessage.SENDER_RESPONDER
            if role in ADMIN_ROLES
            else FollowUpMessage.SENDER_ADMIN
        )
        FollowUpMessage.objects.filter(
            thread=thread,
            sender_role=other_role,
            read_at__isnull=True,
        ).update(read_at=timezone.now())

        return DRFResponse({'ok': True})

    @action(detail=False, methods=['get'], url_path='presets')
    def presets(self, request):
        """Return the preset follow-up message library."""
        lang = request.query_params.get('lang', 'ar')
        result = [
            {'key': k, 'text': v.get(lang, v['ar'])}
            for k, v in PRESETS.items()
        ]
        return DRFResponse(result)
