import importlib.util
import os

from data.models import db, initialize_models
from utils.config import DATABASE_FILE
from utils.logging import logger


def set_database_file(db_file):
    """Set the database file path for the global database object."""
    db.init(db_file)

def apply_migrations():
    """Apply database migrations sequentially."""
    migrations_dir = os.path.join(os.path.dirname(__file__), '..', 'migrations')
    migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.py') and f != '__init__.py'])

    for migration_file in migration_files:
        try:
            file_path = os.path.join(migrations_dir, migration_file)
            spec = importlib.util.spec_from_file_location(migration_file, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            logger.info(f"Applied migration: {migration_file}")
        except Exception as e:
            logger.error(f"Error applying migration {migration_file}: {e}")
            # Depending on your needs, you might want to re-raise the exception
            # or handle it more gracefully (e.g., mark migration as failed).

def initialize_database():
    """Initialize the database by setting the file path and creating tables."""
    set_database_file(DATABASE_FILE)
    initialize_models()
    # Get the list of columns
    cursor = db.execute_sql('PRAGMA table_info(guildconfig);')
    columns = [row[1] for row in cursor.fetchall()]

    # Add the column if it doesn't exist
    if 'custom_availability_pattern' not in columns:
        db.execute_sql('ALTER TABLE guildconfig ADD COLUMN custom_availability_pattern TEXT;')
        logger.info("Added 'custom_availability_pattern' to the 'guildconfig' table.")
    db.close()
    # apply_migrations()
    logger.info("Database initialized using Peewee models.")
