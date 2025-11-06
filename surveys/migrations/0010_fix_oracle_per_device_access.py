# Generated manually to fix Oracle per_device_access constraints

from django.db import migrations, models, connection


def fix_per_device_access_constraints(apps, schema_editor):
    """
    Fix Oracle constraints for per_device_access field
    """
    db_alias = schema_editor.connection.alias
    
    # Check if we're using Oracle
    if connection.vendor != 'oracle':
        return
    
    with connection.cursor() as cursor:
        try:
            # Set any NULL values to FALSE first
            cursor.execute("""
                UPDATE surveys_survey 
                SET per_device_access = 0 
                WHERE per_device_access IS NULL
            """)
            
            # Check if column exists and its current state
            cursor.execute("""
                SELECT nullable, data_default 
                FROM user_tab_columns 
                WHERE table_name = 'SURVEYS_SURVEY' 
                AND column_name = 'PER_DEVICE_ACCESS'
            """)
            
            result = cursor.fetchone()
            if result:
                nullable, data_default = result
                print(f"Current state - Nullable: {nullable}, Default: {data_default}")
                
                # If the column allows NULLs, make it NOT NULL
                if nullable == 'Y':
                    cursor.execute("""
                        ALTER TABLE surveys_survey 
                        MODIFY (per_device_access NUMBER(1) DEFAULT 0 NOT NULL)
                    """)
                    print("SUCCESS: Updated column to NOT NULL with default 0")
                else:
                    print("SUCCESS: Column already NOT NULL")
            else:
                print("Column not found")
                
        except Exception as e:
            print(f"Error fixing Oracle constraints: {e}")


def reverse_fix_per_device_access_constraints(apps, schema_editor):
    """
    Reverse the constraints fix (allow NULLs again)
    """
    db_alias = schema_editor.connection.alias
    
    # Check if we're using Oracle
    if connection.vendor != 'oracle':
        return
    
    with connection.cursor() as cursor:
        try:
            cursor.execute("""
                ALTER TABLE surveys_survey 
                MODIFY (per_device_access NUMBER(1) NULL)
            """)
            print("SUCCESS: Reversed constraint - column now allows NULL")
        except Exception as e:
            print(f"Error reversing constraints: {e}")


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0009_fix_per_device_access_default'),
    ]

    operations = [
        migrations.RunPython(
            fix_per_device_access_constraints,
            reverse_fix_per_device_access_constraints,
        ),
    ]
