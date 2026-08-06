"""
Test cases for survey reference attachments.

Covers the files a survey CREATOR pins to a survey so respondents can read
them while answering: upload rules, permissions, listing, download
disposition, the per-survey cap, clone copying and cascade cleanup.
"""

import io
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from surveys.models import Survey, SurveyAttachment
from surveys.serializers import (
    AttachmentUploadSerializer,
    SurveyAttachmentUploadSerializer,
    SurveySerializer,
)
from surveys.views import CloneSurveyView
from surveys.views_attachments import (
    SurveyAttachmentDeleteView,
    SurveyAttachmentDownloadView,
    SurveyAttachmentListView,
    SurveyAttachmentUploadView,
)

User = get_user_model()

PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)

PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def make_ooxml(name, inner_path, content_type):
    """Build a minimal OOXML file — a ZIP container, as Office really is."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<xml/>')
        archive.writestr(inner_path, '<x/>')
    return SimpleUploadedFile(name, buf.getvalue(), content_type=content_type)


def make_pptx(name='deck.pptx'):
    return make_ooxml(name, 'ppt/presentation.xml', PPTX_MIME)


def make_docx(name='report.docx'):
    return make_ooxml(name, 'word/document.xml', DOCX_MIME)


def make_png(name='image.png'):
    return SimpleUploadedFile(name, PNG_BYTES, content_type='image/png')


class SurveyAttachmentTestBase(TestCase):
    """Shared fixtures: a survey owner and an unrelated user."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.creator = User.objects.create_user(
            username='creator@example.com',
            email='creator@example.com',
            password='testpass123',
            role='admin',
        )
        self.other = User.objects.create_user(
            username='other@example.com',
            email='other@example.com',
            password='testpass123',
            role='user',
        )
        self.survey = Survey.objects.create(
            title='Attachment Survey',
            description='Survey with reference files',
            creator=self.creator,
            visibility='AUTH',
            status='draft',
        )

    def upload(self, uploaded_file, user=None, description=None):
        payload = {'file': uploaded_file}
        if description:
            payload['description'] = description
        request = self.factory.post(
            f'/api/surveys/surveys/{self.survey.id}/attachments/upload/',
            payload,
            format='multipart',
        )
        force_authenticate(request, user=self.creator if user is None else user)
        return SurveyAttachmentUploadView.as_view()(request, survey_id=str(self.survey.id))


class SurveyAttachmentUploadTests(SurveyAttachmentTestBase):
    """Upload validation and permission rules"""

    def test_creator_can_upload_powerpoint(self):
        """PowerPoint is accepted for survey attachments"""
        response = self.upload(make_pptx(), description='عرض تقديمي مهم')

        self.assertEqual(response.status_code, 201)
        attachment = response.data['data']['attachment']
        self.assertEqual(attachment['mime_type'], PPTX_MIME)
        self.assertEqual(attachment['format_name'], 'PowerPoint (PPTX)')
        self.assertFalse(attachment['is_image'])
        self.assertFalse(attachment['is_inline_viewable'])
        self.assertEqual(attachment['description'], 'عرض تقديمي مهم')

    def test_ooxml_container_is_resolved_from_extension(self):
        """docx/xlsx detect as application/zip — extension must resolve the real type"""
        response = self.upload(make_docx('تقرير.docx'))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data']['attachment']['mime_type'], DOCX_MIME)

    def test_image_is_flagged_for_preview(self):
        """Images are flagged so the UI can offer the eye/preview action"""
        response = self.upload(make_png('مخطط الطابق.png'))

        self.assertEqual(response.status_code, 201)
        attachment = response.data['data']['attachment']
        self.assertTrue(attachment['is_image'])
        self.assertTrue(attachment['is_inline_viewable'])
        self.assertEqual(attachment['original_filename'], 'مخطط الطابق.png')

    def test_executable_is_rejected(self):
        """Forbidden extensions are refused"""
        response = self.upload(
            SimpleUploadedFile('evil.exe', b'MZ\x90\x00' * 64, content_type='application/x-msdownload')
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(SurveyAttachment.objects.filter(survey=self.survey).count(), 0)

    def test_uploads_are_ordered_by_arrival(self):
        """display_order increments so the creator's ordering is stable"""
        first = self.upload(make_png('a.png')).data['data']['attachment']
        second = self.upload(make_png('b.png')).data['data']['attachment']

        self.assertEqual(first['display_order'], 0)
        self.assertEqual(second['display_order'], 1)

    def test_non_creator_cannot_upload(self):
        """Only the creator (or a super admin) may attach files"""
        response = self.upload(make_png(), user=self.other)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(SurveyAttachment.objects.filter(survey=self.survey).count(), 0)

    def test_super_admin_can_upload(self):
        """Super admin can manage any survey"""
        super_admin = User.objects.create_user(
            username='super@example.com',
            email='super@example.com',
            password='testpass123',
            role='super_admin',
        )

        response = self.upload(make_png(), user=super_admin)

        self.assertEqual(response.status_code, 201)

    def test_per_survey_cap_is_enforced(self):
        """A survey holds at most MAX_ATTACHMENTS_PER_SURVEY files"""
        from surveys.attachment_utils import MAX_ATTACHMENTS_PER_SURVEY

        for index in range(MAX_ATTACHMENTS_PER_SURVEY):
            self.assertEqual(self.upload(make_png(f'f{index}.png')).status_code, 201)

        response = self.upload(make_png('over.png'))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            SurveyAttachment.objects.filter(survey=self.survey).count(),
            MAX_ATTACHMENTS_PER_SURVEY,
        )

    def test_locked_survey_rejects_upload(self):
        """A locked survey cannot be modified"""
        self.survey.is_locked = True
        self.survey.save(update_fields=['is_locked'])

        response = self.upload(make_png())

        self.assertEqual(response.status_code, 409)

    def test_powerpoint_still_rejected_for_response_attachments(self):
        """Widening survey types must not widen what respondents may upload"""
        self.assertFalse(AttachmentUploadSerializer(data={'file': make_pptx()}).is_valid())
        self.assertTrue(SurveyAttachmentUploadSerializer(data={'file': make_pptx()}).is_valid())

    def test_docx_accepted_for_response_attachments(self):
        """The OOXML container fix also unblocks respondent Word/Excel uploads"""
        self.assertTrue(AttachmentUploadSerializer(data={'file': make_docx()}).is_valid())


