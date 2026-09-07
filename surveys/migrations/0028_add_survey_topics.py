"""
Add SurveyTopic — organizational folders ("موضوع") that group related surveys —
and the nullable Survey.topic FK that points at them.

Made self-healing (Safe* operations below) after this migration hit two Oracle
failures in sequence on a real environment:
1. ORA-01408 ("such column list already indexed") from the now-removed
   topic_parent_idx — 'parent' is a ForeignKey, which already gets an implicit
   index, so the explicit index duplicated that column list. SQLite/Postgres/
   MySQL silently tolerate the duplicate; only Oracle rejects it.
2. Because Oracle DDL cannot be rolled back (can_rollback_ddl=False), the
   CreateModel from that failed attempt had already committed the table before
   the AddIndex call blew up — so surveys_topic existed, but this migration
   was never marked applied, and simply re-running it after the index fix
   tried CreateModel again and hit ORA-00955 ("name is already used by an
   existing object").

Each operation below checks what already exists before touching it, so this
migration completes correctly regardless of whether it's running against a
brand-new database, one where a previous attempt partially got through, or one
that already has real SurveyTopic rows — no manual DROP TABLE, and no data
loss, on any of them.

Oracle compatibility notes:
- db_table 'surveys_topic' is 13 chars (Oracle 11g/12.1 limit is 30)
- index names: topic_path_idx (14), topic_deleted_idx (17),
  topic_pin_order_idx (19) — all well under the 30-char limit
- no explicit index on `parent` (see point 1 above)
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
from django.db import migrations, models, connection


def _table_exists(table_name):
    """Cross-vendor existence check for a table."""
    with connection.cursor() as cursor:
        if connection.vendor == 'oracle':
            cursor.execute(
                "SELECT COUNT(*) FROM user_tables WHERE table_name = UPPER(%s)",
                [table_name],
            )
        elif connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=%s",
                [table_name],
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s",
                [table_name],
            )
        return cursor.fetchone()[0] > 0


def _column_exists(table_name, column_name):
    """Cross-vendor existence check for a column."""
    with connection.cursor() as cursor:
        if connection.vendor == 'oracle':
            cursor.execute(
                """SELECT COUNT(*) FROM user_tab_columns
                   WHERE table_name = UPPER(%s) AND column_name = UPPER(%s)""",
                [table_name, column_name],
            )
            return cursor.fetchone()[0] > 0
        elif connection.vendor == 'sqlite':
            cursor.execute(f"PRAGMA table_info({table_name})")
            return column_name in [row[1] for row in cursor.fetchall()]
        else:
            cursor.execute(
                """SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_name = %s AND column_name = %s""",
                [table_name, column_name],
            )
            return cursor.fetchone()[0] > 0


def _index_exists(index_name):
    """Cross-vendor existence check for an index, by name."""
    with connection.cursor() as cursor:
        if connection.vendor == 'oracle':
            cursor.execute(
                "SELECT COUNT(*) FROM user_indexes WHERE index_name = UPPER(%s)",
                [index_name],
            )
        elif connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=%s",
                [index_name],
            )
        elif connection.vendor == 'postgresql':
            cursor.execute(
                "SELECT COUNT(*) FROM pg_indexes WHERE indexname = %s",
                [index_name],
            )
        elif connection.vendor == 'mysql':
            cursor.execute(
                """SELECT COUNT(*) FROM information_schema.statistics
                   WHERE index_name = %s AND table_schema = DATABASE()""",
                [index_name],
            )
        else:
            return False
        return cursor.fetchone()[0] > 0


class SafeCreateModel(migrations.CreateModel):
    """CreateModel that no-ops if the table already exists (state still updates)."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        table_name = self.options.get('db_table') or f"{app_label}_{self.name.lower()}"
        if _table_exists(table_name):
            print(f"SUCCESS: table {table_name} already exists — skipping CreateModel")
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
        print(f"SUCCESS: created table {table_name}")


class SafeAddIndex(migrations.AddIndex):
    """AddIndex that no-ops if an index with this name already exists."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if _index_exists(self.index.name):
            print(f"SUCCESS: index {self.index.name} already exists — skipping")
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
        print(f"SUCCESS: created index {self.index.name}")


class SafeAddField(migrations.AddField):
    """AddField that no-ops if the column already exists."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        column_name = model._meta.get_field(self.name).column
        table_name = model._meta.db_table
        if _column_exists(table_name, column_name):
            print(f"SUCCESS: column {column_name} on {table_name} already exists — skipping")
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
        print(f"SUCCESS: added column {column_name} to {table_name}")


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0027_add_survey_attachments'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        SafeCreateModel(
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
        SafeAddIndex(
            model_name='surveytopic',
            index=models.Index(fields=['path'], name='topic_path_idx'),
        ),
        SafeAddIndex(
            model_name='surveytopic',
            index=models.Index(fields=['deleted_at'], name='topic_deleted_idx'),
        ),
        SafeAddIndex(
            model_name='surveytopic',
            index=models.Index(fields=['is_pinned', 'display_order'], name='topic_pin_order_idx'),
        ),
        SafeAddField(
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
