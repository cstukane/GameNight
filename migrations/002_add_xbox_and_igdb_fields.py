from peewee import CharField, IntegerField, SqliteDatabase, TextField
from playhouse.migrate import SqliteMigrator

# Point to the database file
db = SqliteDatabase('data/users.db')
migrator = SqliteMigrator(db)

# Define the fields to add
xbox_refresh_token_field = TextField(null=True)
xbox_xuid_field = CharField(null=True)

igdb_id_field = IntegerField(null=True, unique=True)
cover_url_field = CharField(null=True)
multiplayer_info_field = TextField(null=True)

source_field = CharField(null=True, default='steam')

# with db.atomic():
#     migrate(
#         # Add columns to User table
#         migrator.add_column('user', 'xbox_refresh_token', xbox_refresh_token_field),
#         migrator.add_column('user', 'xbox_xuid', xbox_xuid_field),

#         # Add columns to Game table
#         migrator.add_column('game', 'igdb_id', igdb_id_field),
#         migrator.add_column('game', 'cover_url', cover_url_field),
#         migrator.add_column('game', 'multiplayer_info', multiplayer_info_field),

#         # Rename name to title in Game table
#         migrator.rename_column('game', 'name', 'title'),

#         # Add source to UserGame table
#         migrator.add_column('usergame', 'source', source_field)
#     )

print("Migration 002 completed successfully.")
