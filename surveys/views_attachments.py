"""
Attachment views for survey responses and follow-up messages.
Supports upload (POST multipart), list (GET), download (GET binary), delete (DELETE).
Storage: BLOB in database (no filesystem).
"""

import logging
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response as DRFResponse
from rest_framework.views import APIView

from authentication.dual_auth import UniversalAuthentication
from .models import (
    Survey,
    Response as SurveyResponse,
    ResponseAttachment,
    FollowUpMessage,
    FollowUpMessageAttachment,
    ResponseFollowUp,
)
from .serializers import (
    AttachmentUploadSerializer,
    ResponseAttachmentSerializer,
    FollowUpMessageAttachmentSerializer,
)
from .attachment_utils import (
    process_attachment_upload,
    MAX_ATTACHMENTS_PER_SUBMISSION,
)

logger = logging.getLogger(__name__)


def _uniform(success, message, data=None, status_code=200):
    return DRFResponse(
        {'status': 'success' if success else 'error', 'message': message, 'data': data},
        status=status_code,
    )


# =============================================================================
# Response Attachments
# =============================================================================


class ResponseAttachmentUploadView(APIView):
    """
    POST /api/surveys/responses/<response_id>/attachments/upload/
    Upload attachment to a survey response. Supports both authenticated and public uploads.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request, response_id):
        response_obj = get_object_or_404(SurveyResponse, pk=response_id)

        # Check if survey allows attachments
        if response_obj.survey.allow_attachments == 'none':
            return _uniform(
                False,
                'هذا الاستبيان لا يسمح بإرفاق ملفات',  # This survey does not allow attachments
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Enforce max attachments per submission
        current_count = ResponseAttachment.objects.filter(response=response_obj).count()
        if current_count >= MAX_ATTACHMENTS_PER_SUBMISSION:
            return _uniform(
                False,
                f'تم الوصول إلى الحد الأقصى ({MAX_ATTACHMENTS_PER_SUBMISSION}) من المرفقات لهذه الاستجابة',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AttachmentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return _uniform(
                False,
                'بيانات الملف غير صالحة',  # Invalid file data
                data={'errors': serializer.errors},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = serializer.validated_data['file']
        description = serializer.validated_data.get('description', '')

        processed = process_attachment_upload(file_obj)

        attachment = ResponseAttachment.objects.create(
            response=response_obj,
            file_data=processed['file_data'],
            original_filename=processed['original_filename'],
            file_size=processed['file_size'],
            mime_type=processed['mime_type'],
            description=description,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        out_serializer = ResponseAttachmentSerializer(attachment, context={'request': request})
        logger.info(
            "Attachment uploaded: %s for response %s by %s",
            attachment.id, response_id, request.user if request.user.is_authenticated else 'anonymous',
        )
        return _uniform(
            True,
            'تم رفع المرفق بنجاح',  # Attachment uploaded successfully
            data={'attachment': out_serializer.data},
            status_code=status.HTTP_201_CREATED,
        )


class ResponseAttachmentListView(APIView):
    """
    GET /api/surveys/responses/<response_id>/attachments/
    List all attachments for a survey response.
    """
    permission_classes = [AllowAny]

    def get(self, request, response_id):
        response_obj = get_object_or_404(SurveyResponse, pk=response_id)
        attachments = ResponseAttachment.objects.filter(response=response_obj).order_by('-uploaded_at')
        serializer = ResponseAttachmentSerializer(attachments, many=True, context={'request': request})
        return _uniform(
            True,
            'تم جلب المرفقات بنجاح',
            data={'attachments': serializer.data, 'count': attachments.count()},
        )


class ResponseAttachmentDownloadView(APIView):
    """
    GET /api/surveys/response-attachments/<pk>/download/
    Download a response attachment (binary stream).
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        attachment = get_object_or_404(ResponseAttachment, pk=pk)
        # Oracle returns BinaryField as LOB/memoryview — convert to bytes explicitly
        raw = attachment.file_data
        file_bytes = raw.read() if hasattr(raw, 'read') else bytes(raw)
        response = HttpResponse(file_bytes, content_type=attachment.mime_type)
        # Force download for documents, inline for images
        if attachment.mime_type.startswith('image/'):
            disposition = 'inline'
        else:
            disposition = 'attachment'
        response['Content-Disposition'] = f'{disposition}; filename="{attachment.original_filename}"'
        response['Content-Length'] = attachment.file_size
        return response


