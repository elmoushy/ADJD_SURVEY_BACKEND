"""
Add SurveyAttachment — reference files the survey creator pins to a survey so
respondents can read them while answering.

Oracle compatibility notes:
- db_table 'surveys_survey_attachment' is 25 chars (Oracle 11g/12.1 limit is 30)
- index name 'survey_att_order_idx' is 20 chars (same 30-char limit)
- BinaryField maps to BLOB, matching the existing attachment tables
- no conditional/partial indexes (unsupported on Oracle)
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0026_alter_allow_attachments_default_optional'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SurveyAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file_data', models.BinaryField(help_text='File content stored as BLOB (max 10MB)')),
                ('original_filename', models.CharField(help_text='Sanitized original filename', max_length=255)),
                ('file_size', models.IntegerField(help_text='File size in bytes')),
                ('mime_type', models.CharField(help_text='Validated MIME type', max_length=150)),
                ('description', models.CharField(blank=True, help_text='Optional note shown to respondents next to the file', max_length=500)),
                ('display_order', models.IntegerField(default=0, help_text='Order the attachments are shown to respondents')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True, help_text='Upload timestamp')),
                ('survey', models.ForeignKey(help_text='Parent survey (CASCADE deletes attachments when survey deleted)', on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='surveys.survey')),
                ('uploaded_by', models.ForeignKey(blank=True, help_text='User who uploaded this attachment', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_survey_attachments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Survey Attachment',
                'verbose_name_plural': 'Survey Attachments',
                'db_table': 'surveys_survey_attachment',
                'ordering': ['display_order', 'uploaded_at'],
                'indexes': [models.Index(fields=['survey', 'display_order'], name='survey_att_order_idx')],
            },
        ),
    ]
