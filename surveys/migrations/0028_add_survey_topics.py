"""
Add SurveyTopic — organizational folders ("موضوع") that group related surveys —
and the nullable Survey.topic FK that points at them.

Oracle compatibility notes:
- db_table 'surveys_topic' is 13 chars (Oracle 11g/12.1 limit is 30)
- index names: topic_path_idx (14), topic_deleted_idx (17),
  topic_pin_order_idx (19) — all well under the 30-char limit
- no explicit index on `parent`: it's a ForeignKey, which already gets an
  implicit index from CreateModel; an explicit AddIndex on the same single
  column duplicates that column list, and Oracle raises ORA-01408 ("such
  column list already indexed") for that — SQLite/Postgres/MySQL silently
  allow the duplicate, which is why this only surfaces on Oracle
- the new table has NO NCLOB column (description is CharField(500), not TextField),
  which keeps DISTINCT / GROUP BY / ORDER BY over topic columns legal on Oracle and
  makes select_related('topic') safe inside the survey queryset that uses .distinct()
- no conditional/partial indexes (unsupported on Oracle)
- BooleanFields are declared with explicit `default=False` so Oracle receives a real
  NUMBER(1) default instead of NULL (see migrations 0009-0012 for the history behind this)
- Survey.topic is nullable, so Oracle adds the column without a table rewrite and
  without a NOT NULL-with-default scan
- uniqueness on name_key is global, not (parent, name_key): Oracle treats NULL as
  distinct inside unique constraints, so root topics would escape a composite one
- db_column='topic_id' / 'parent_id' keeps the generated column names short
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0027_add_survey_attachments'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SurveyTopic',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='Topic display name (plaintext organizational label)', max_length=255)),
                ('name_key', models.CharField(help_text='Normalized (trimmed + casefolded) name used for case-insensitive uniqueness', max_length=255, unique=True)),
                ('description', models.CharField(blank=True, default='', help_text='Short description. CharField (not TextField) to keep this table LOB-free for Oracle', max_length=500)),
                ('color', models.CharField(blank=True, default='', help_text='Accent colour from the brand palette, e.g. #A17D23', max_length=7)),
                ('icon', models.CharField(blank=True, default='', help_text='FontAwesome icon name from ALLOWED_ICONS', max_length=40)),
                ('depth', models.PositiveSmallIntegerField(default=0, help_text='0 for root topics, at most MAX_DEPTH - 1')),
                ('path', models.CharField(blank=True, default='', help_text="Materialized path of hex UUIDs, e.g. 'aaaa.bbbb.cccc'. Enables subtree queries via path__startswith (an indexable LIKE 'prefix%' on Oracle)", max_length=200)),
                ('is_pinned', models.BooleanField(blank=True, default=False, help_text='Pinned topics are listed first')),
                ('display_order', models.IntegerField(default=0, help_text='Manual ordering inside the same pin bucket')),
                ('is_archived', models.BooleanField(blank=True, default=False, help_text='Archived topics keep their surveys but cannot receive new ones')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, help_text='User who created this topic', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_survey_topics', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, db_column='parent_id', help_text='Parent topic; NULL for root topics', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='surveys.surveytopic')),
            ],
            options={
                'verbose_name': 'Survey Topic',
                'verbose_name_plural': 'Survey Topics',
                'db_table': 'surveys_topic',
                'ordering': ['-is_pinned', 'display_order', 'name'],
            },
        ),
        migrations.AddIndex(
            model_name='surveytopic',
            index=models.Index(fields=['path'], name='topic_path_idx'),
        ),
        migrations.AddIndex(
            model_name='surveytopic',
            index=models.Index(fields=['deleted_at'], name='topic_deleted_idx'),
        ),
        migrations.AddIndex(
            model_name='surveytopic',
            index=models.Index(fields=['is_pinned', 'display_order'], name='topic_pin_order_idx'),
        ),
        migrations.AddField(
            model_name='survey',
            name='topic',
            field=models.ForeignKey(
                blank=True,
                db_column='topic_id',
                help_text='Optional topic (folder) this survey belongs to',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='surveys',
                to='surveys.surveytopic',
            ),
        ),
    ]
