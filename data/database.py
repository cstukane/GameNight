from data.models import db, initialize_models
from utils.config import DATABASE_FILE
from utils.logging import logger


def set_database_file(db_file):
    """Set the database file path for the global database object."""
    db.init(db_file)


def initialize_database():
    """Initialize the database by setting the file path and creating tables."""
    set_database_file(DATABASE_FILE)
    initialize_models()
    logger.info("Database initialized using Peewee models.")
