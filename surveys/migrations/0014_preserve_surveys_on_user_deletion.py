# Generated migration to preserve surveys when users are deleted
# This migration changes the foreign key relationships to use SET_NULL
# instead of CASCADE to meet the system requirement

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0013_sync_device_models_state'),
    ]

    operations = [
        # Change Survey.creator to SET_NULL and make it nullable
        migrations.AlterField(
            model_name='survey',
            name='creator',
            field=models.ForeignKey(
                blank=True,
                help_text='User who created this survey',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_surveys',
                to='authentication.user'
            ),
        ),
        # Change PublicAccessToken.created_by to SET_NULL and make it nullable
        migrations.AlterField(
            model_name='publicaccesstoken',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                help_text='User who created this token',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_tokens',
                to='authentication.user'
            ),
        ),
    ]
