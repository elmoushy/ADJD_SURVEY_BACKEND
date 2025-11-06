# Sync Django migration state with existing database schema
# The per_device_access field and DeviceResponse model already exist in the database
# (created by migration 0008 using raw SQL), but Django's migration state wasn't updated.
# This migration syncs Django's state without modifying the database.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0012_fix_oracle_default_value'),
    ]

    # Store the operations that should be reflected in Django's migration state
    state_operations = [
        migrations.AddField(
            model_name='survey',
            name='per_device_access',
            field=models.BooleanField(default=False, help_text='If enabled, survey can only be filled once per device (no email/phone required)'),
        ),
        migrations.CreateModel(
            name='DeviceResponse',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('device_fingerprint', models.CharField(help_text='SHA256 hash of device fingerprint (User-Agent + Screen Resolution + Timezone + Language)', max_length=64)),
                ('ip_address', models.GenericIPAddressField(blank=True, help_text='IP address of the device', null=True)),
                ('user_agent', models.TextField(blank=True, help_text='User agent string from the device', null=True)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('response', models.OneToOneField(blank=True, help_text='Associated response object', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='device_tracking', to='surveys.response')),
                ('survey', models.ForeignKey(help_text='Survey this device response belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='device_responses', to='surveys.survey')),
            ],
            options={
                'verbose_name': 'Device Response',
                'verbose_name_plural': 'Device Responses',
                'db_table': 'surveys_device_response',
                'ordering': ['-submitted_at'],
                'indexes': [models.Index(fields=['survey', 'device_fingerprint'], name='surveys_device_survey_fp_idx'), models.Index(fields=['device_fingerprint'], name='surveys_device_fp_idx')],
                'unique_together': {('survey', 'device_fingerprint')},
            },
        ),
    ]

    operations = [
        # Use SeparateDatabaseAndState to update Django's migration state
        # without executing database operations (since the schema already exists)
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[],  # No database operations - schema already exists
        ),
    ]
