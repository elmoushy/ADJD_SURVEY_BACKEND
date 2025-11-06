# Manual migration to fix Oracle per_device_access field completely

from django.db import migrations, models, connection
import logging

logger = logging.getLogger(__name__)


def ensure_oracle_boolean_field(apps, schema_editor):
    """
    Ensure per_device_access field works properly with Oracle
    """
    db_alias = schema_editor.connection.alias
    
    # Check if we're using Oracle
    if connection.vendor != 'oracle':
        logger.info("Not Oracle database, skipping Oracle-specific fixes")
        return
    
    with connection.cursor() as cursor:
        try:
            # First, update any NULL values to 0 (False)
            cursor.execute("""
                UPDATE surveys_survey 
                SET per_device_access = 0 
                WHERE per_device_access IS NULL
            """)
            rows_updated = cursor.rowcount
            logger.info(f"Updated {rows_updated} NULL per_device_access values to 0")
            
            # Check current column definition
            cursor.execute("""
                SELECT data_type, nullable, data_default, data_length, data_precision, data_scale
                FROM user_tab_columns 
                WHERE table_name = 'SURVEYS_SURVEY' 
                AND column_name = 'PER_DEVICE_ACCESS'
            """)
            
            result = cursor.fetchone()
            if result:
                data_type, nullable, data_default, data_length, data_precision, data_scale = result
                logger.info(f"Current column: TYPE={data_type}, NULLABLE={nullable}, DEFAULT={data_default}, "
                          f"LENGTH={data_length}, PRECISION={data_precision}, SCALE={data_scale}")
                
                # Recreate column with proper Oracle boolean setup
                if nullable == 'Y' or data_default is None or str(data_default).strip() == 'NULL':
                    logger.info("Fixing column definition...")
                    cursor.execute("""
                        ALTER TABLE surveys_survey 
                        MODIFY (per_device_access NUMBER(1,0) DEFAULT 0 NOT NULL 
                                CHECK (per_device_access IN (0,1)))
                    """)
                    logger.info("SUCCESS: Fixed per_device_access column definition")
                else:
                    logger.info("SUCCESS: Column already properly configured")
                    
            else:
                logger.error("per_device_access column not found!")
                
        except Exception as e:
            logger.error(f"Error ensuring Oracle boolean field: {e}")
            # Don't raise - let the migration continue


def reverse_oracle_boolean_field(apps, schema_editor):
    """
    Reverse the Oracle boolean field changes
    """
    db_alias = schema_editor.connection.alias
    
    if connection.vendor != 'oracle':
        return
    
    with connection.cursor() as cursor:
        try:
            cursor.execute("""
                ALTER TABLE surveys_survey 
                MODIFY (per_device_access NUMBER(1,0) NULL)
            """)
            logger.info("SUCCESS: Reversed Oracle boolean field constraints")
        except Exception as e:
            logger.error(f"Error reversing Oracle boolean field: {e}")


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0010_fix_oracle_per_device_access'),
    ]

    operations = [
        migrations.RunPython(
            ensure_oracle_boolean_field,
            reverse_oracle_boolean_field,
        ),
    ]
