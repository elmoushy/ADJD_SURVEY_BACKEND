"""
Migration to change allow_attachments from BooleanField to CharField with choices.
Converts: False -> 'none', True -> 'optional'
"""

from django.db import migrations, models


def convert_bool_to_choices(apps, schema_editor):
    """Convert existing boolean values to choice values."""
    Survey = apps.get_model('surveys', 'Survey')
    # True -> 'optional', False -> 'none'
    Survey.objects.filter(allow_attachments_bool=True).update(allow_attachments='optional')
    Survey.objects.filter(allow_attachments_bool=False).update(allow_attachments='none')


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0024_add_attachments'),
    ]

    operations = [
        # Step 1: Rename old field
        migrations.RenameField(
            model_name='survey',
            old_name='allow_attachments',
            new_name='allow_attachments_bool',
        ),
        # Step 2: Add new CharField
        migrations.AddField(
            model_name='survey',
            name='allow_attachments',
            field=models.CharField(
                choices=[('none', 'None'), ('optional', 'Optional'), ('required', 'Required')],
                default='none',
                help_text='Whether respondents can/must upload attachments: none, optional, required',
                max_length=10,
            ),
        ),
        # Step 3: Convert data
        migrations.RunPython(convert_bool_to_choices, migrations.RunPython.noop),
        # Step 4: Remove old field
        migrations.RemoveField(
            model_name='survey',
            name='allow_attachments_bool',
        ),
    ]
