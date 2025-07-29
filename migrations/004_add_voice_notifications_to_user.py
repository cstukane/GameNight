from peewee import BooleanField
from playhouse.migrate import migrate, SqliteMigrator

from data.database import db

def up():
    migrator = SqliteMigrator(db)
    migrate(
        migrator.add_column('user', 'receive_voice_notifications', BooleanField(default=True)),
    )

def down():
    migrator = SqliteMigrator(db)
    migrate(
        migrator.drop_column('user', 'receive_voice_notifications'),
    )
