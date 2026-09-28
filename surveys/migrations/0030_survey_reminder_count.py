"""
Add the manual reminder counter to Survey: reminder_count + last_reminder_at.

Oracle compatibility notes:
- Self-healing like 0028: Oracle DDL cannot be rolled back (can_rollback_ddl=False),
  so if one ADD commits and a later step fails, a plain AddField re-run would hit
  ORA-01430 ("column being added already exists in table"). SafeAddField checks
  user_tab_columns first and only updates migration state when the column exists.
- reminder_count -> NUMBER(11) DEFAULT 0 NOT NULL + CHECK (>= 0). Oracle 11g+ adds a
  NOT NULL column with a DEFAULT as a metadata-only change (no table rewrite, no
  full scan), and existing rows read 0 immediately.
- last_reminder_at -> nullable TIMESTAMP; a plain ALTER TABLE ADD.
- Neither column is a LOB, so both stay legal inside the DISTINCT / .only() survey
  list querysets (see SurveyViewSet.get_oracle_safe_fields).
- Column names are 14 / 16 chars (Oracle 11g/12.1 identifier limit is 30).
"""

from django.db import migrations, models


def _column_exists(connection, table_name, column_name):
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


class SafeAddField(migrations.AddField):
    """AddField that no-ops if the column already exists (state still updates)."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        column_name = model._meta.get_field(self.name).column
        table_name = model._meta.db_table
        if _column_exists(schema_editor.connection, table_name, column_name):
            print(f"SUCCESS: column {column_name} on {table_name} already exists — skipping")
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)
        print(f"SUCCESS: added column {column_name} to {table_name}")


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0029_alter_surveytopic_depth_alter_surveytopic_path'),
    ]

    operations = [
        SafeAddField(
            model_name='survey',
            name='reminder_count',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Number of times a manual reminder was sent for this survey',
            ),
        ),
        SafeAddField(
            model_name='survey',
            name='last_reminder_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='When the last manual reminder was sent',
            ),
        ),
    ]
