# Fix Oracle default value for per_device_access

from django.db import migrations, models, connection
import logging

logger = logging.getLogger(__name__)


def fix_oracle_default_value(apps, schema_editor):
    """
    Fix Oracle default value for per_device_access
    """
    db_alias = schema_editor.connection.alias
    
    # Check if we're using Oracle
    if connection.vendor != 'oracle':
        logger.info("Not Oracle database, skipping Oracle-specific fixes")
        return
    
    with connection.cursor() as cursor:
        try:
            # First, set a proper default value without changing the NOT NULL constraint
            cursor.execute("""
                ALTER TABLE surveys_survey 
                MODIFY (per_device_access DEFAULT 0)
            """)
            logger.info("SUCCESS: Set default value to 0 for per_device_access")
            
            # Add check constraint if it doesn't exist
            try:
                cursor.execute("""
                    ALTER TABLE surveys_survey 
                    ADD CONSTRAINT surveys_survey_per_device_access_check 
                    CHECK (per_device_access IN (0,1))
                """)
                logger.info("SUCCESS: Added check constraint for per_device_access")
            except Exception as e:
                if "ORA-02264" in str(e):  # constraint already exists
                    logger.info("SUCCESS: Check constraint already exists")
                else:
                    logger.warning(f"Could not add check constraint: {e}")
                    
        except Exception as e:
            logger.error(f"Error fixing Oracle default value: {e}")


def reverse_oracle_default_value(apps, schema_editor):
    """
    Reverse the Oracle default value changes
    """
    db_alias = schema_editor.connection.alias
    
    if connection.vendor != 'oracle':
        return
    
    with connection.cursor() as cursor:
        try:
            cursor.execute("""
                ALTER TABLE surveys_survey 
                MODIFY (per_device_access DEFAULT NULL)
            """)
            logger.info("SUCCESS: Reversed default value for per_device_access")
        except Exception as e:
            logger.error(f"Error reversing Oracle default value: {e}")


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0011_ensure_oracle_boolean_field'),
    ]

    operations = [
        migrations.RunPython(
            fix_oracle_default_value,
            reverse_oracle_default_value,
        ),
    ]
