"""
Migration: add is_group_submission + submitted_via_group to Response model.
Includes RunPython backfill to classify existing responses.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_group_submissions(apps, schema_editor):
    Response = apps.get_model('surveys', 'Response')
    for response in Response.objects.select_related('survey', 'respondent').iterator(chunk_size=500):
        survey = response.survey
        if not response.respondent_id:
            continue
        # Named individual in shared_with → NOT a group submission
        if survey.shared_with.filter(id=response.respondent_id).exists():
            continue
        # Matched only via a shared group → group submission
        user_group_ids = response.respondent.user_groups.values_list('group_id', flat=True)
        first_group = (
            survey.shared_with_groups
                  .filter(id__in=user_group_ids)
                  .order_by('id')
                  .first()
        )
        if first_group:
            response.is_group_submission = True
            response.submitted_via_group = first_group
            response.save(update_fields=['is_group_submission', 'submitted_via_group'])


def reverse_backfill(apps, schema_editor):
    Response = apps.get_model('surveys', 'Response')
    Response.objects.update(is_group_submission=False, submitted_via_group=None)


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0021_replace_ip_with_mac_address'),
        ('authentication', '__first__'),
    ]

    operations = [
        migrations.AddField(
            model_name='response',
            name='is_group_submission',
            field=models.BooleanField(
                default=False,
                help_text='True when respondent matched via shared_with_groups (not named individually)',
            ),
        ),
        migrations.AddField(
            model_name='response',
            name='submitted_via_group',
            field=models.ForeignKey(
                blank=True,
                help_text='The group through which the respondent gained access (if is_group_submission)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='submissions',
                to='authentication.group',
            ),
        ),
        migrations.RunPython(backfill_group_submissions, reverse_backfill),
    ]
