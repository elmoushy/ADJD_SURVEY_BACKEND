"""
Migration: add ResponseFollowUp and FollowUpMessage models.
Pure additive — no backfill needed.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0022_response_group_flag'),
        ('authentication', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResponseFollowUp',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[
                        ('pending_reply', 'Pending Reply'),
                        ('replied', 'Replied'),
                        ('accepted', 'Accepted'),
                        ('rejected', 'Rejected'),
                        ('closed', 'Closed'),
                    ],
                    default='pending_reply',
                    max_length=20,
                )),
                ('decision_reason', models.TextField(blank=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('response', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='follow_ups',
                    to='surveys.response',
                )),
                ('opened_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='followups_opened',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('decided_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='followups_decided',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Response Follow-up',
                'verbose_name_plural': 'Response Follow-ups',
                'db_table': 'surveys_response_followup',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='FollowUpMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('sender_role', models.CharField(
                    choices=[('admin', 'Admin'), ('responder', 'Responder')],
                    max_length=20,
                )),
                ('body', models.TextField()),
                ('is_preset', models.BooleanField(default=False)),
                ('preset_key', models.CharField(blank=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('thread', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='messages',
                    to='surveys.responsefollowup',
                )),
                ('sender', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='followup_messages',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Follow-up Message',
                'verbose_name_plural': 'Follow-up Messages',
                'db_table': 'surveys_followup_message',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='responsefollowup',
            index=models.Index(fields=['response', 'status'], name='followup_response_status_idx'),
        ),
        migrations.AddIndex(
            model_name='responsefollowup',
            index=models.Index(fields=['status', 'updated_at'], name='followup_status_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='followupmessage',
            index=models.Index(fields=['thread', 'created_at'], name='followup_msg_thread_time_idx'),
        ),
    ]
