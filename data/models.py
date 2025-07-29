from datetime import datetime

from peewee import (
    AutoField,
    BooleanField,
    CharField,
    CompositeKey,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from utils.config import DATABASE_FILE

db = SqliteDatabase(DATABASE_FILE)


class BaseModel(Model):
    """A base model that specifies the database connection."""

    class Meta:
        """Meta configuration for the BaseModel."""

        database = db


class User(BaseModel):
    """Represents a Discord user in the database."""

    id = AutoField()
    discord_id = CharField(unique=True)
    steam_id = CharField(null=True)
    username = CharField(null=True)
    is_active = BooleanField(default=True)
    has_game_pass = BooleanField(default=False)
    default_reminder_offset_minutes = IntegerField(default=60)  # Default to 60 minutes
    xbox_refresh_token = TextField(null=True)
    xbox_xuid = CharField(null=True)
    # --- THIS LINE IS NEW ---
    receive_voice_notifications = BooleanField(default=True)


class UserAvailability(BaseModel):
    """Stores a user's recurring weekly availability."""

    user = ForeignKeyField(User, backref='availability', primary_key=True)
    # Store available days as a comma-separated string of integers (0=Monday, 6=Sunday)
    available_days = CharField(null=True)


class Game(BaseModel):
    """Represents a game in the database."""

    igdb_id = IntegerField(primary_key=True)
    steam_appid = CharField(null=True)
    title = CharField()
    cover_url = CharField(null=True)
    multiplayer_info = TextField(null=True)
    tags = CharField(null=True)
    min_players = IntegerField(null=True)
    max_players = IntegerField(null=True)
    last_played = DateTimeField(null=True)
    release_date = CharField(null=True)
    description = CharField(null=True)
    metacritic = IntegerField(null=True)


class UserGame(BaseModel):
    """A through-model linking Users and Games, representing ownership and preferences."""

    user = ForeignKeyField(User, backref='user_games')
    game = ForeignKeyField(Game, backref='game_users')
    source = CharField() # e.g., 'steam', 'xbox_achievement', 'game_pass', 'manual'
    liked = BooleanField(default=False)
    disliked = BooleanField(default=False)
    is_installed = BooleanField(default=False)

    class Meta:
        """Meta configuration for the UserGame model."""

        primary_key = CompositeKey('user', 'game', 'source')


class GameNight(BaseModel):
    """Represents a scheduled game night event."""

    id = AutoField()
    organizer = ForeignKeyField(User, backref='organized_game_nights')
    scheduled_time = DateTimeField()
    channel_id = CharField()
    availability_poll_message_id = CharField(null=True)
    game_poll_message_id = CharField(null=True)
    suggested_games_list = CharField(null=True)
    poll_close_time = DateTimeField(null=True)
    selected_game = ForeignKeyField(Game, null=True, backref='game_nights')


class GameNightAttendee(BaseModel):
    """A through-model linking Users to GameNights, representing attendance status."""

    game_night = ForeignKeyField(GameNight, backref='attendees')
    user = ForeignKeyField(User, backref='attended_game_nights')
    status = CharField(default='attending')  # e.g., attending, maybe, not_attending

    class Meta:
        """Meta configuration for the GameNightAttendee model."""

        primary_key = CompositeKey('game_night', 'user')


class GameExclusion(BaseModel):
    """Represents a user's choice to exclude a game from suggestions."""

    user = ForeignKeyField(User, backref='excluded_games')
    game = ForeignKeyField(Game, backref='excluded_by_users')

    class Meta:
        """Meta configuration for the GameExclusion model."""

        primary_key = CompositeKey('user', 'game')


class VoiceActivity(BaseModel):
    """Records a user's voice channel join and leave events."""

    user = ForeignKeyField(User, backref='voice_activities')
    guild_id = CharField()
    channel_id = CharField()
    join_time = DateTimeField()
    leave_time = DateTimeField(null=True)
    duration_seconds = IntegerField(null=True)


class GamePassGame(BaseModel):
    """Represents a game available on Game Pass."""

    id = AutoField()
    title = CharField()
    microsoft_store_id = CharField(unique=True)

    # --- THIS IS THE FIX ---
    class Meta:
        """Meta configuration for the GamePassGame model."""

        # This line tells Peewee the exact table name to use,
        # matching what the Node.js script creates.
        table_name = 'game_pass_catalog'


class GameVote(BaseModel):
    """Represents a user's vote for a game in a specific game night poll."""

    game_night = ForeignKeyField(GameNight, backref='game_votes')
    user = ForeignKeyField(User, backref='voted_games')
    game = ForeignKeyField(Game, backref='game_votes')

    class Meta:
        """Meta configuration for the GameVote model."""

        primary_key = CompositeKey('game_night', 'user')


class Poll(BaseModel):
    """Represents a poll created by the bot."""

    id = AutoField()
    message_id = CharField(unique=True)
    channel_id = CharField()
    poll_type = CharField()  # e.g., 'availability', 'game_selection'
    start_time = DateTimeField()
    end_time = DateTimeField()
    status = CharField(default='open')  # e.g., 'open', 'closed'
    related_game_night = ForeignKeyField(GameNight, null=True, backref='polls')
    suggested_slots_json = CharField(null=True)
    # Stores JSON string of expected participant discord_ids
    expected_participants_json = CharField(null=True)


class PollResponse(BaseModel):
    """Stores a user's response to a poll."""

    poll = ForeignKeyField(Poll, backref='responses')
    user = ForeignKeyField(User, backref='poll_responses')
    selected_options = CharField(null=True)
    timestamp = DateTimeField(default=datetime.now)

    class Meta:
        """Meta configuration for the PollResponse model."""

        primary_key = CompositeKey('poll', 'user')


class GuildConfig(BaseModel):
    """Stores guild-specific configurations."""

    guild_id = CharField(unique=True)
    main_channel_id = CharField(null=True)
    planning_channel_id = CharField(null=True)
    custom_availability_pattern = TextField(null=True)
    voice_notification_channel_id = CharField(null=True)


def initialize_models():
    """Connect to the database and create all necessary tables if they don't exist."""
    db.connect(reuse_if_open=True)
    db.create_tables([
        User,
        Game,
        UserGame,
        GameNight,
        GameNightAttendee,
        GameExclusion,
        VoiceActivity,

        GameVote,
        UserAvailability,
        Poll,
        PollResponse,
        GuildConfig,
        GamePassGame,
    ])


if __name__ == '__main__':
    initialize_models()
    print("Database models initialized.")