class SurveyAttachmentListTests(SurveyAttachmentTestBase):
    """Listing is open to respondents, including anonymous ones"""

    def test_anonymous_respondent_can_list(self):
        """Public/token respondents must be able to read the creator's files"""
        self.upload(make_png('a.png'))
        self.upload(make_pptx())

        request = self.factory.get(f'/api/surveys/surveys/{self.survey.id}/attachments/')
        response = SurveyAttachmentListView.as_view()(request, survey_id=str(self.survey.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['count'], 2)
        self.assertFalse(any(a['can_delete'] for a in response.data['data']['attachments']))

    def test_creator_sees_delete_permission(self):
        """can_delete reflects the caller, so the editor can show a remove button"""
        self.upload(make_png('a.png'))

        request = self.factory.get(f'/api/surveys/surveys/{self.survey.id}/attachments/')
        force_authenticate(request, user=self.creator)
        response = SurveyAttachmentListView.as_view()(request, survey_id=str(self.survey.id))

        self.assertTrue(response.data['data']['attachments'][0]['can_delete'])

    def test_deleted_survey_returns_404(self):
        """Soft-deleted surveys expose nothing"""
        self.upload(make_png('a.png'))
        self.survey.soft_delete()

        request = self.factory.get(f'/api/surveys/surveys/{self.survey.id}/attachments/')
        response = SurveyAttachmentListView.as_view()(request, survey_id=str(self.survey.id))

        self.assertEqual(response.status_code, 404)

    def _serialize_survey_as(self, user):
        request = self.factory.get(f'/api/surveys/surveys/{self.survey.id}/')
        force_authenticate(request, user=user)
        request.user = user
        return SurveySerializer(self.survey, context={'request': request}).data

    def test_survey_serializer_exposes_attachments_to_creator(self):
        """The editor loads existing attachments straight off the survey payload"""
        self.upload(make_png('a.png'))

        data = self._serialize_survey_as(self.creator)

        self.assertEqual(data['attachment_count'], 1)
        self.assertEqual(len(data['attachments']), 1)
        self.assertEqual(data['attachments'][0]['original_filename'], 'a.png')

    def test_respondent_limited_view_includes_attachments(self):
        """to_representation whitelists fields per role — respondents still get the files"""
        self.upload(make_png('a.png'))

        data = self._serialize_survey_as(self.other)

        self.assertEqual(data['attachment_count'], 1)
        self.assertEqual(len(data['attachments']), 1)
        self.assertFalse(data['attachments'][0]['can_delete'])


class SurveyAttachmentDownloadTests(SurveyAttachmentTestBase):
    """Download disposition drives the frontend's preview/open behaviour"""

    def _download(self, attachment_id, query=''):
        request = self.factory.get(
            f'/api/surveys/survey-attachments/{attachment_id}/download/{query}'
        )
        return SurveyAttachmentDownloadView.as_view()(request, pk=attachment_id)

    def test_image_is_served_inline(self):
        """Images render inline so they can be previewed"""
        attachment = self.upload(make_png()).data['data']['attachment']

        response = self._download(attachment['id'])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response['Content-Disposition'].startswith('inline'))
        self.assertEqual(b''.join(response.streaming_content) if response.streaming else response.content, PNG_BYTES)

    def test_powerpoint_is_served_as_download(self):
        """Formats the browser cannot render are downloaded"""
        attachment = self.upload(make_pptx()).data['data']['attachment']

        response = self._download(attachment['id'])

        self.assertTrue(response['Content-Disposition'].startswith('attachment'))

    def test_download_flag_forces_attachment(self):
        """?download=1 forces a save even for inline-viewable types"""
        attachment = self.upload(make_png()).data['data']['attachment']

        response = self._download(attachment['id'], '?download=1')

        self.assertTrue(response['Content-Disposition'].startswith('attachment'))

    def test_arabic_filename_survives_the_header(self):
        """Arabic names are sent RFC 5987 encoded, not mangled into latin-1"""
        attachment = self.upload(make_png('مخطط.png')).data['data']['attachment']

        response = self._download(attachment['id'])
        disposition = response['Content-Disposition']

        self.assertIn("filename*=UTF-8''", disposition)
        # ASCII fallback keeps the extension instead of collapsing to ".png"
        self.assertIn('filename="attachment.png"', disposition)

    def test_ascii_filename_is_kept_verbatim(self):
        """Latin filenames need no fallback substitution"""
        attachment = self.upload(make_pptx('quarterly-deck.pptx')).data['data']['attachment']

        response = self._download(attachment['id'])

        self.assertIn('filename="quarterly-deck.pptx"', response['Content-Disposition'])


