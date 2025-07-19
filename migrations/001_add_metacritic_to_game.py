from peewee import IntegerField, SqliteDatabase
from playhouse.migrate import SqliteMigrator

db = SqliteDatabase('data/users.db')
migrator = SqliteMigrator(db)

metacritic_field = IntegerField(null=True)

# migrate(
#     migrator.add_column('game', 'metacritic', metacritic_field),
# )
