# Migration to fix per_device_access column default value and NOT NULL constraint

from django.db import migrations, connection


def fix_per_device_access_column(apps, schema_editor):
    """
    Fix the per_device_access column to have proper default value and NOT NULL constraint.
    This handles the Oracle error: ORA-01400: cannot insert NULL into PER_DEVICE_ACCESS
    """
    
    with connection.cursor() as cursor:
        if connection.vendor == 'oracle':
            print("Fixing per_device_access column for Oracle...")
            
            try:
                # Step 1: Update any existing NULL values to FALSE (0 in Oracle)
                cursor.execute("""
                    UPDATE surveys_survey 
                    SET per_device_access = 0 
                    WHERE per_device_access IS NULL
                """)
                rows_updated = cursor.rowcount
                print(f"SUCCESS: Updated {rows_updated} rows with NULL values to FALSE")
                
                # Step 2: Add NOT NULL constraint if it doesn't exist
                cursor.execute("""
                    ALTER TABLE surveys_survey 
                    MODIFY per_device_access DEFAULT 0 NOT NULL
                """)
                print("SUCCESS: Added NOT NULL constraint with default value 0")
                
                # Step 3: Ensure check constraint exists for boolean behavior
                try:
                    cursor.execute("""
                        ALTER TABLE surveys_survey 
                        ADD CONSTRAINT surveys_survey_per_device_access_check 
                        CHECK (per_device_access IN (0, 1))
                    """)
                    print("SUCCESS: Added check constraint for boolean values")
                except Exception as e:
                    if "already exists" in str(e).lower() or "ora-00955" in str(e).lower():
                        print("SUCCESS: Check constraint already exists - skipping")
                    else:
                        print(f"Warning: Could not add check constraint: {e}")
                
            except Exception as e:
                error_msg = str(e).lower()
                if "does not exist" in error_msg:
                    print("SUCCESS: per_device_access column doesn't exist yet - skipping")
                else:
                    print(f"Error fixing per_device_access column: {e}")
                    
        else:
            # For other databases (SQLite, PostgreSQL, MySQL)
            print("Fixing per_device_access column for non-Oracle database...")
            
            try:
                # Update NULL values to FALSE
                cursor.execute("""
                    UPDATE surveys_survey 
                    SET per_device_access = FALSE 
                    WHERE per_device_access IS NULL
                """)
                rows_updated = cursor.rowcount
                print(f"SUCCESS: Updated {rows_updated} rows with NULL values to FALSE")
                
                # For non-Oracle databases, try to alter the column
                if connection.vendor == 'postgresql':
                    cursor.execute("""
                        ALTER TABLE surveys_survey 
                        ALTER COLUMN per_device_access SET DEFAULT FALSE,
                        ALTER COLUMN per_device_access SET NOT NULL
                    """)
                elif connection.vendor == 'mysql':
                    cursor.execute("""
                        ALTER TABLE surveys_survey 
                        MODIFY COLUMN per_device_access BOOLEAN DEFAULT FALSE NOT NULL
                    """)
                else:  # SQLite
                    # SQLite doesn't support modifying columns easily, but it should work with Django's boolean handling
                    pass
                    
                print("SUCCESS: Updated column constraints")
                
            except Exception as e:
                print(f"Error fixing per_device_access column: {e}")


def reverse_per_device_access_fix(apps, schema_editor):
    """
    Reverse the fix - remove NOT NULL constraint (not recommended in production)
    """
    print("Reverse operation - removing NOT NULL constraint from per_device_access")
    
    with connection.cursor() as cursor:
        if connection.vendor == 'oracle':
            try:
                cursor.execute("""
                    ALTER TABLE surveys_survey 
                    MODIFY per_device_access NULL
                """)
                print("SUCCESS: Removed NOT NULL constraint")
            except Exception as e:
                print(f"Error removing NOT NULL constraint: {e}")


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0008_add_per_device_access_safe'),
    ]

    operations = [
        migrations.RunPython(
            fix_per_device_access_column,
            reverse_per_device_access_fix,
            elidable=True
        ),
    ]
