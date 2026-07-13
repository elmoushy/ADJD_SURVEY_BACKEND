"""
Change the default value of allow_attachments from 'none' to 'optional'
so new surveys allow optional attachments by default.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0025_alter_allow_attachments_to_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='survey',
            name='allow_attachments',
            field=models.CharField(
                choices=[('none', 'None'), ('optional', 'Optional'), ('required', 'Required')],
                default='optional',
                help_text='Whether respondents can/must upload attachments: none, optional, required',
                max_length=10,
            ),
        ),
    ]
