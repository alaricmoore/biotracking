#!/usr/bin/env python3
"""
Database migration: Symptom category reorganization
- Merge word_loss into cognitive
- Rename air_hunger to pulmonary  
- Add gastro symptom
- Add mucosal symptom
"""

import sqlite3
from pathlib import Path

DB_FILE = "biotracking.db"

def migrate_database():
    """Execute all migration steps."""
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("Starting database migration...")
    
    try:
        # Step 1: Add new columns
        print("\n1. Adding new columns...")
        
        cursor.execute("""
            ALTER TABLE daily_observations 
            ADD COLUMN gastro INTEGER DEFAULT 0
        """)
        print("  ✓ Added gastro column")
        
        cursor.execute("""
            ALTER TABLE daily_observations 
            ADD COLUMN gastro_notes TEXT
        """)
        print("  ✓ Added gastro_notes column")
        
        cursor.execute("""
            ALTER TABLE daily_observations 
            ADD COLUMN mucosal INTEGER DEFAULT 0
        """)
        print("  ✓ Added mucosal column")
        
        cursor.execute("""
            ALTER TABLE daily_observations 
            ADD COLUMN mucosal_notes TEXT
        """)
        print("  ✓ Added mucosal_notes column")
        
        cursor.execute("""
            ALTER TABLE daily_observations 
            ADD COLUMN pulmonary INTEGER DEFAULT 0
        """)
        print("  ✓ Added pulmonary column")
        
        cursor.execute("""
            ALTER TABLE daily_observations 
            ADD COLUMN pulmonary_notes TEXT
        """)
        print("  ✓ Added pulmonary_notes column")
        
        
        # Step 2: Migrate air_hunger data to pulmonary
        print("\n2. Migrating air_hunger → pulmonary...")
        
        cursor.execute("""
            UPDATE daily_observations
            SET pulmonary = air_hunger,
                pulmonary_notes = air_hunger_notes
            WHERE air_hunger IS NOT NULL
        """)
        rows_affected = cursor.rowcount
        print(f"  ✓ Migrated {rows_affected} rows")
        
        
        # Step 3: Merge word_loss into cognitive
        print("\n3. Merging word_loss → cognitive...")
        
        # First, check how many rows have word_loss but NOT cognitive
        cursor.execute("""
            SELECT COUNT(*) FROM daily_observations
            WHERE word_loss = 1 AND (cognitive = 0 OR cognitive IS NULL)
        """)
        word_loss_only = cursor.fetchone()[0]
        print(f"  → {word_loss_only} days have word_loss but not cognitive")
        
        # Merge: if either word_loss OR cognitive is 1, set cognitive to 1
        cursor.execute("""
            UPDATE daily_observations
            SET cognitive = 1
            WHERE word_loss = 1 OR cognitive = 1
        """)
        print(f"  ✓ Merged word_loss into cognitive")
        
        # Append word_loss_notes to cognitive_notes where both exist
        cursor.execute("""
            UPDATE daily_observations
            SET cognitive_notes = CASE
                WHEN cognitive_notes IS NOT NULL AND word_loss_notes IS NOT NULL 
                THEN cognitive_notes || '; Word loss: ' || word_loss_notes
                WHEN word_loss_notes IS NOT NULL 
                THEN 'Word loss: ' || word_loss_notes
                ELSE cognitive_notes
            END
            WHERE word_loss_notes IS NOT NULL
        """)
        print(f"  ✓ Merged word_loss notes into cognitive notes")
        
        
        # Step 4: Drop old columns
        print("\n4. Preparing to drop old columns...")
        print("  Note: SQLite doesn't support DROP COLUMN directly")
        print("  Old columns (air_hunger, word_loss) will be left as-is")
        print("  You can manually clean them later if desired")
        
        # Commit all changes
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        
        # Step 5: Verify migration
        print("\n5. Verification:")
        
        cursor.execute("SELECT COUNT(*) FROM daily_observations WHERE pulmonary = 1")
        pulmonary_count = cursor.fetchone()[0]
        print(f"  → {pulmonary_count} days with pulmonary symptoms")
        
        cursor.execute("SELECT COUNT(*) FROM daily_observations WHERE cognitive = 1")
        cognitive_count = cursor.fetchone()[0]
        print(f"  → {cognitive_count} days with cognitive symptoms")
        
        cursor.execute("SELECT COUNT(*) FROM daily_observations WHERE gastro = 1")
        gastro_count = cursor.fetchone()[0]
        print(f"  → {gastro_count} days with gastro symptoms (should be 0 initially)")
        
        cursor.execute("SELECT COUNT(*) FROM daily_observations WHERE mucosal = 1")
        mucosal_count = cursor.fetchone()[0]
        print(f"  → {mucosal_count} days with mucosal symptoms (should be 0 initially)")
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print(f"\n⚠️  Column already exists: {e}")
            print("    Migration may have already been run")
        else:
            raise
    
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    
    finally:
        conn.close()


if __name__ == "__main__":
    # Confirm before running
    print("=" * 60)
    print("DATABASE MIGRATION SCRIPT")
    print("=" * 60)
    print("\nThis will:")
    print("  1. Add gastro and mucosal columns")
    print("  2. Add pulmonary column")
    print("  3. Copy air_hunger → pulmonary")
    print("  4. Merge word_loss → cognitive")
    print("  5. Keep old columns (air_hunger, word_loss) for safety")
    print("\n⚠️  BACKUP YOUR DATABASE FIRST!")
    print(f"   Database: {DB_FILE}")
    
    response = input("\nContinue with migration? (yes/no): ")
    
    if response.lower() == 'yes':
        migrate_database()
    else:
        print("Migration cancelled")