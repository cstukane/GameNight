from data.models import db, initialize_models, GuildConfig
from utils.config import DATABASE_FILE
from utils.logging import logger


def set_database_file(db_file):
    """Set the database file path for the global database object."""
    db.init(db_file)


def initialize_database():
    """Initialize the database by setting the file path and creating tables."""
    set_database_file(DATABASE_FILE)
    db.connect()
    # Get the list of columns
    cursor = db.execute_sql('PRAGMA table_info(guildconfig);')
    columns = [row[1] for row in cursor.fetchall()]

    # Add the column if it doesn't exist
    if 'custom_availability_pattern' not in columns:
        db.execute_sql('ALTER TABLE guildconfig ADD COLUMN custom_availability_pattern TEXT;')
        logger.info("Added 'custom_availability_pattern' to the 'guildconfig' table.")
    db.close()
    initialize_models()
    logger.info("Database initialized using Peewee models.")