class ResponseAttachmentDeleteView(APIView):
    """
    DELETE /api/surveys/response-attachments/<pk>/
    Delete a response attachment.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        attachment = get_object_or_404(ResponseAttachment, pk=pk)

        # Only super_admin or the survey creator can delete response attachments
        is_superadmin = getattr(request.user, 'role', None) == 'super_admin'
        survey_creator_id = attachment.response.survey.creator_id
        is_survey_creator = survey_creator_id is not None and survey_creator_id == request.user.id

        if not (is_superadmin or is_survey_creator):
            return _uniform(
                False,
                'ليس لديك صلاحية حذف هذا المرفق',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        attachment_id = str(attachment.id)
        attachment.delete()
        logger.info("Attachment deleted: %s by %s", attachment_id, request.user.email)
        return _uniform(True, 'تم حذف المرفق بنجاح', status_code=status.HTTP_200_OK)


# =============================================================================
# Follow-Up Message Attachments
# =============================================================================


class FollowUpAttachmentUploadView(APIView):
    """
    POST /api/surveys/follow-ups/<thread_id>/messages/<message_id>/attachments/upload/
    Upload attachment to a follow-up message.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, thread_id, message_id):
        thread = get_object_or_404(ResponseFollowUp, pk=thread_id)
        message = get_object_or_404(FollowUpMessage, pk=message_id, thread=thread)

        # Only the message sender can attach files to their message
        if message.sender != request.user:
            return _uniform(
                False,
                'يمكنك فقط إرفاق ملفات برسائلك الخاصة',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Max attachments per message
        current_count = FollowUpMessageAttachment.objects.filter(message=message).count()
        if current_count >= MAX_ATTACHMENTS_PER_SUBMISSION:
            return _uniform(
                False,
                f'تم الوصول إلى الحد الأقصى ({MAX_ATTACHMENTS_PER_SUBMISSION}) من المرفقات لهذه الرسالة',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AttachmentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return _uniform(
                False,
                'بيانات الملف غير صالحة',
                data={'errors': serializer.errors},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = serializer.validated_data['file']
        description = serializer.validated_data.get('description', '')

        processed = process_attachment_upload(file_obj)

        attachment = FollowUpMessageAttachment.objects.create(
            message=message,
            file_data=processed['file_data'],
            original_filename=processed['original_filename'],
            file_size=processed['file_size'],
            mime_type=processed['mime_type'],
            description=description,
            uploaded_by=request.user,
        )

        out_serializer = FollowUpMessageAttachmentSerializer(attachment, context={'request': request})
        logger.info(
            "Follow-up attachment uploaded: %s for message %s by %s",
            attachment.id, message_id, request.user.email,
        )
        return _uniform(
            True,
            'تم رفع المرفق بنجاح',
            data={'attachment': out_serializer.data},
            status_code=status.HTTP_201_CREATED,
        )


class FollowUpAttachmentDownloadView(APIView):
    """
    GET /api/surveys/follow-up-attachments/<pk>/download/
    Download a follow-up message attachment.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        attachment = get_object_or_404(FollowUpMessageAttachment, pk=pk)

        # Must be a participant of the thread
        thread = attachment.message.thread
        is_respondent = (
            thread.response.respondent_id is not None
            and thread.response.respondent_id == request.user.pk
        )
        is_admin = getattr(request.user, 'role', None) in ('admin', 'manager', 'super_admin')
        is_opener = thread.opened_by == request.user

        if not (is_respondent or is_admin or is_opener):
            return _uniform(
                False,
                'ليس لديك صلاحية لتحميل هذا المرفق',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Oracle returns BinaryField as LOB/memoryview — convert to bytes explicitly
        raw = attachment.file_data
        file_bytes = raw.read() if hasattr(raw, 'read') else bytes(raw)
        response = HttpResponse(file_bytes, content_type=attachment.mime_type)
        if attachment.mime_type.startswith('image/'):
            disposition = 'inline'
        else:
            disposition = 'attachment'
        response['Content-Disposition'] = f'{disposition}; filename="{attachment.original_filename}"'
        response['Content-Length'] = attachment.file_size
        return response


class FollowUpAttachmentDeleteView(APIView):
    """
    DELETE /api/surveys/follow-up-attachments/<pk>/
    Delete a follow-up message attachment.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        attachment = get_object_or_404(FollowUpMessageAttachment, pk=pk)

        # Only the uploader can delete their follow-up attachments
        is_owner = attachment.uploaded_by == request.user

        if not is_owner:
            return _uniform(
                False,
                'ليس لديك صلاحية حذف هذا المرفق',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        attachment_id = str(attachment.id)
        attachment.delete()
        logger.info("Follow-up attachment deleted: %s by %s", attachment_id, request.user.email)
        return _uniform(True, 'تم حذف المرفق بنجاح', status_code=status.HTTP_200_OK)
