import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.models import db, UserGame
from data.database import initialize_database
from utils.logging import logger

def migrate_sources_to_uppercase():
    """
    Migrates all existing UserGame.source entries to standardize 'Game_Pass' to 'Game Pass' and 'Pc' to 'PC'.
    """
    initialize_database() # Ensure database connection and models are set up
    
    try:
        with db.atomic():
            updated_count = 0
            for user_game in UserGame.select():
                old_source = user_game.source
                new_source = old_source # Initialize new_source with old_source

                if old_source == "Game_Pass":
                    new_source = "Game Pass"
                elif old_source == "Pc":
                    new_source = "PC"
                # If there are other sources that need to be uppercased,
                # or follow a different standardization, that logic would go here.
                # For now, only addressing the specific request.

                if old_source != new_source:
                    user_game.source = new_source
                    user_game.save()
                    updated_count += 1
                    logger.info(f"Migrated source for UserGame ID {user_game.id}: '{old_source}' -> '{new_source}'")
            logger.info(f"Migration complete. Updated {updated_count} UserGame source entries.")
    except Exception as e:
        logger.error(f"Error during source migration: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrate_sources_to_uppercase()