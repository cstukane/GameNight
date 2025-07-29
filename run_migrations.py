# add_notification_column.py

from peewee import SqliteDatabase, BooleanField
from playhouse.migrate import SqliteMigrator, migrate
import os

# --- IMPORTANT ---
# This script assumes your database file is located at 'data/gamernight.db'
# relative to where you run the script. Please verify this path is correct.
# It should match the DATABASE_FILE setting in your project.
DATABASE_FILE = os.path.join('data', 'users.db')

def run_migration():
    """
    Connects to the database and adds the new 'receive_voice_notifications'
    column to the User table.
    """
    print(f"--- Database Update Script ---")
    if not os.path.exists(DATABASE_FILE):
        print(f"ERROR: Database file not found at '{DATABASE_FILE}'")
        print("Please make sure the DATABASE_FILE path is correct and you are running this script from your main project directory.")
        return

    print(f"Connecting to database at: {DATABASE_FILE}")
    db = SqliteDatabase(DATABASE_FILE)
    
    # The migrator is a tool that lets us change (migrate) a table's structure.
    migrator = SqliteMigrator(db)
    
    print("Preparing to add 'receive_voice_notifications' column to the 'user' table...")

    try:
        # We are defining the new column.
        # It's a BooleanField (True/False) and will default to True for all existing users.
        new_column = BooleanField(default=True)

        # The migrate() function applies our changes.
        migrate(
            migrator.add_column('user', 'receive_voice_notifications', new_column),
        )
        print("\nSUCCESS!")
        print("The 'receive_voice_notifications' column has been added to your database.")
        print("You can now restart your bot normally.")

    except Exception as e:
        # This error often happens if the column was already added.
        if "duplicate column name" in str(e).lower():
            print("\nNOTE: The column 'receive_voice_notifications' already exists.")
            print("No changes were needed. You are good to go!")
        else:
            print(f"\nERROR: An unexpected error occurred: {e}")
            print("Please check the error message. If you need help, please provide the full error.")

if __name__ == "__main__":
    run_migration()