class SurveyAttachmentDeleteTests(SurveyAttachmentTestBase):
    """Removal rules"""

    def _delete(self, attachment_id, user):
        request = self.factory.delete(f'/api/surveys/survey-attachments/{attachment_id}/')
        force_authenticate(request, user=user)
        return SurveyAttachmentDeleteView.as_view()(request, pk=attachment_id)

    def test_creator_can_delete(self):
        attachment = self.upload(make_png()).data['data']['attachment']

        response = self._delete(attachment['id'], self.creator)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SurveyAttachment.objects.filter(survey=self.survey).count(), 0)

    def test_non_creator_cannot_delete(self):
        attachment = self.upload(make_png()).data['data']['attachment']

        response = self._delete(attachment['id'], self.other)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(SurveyAttachment.objects.filter(survey=self.survey).count(), 1)

    def test_deleting_survey_removes_attachments(self):
        """CASCADE keeps no orphan BLOBs behind"""
        self.upload(make_png())
        survey_id = self.survey.id

        self.survey.delete()

        self.assertEqual(SurveyAttachment.objects.filter(survey_id=survey_id).count(), 0)


class SurveyAttachmentCloneTests(SurveyAttachmentTestBase):
    """Cloning a survey duplicates its reference files"""

    def test_clone_copies_attachment_bytes(self):
        self.upload(make_png('plan.png'), description='مخطط')
        self.upload(make_pptx())

        request = self.factory.post(f'/api/surveys/surveys/{self.survey.id}/clone/', {}, format='json')
        force_authenticate(request, user=self.creator)
        response = CloneSurveyView.as_view()(request, survey_id=str(self.survey.id))

        self.assertEqual(response.status_code, 201)
        clone_id = response.data['data']['survey']['id']
        self.assertEqual(SurveyAttachment.objects.filter(survey_id=clone_id).count(), 2)

        original = SurveyAttachment.objects.get(survey=self.survey, original_filename='plan.png')
        copy = SurveyAttachment.objects.get(survey_id=clone_id, original_filename='plan.png')
        self.assertEqual(bytes(copy.file_data), bytes(original.file_data))
        self.assertEqual(copy.file_size, original.file_size)
        self.assertEqual(copy.description, original.description)
        self.assertEqual(copy.display_order, original.display_order)
