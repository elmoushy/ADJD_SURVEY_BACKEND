"""
Tests for the manual reminder counter (Survey.reminder_count / last_reminder_at).

Covers:
- send-reminder increments the counter once per send that reaches someone
- a send with nobody to remind is not counted
- the counter write is atomic and does not bump updated_at
- a stale instance's save() can never reset the counter
- the list endpoint exposes the counter (Oracle-safe .only() path, no N+1)
"""

import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from surveys.models import Survey
from surveys.views import SurveyViewSet

User = get_user_model()


def envelope(response):
    data = response.data
    if isinstance(data, dict) and 'data' in data:
        return data['data']
    return data


class ReminderCountTests(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.creator = User.objects.create_user(
            username='creator@example.com', email='creator@example.com',
            password='testpass123', role='admin',
        )
        self.member = User.objects.create_user(
            username='member@example.com', email='member@example.com',
            password='testpass123', role='user',
        )
        self.survey = Survey.objects.create(
            title='Reminded survey', creator=self.creator,
            status='submitted', visibility='AUTH',
        )
        self.send_view = SurveyViewSet.as_view({'post': 'send_reminder'})
        self.list_view = SurveyViewSet.as_view({'get': 'list'})

    def send(self, user=None):
        request = self.factory.post(f'/api/surveys/surveys/{self.survey.id}/send-reminder/', {}, format='json')
        force_authenticate(request, user=user or self.creator)
        return self.send_view(request, pk=str(self.survey.id))

    # ── counting ─────────────────────────────────────────────────────────────
    @patch('surveys.email_service.notify_survey_reminder', return_value=5)
    def test_each_send_increments_once_regardless_of_recipients(self, _notify):
        first = envelope(self.send())
        self.assertEqual(first['count'], 5)
        self.assertEqual(first['reminder_count'], 1)
        self.assertIsNotNone(first['last_reminder_at'])

        second = envelope(self.send())
        self.assertEqual(second['reminder_count'], 2)

        self.survey.refresh_from_db()
        self.assertEqual(self.survey.reminder_count, 2)
        self.assertIsNotNone(self.survey.last_reminder_at)

    @patch('surveys.email_service.notify_survey_reminder', return_value=0)
    def test_send_with_nobody_to_remind_is_not_counted(self, _notify):
        body = envelope(self.send())
        self.assertEqual(body['count'], 0)
        self.assertEqual(body['reminder_count'], 0)
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.reminder_count, 0)
        self.assertIsNone(self.survey.last_reminder_at)

    @patch('surveys.email_service.notify_survey_reminder', return_value=3)
    def test_non_creator_cannot_send_or_count(self, _notify):
        response = self.send(user=self.member)
        self.assertEqual(response.status_code, 403)
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.reminder_count, 0)

    def test_record_reminder_does_not_touch_updated_at(self):
        before = Survey.objects.get(pk=self.survey.pk).updated_at
        self.survey.record_reminder_sent()
        after = Survey.objects.get(pk=self.survey.pk)
        self.assertEqual(after.reminder_count, 1)
        self.assertEqual(after.updated_at, before)

    # ── stale-save protection ────────────────────────────────────────────────
    def test_stale_instance_save_keeps_the_counter(self):
        stale = Survey.objects.get(pk=self.survey.pk)      # loaded with count 0
        self.survey.record_reminder_sent()                  # count -> 1 in DB
        stale.is_locked = True
        stale.save()                                         # full save of stale copy

        fresh = Survey.objects.get(pk=self.survey.pk)
        self.assertTrue(fresh.is_locked)
        self.assertEqual(fresh.reminder_count, 1)
        self.assertIsNotNone(fresh.last_reminder_at)

    def test_deferred_instance_save_still_works(self):
        partial = Survey.objects.only('id', 'title', 'is_active').get(pk=self.survey.pk)
        partial.is_active = False
        partial.save()
        self.assertFalse(Survey.objects.get(pk=self.survey.pk).is_active)

    def test_new_survey_starts_at_zero(self):
        survey = Survey.objects.create(title='New', creator=self.creator)
        self.assertEqual(survey.reminder_count, 0)
        self.assertIsNone(survey.last_reminder_at)

    # ── exposure ─────────────────────────────────────────────────────────────
    def list_rows(self, user):
        request = self.factory.get('/api/surveys/surveys/')
        force_authenticate(request, user=user)
        response = self.list_view(request)
        self.assertEqual(response.status_code, 200)
        return {row['id']: row for row in envelope(response)['results']}

    def test_list_exposes_counter_to_creator_and_regular_user(self):
        self.survey.record_reminder_sent()
        for user in (self.creator, self.member):
            row = self.list_rows(user)[str(self.survey.id)]
            self.assertEqual(row['reminder_count'], 1)
            self.assertIsNotNone(row['last_reminder_at'])

    def test_counter_fields_are_not_deferred_in_list_queryset(self):
        """No per-row deferred load for the new columns (N+1 guard)."""
        for i in range(5):
            Survey.objects.create(title=f'Extra {i}', creator=self.creator, status='submitted', visibility='AUTH')
        # Regular users go through the .distinct().only(get_oracle_safe_fields())
        # queryset — the path where a missing field would be deferred.
        with CaptureQueriesContext(connection) as many:
            self.list_rows(self.member)
        # A deferred-field load is Django's refresh_from_db(fields=[f]):
        # SELECT "surveys_survey"."id", "surveys_survey"."<f>" FROM ... WHERE id = ...
        deferred_load = re.compile(
            r'^SELECT "surveys_survey"\."id", "surveys_survey"\."(reminder_count|last_reminder_at)" FROM'
        )
        reminder_loads = [q['sql'] for q in many.captured_queries if deferred_load.match(q['sql'])]
        self.assertEqual(reminder_loads, [])
