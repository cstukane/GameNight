# Standard library imports
import json
from datetime import datetime, timedelta

# Third-party imports
import discord
from discord import app_commands
from discord.ext import commands

# Local application imports
from bot import events, poll_manager
from bot.game_suggester import suggest_games
from data import db_manager
from utils.errors import (
    GameNightError,
    InvalidGameNightIDError,
    PollNotFoundError,
    UserNotFoundError,
)





class GameNightCommands(commands.Cog):
    """A cog for handling game night scheduling and related commands."""

    def __init__(self, bot):
        """Initialize the GameNightCommands cog.

        Args:
        ----
            bot (commands.Bot): The instance of the bot.

        """
        self.bot = bot
        self.scheduler = bot.scheduler

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle errors for commands in this cog."""
        if isinstance(error, GameNightError):
            await interaction.followup.send(str(error), ephemeral=True)
        else:
            await interaction.followup.send("An unexpected error occurred. Please try again later.", ephemeral=True)
            raise error

    @app_commands.command(name="next_game_night", description="Schedules a game night and starts a poll.")
    @app_commands.describe(
        date="Date of the game night (MM/DD/YYYY).",
        time="Time of the game night (HH:MM or HHMM, 24-hour format).",
        poll_close_time="Time to close poll (HH:MM or HHMM). Defaults to 1 hour before game night."
    )
    async def next_game_night(self, interaction: discord.Interaction, date: str, time: str, poll_close_time: str = None):
        """Schedule a game night, creating an event and an availability poll."""
        await interaction.response.defer(ephemeral=True)

        try:
            parsed_date = datetime.strptime(date, "%m/%d/%Y").date()
            if time.isdigit() and len(time) == 4:
                parsed_time = datetime.strptime(time, "%H%M").time()
            else:
                parsed_time = datetime.strptime(time, "%H:%M").time()
        except ValueError:
            raise GameNightError("Invalid date/time format. Use MM/DD/YYYY and HH:MM or HHMM.")

        scheduled_dt = datetime.combine(parsed_date, parsed_time)

        if poll_close_time:
            try:
                if poll_close_time.isdigit() and len(poll_close_time) == 4:
                    parsed_poll_close_time = datetime.strptime(poll_close_time, "%H%M").time()
                else:
                    parsed_poll_close_time = datetime.strptime(poll_close_time, "%H:%M").time()
                poll_close_dt = datetime.combine(parsed_date, parsed_poll_close_time)
            except ValueError:
                raise GameNightError("Invalid poll close time format. Use HH:MM or HHMM.")
        else:
            poll_close_dt = scheduled_dt - timedelta(hours=1)

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        if user_db_id is None:
            raise UserNotFoundError("There was an error finding you in the database.")

        event_id = events.add_game_night_event(user_db_id, scheduled_dt, str(interaction.channel_id), poll_close_dt)
        if not event_id:
            raise GameNightError("Failed to schedule game night event.")

        channel = self.bot.get_channel(interaction.channel_id)
        poll_msg = await poll_manager.create_availability_poll(
            channel, event_id, scheduled_dt.strftime('%Y-%m-%d at %H:%M')
        )
        if not poll_msg:
            raise PollNotFoundError("Failed to create availability poll.")

        events.update_game_night_poll_message_id(event_id, "availability", str(poll_msg.id))
        self.bot.scheduler.add_job(
            self.close_game_poll_job, 'date', run_date=poll_close_dt, args=[event_id, str(channel.id)]
        )

        event_title = "Game Night"
        event_description = f"Join us for game night! Event ID: {event_id}"
        end_dt = scheduled_dt + timedelta(hours=2)
        gcal_link = (
            f"https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={event_title.replace(' ', '+')}"
            f"&dates={scheduled_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}"
            f"&details={event_description.replace(' ', '+')}&sf=true&output=xml"
        )
        message = (
            f"Game night scheduled for {scheduled_dt:%Y-%m-%d at %H:%M}! Event ID: {event_id}.\n"
            f"Poll closes at {poll_close_dt:%Y-%m-%d at %H:%M}.\n"
            f"Add to Google Calendar: <{gcal_link}>"
        )
        await interaction.followup.send(message)

    

    @app_commands.command(name="set_game_night_availability", description="Set your availability for an upcoming game night.")
    @app_commands.describe(
        game_night_id="The ID of the game night.",
        status="Your availability status."
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Attending", value="attending"),
        app_commands.Choice(name="Maybe", value="maybe"),
        app_commands.Choice(name="Not Attending", value="not_attending"),
    ])
    async def set_game_night_availability(self, interaction: discord.Interaction, game_night_id: int, status: str):
        """Set a user's attendance status for a specific game night."""
        await interaction.response.defer(ephemeral=True)

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        if user_db_id is None:
            raise UserNotFoundError("There was an error finding you in the database.")

        events.set_attendee_status(game_night_id, user_db_id, status)

        # If the user is attending, schedule a reminder
        if status == "attending":
            events.schedule_reminder(self.bot, user_db_id, game_night_id)

        await interaction.followup.send(
            f"Your availability for Game Night ID {game_night_id} has been set to **{status}**."
        )

    @set_game_night_availability.autocomplete('game_night_id')
    async def game_night_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for upcoming game night IDs."""
        upcoming_events = events.get_upcoming_game_nights()
        choices = []
        for event in upcoming_events:
            try:
                scheduled_dt = event.scheduled_time
                name = f"ID: {event.id} - {scheduled_dt:%Y-%m-%d at %H:%M}"
                id_match = str(current) in str(event.id)
                name_match = current.lower() in name.lower()
                if id_match or name_match:
                    choices.append(app_commands.Choice(name=name, value=event.id))
            except (ValueError, AttributeError):
                continue
        return choices[:25]

    @app_commands.command(name="finalize_game_night", description="Suggests games for a game night and starts a poll.")
    @app_commands.describe(game_night_id="The ID of the game night to finalize.")
    async def finalize_game_night(self, interaction: discord.Interaction, game_night_id: int):
        """Manually finalize a game night, triggering game suggestions and a poll."""
        await interaction.response.defer()

        game_night_details = events.get_game_night_details(game_night_id)
        if not game_night_details:
            raise InvalidGameNightIDError(f"Game Night with ID {game_night_id} not found.")

        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        is_organizer = user_db and user_db.id == game_night_details.organizer_id
        if not is_organizer:
            raise GameNightError("Only the organizer can finalize this game night.")

        channel = self.bot.get_channel(int(game_night_details.channel_id))
        if not channel:
            raise GameNightError("Could not find the channel for this game night.")

        # Trigger the suggestion and poll process
        await self._handle_game_suggestion_and_poll(game_night_details.id, channel)
        await interaction.followup.send(f"Game selection poll for Game Night ID {game_night_id} has been posted.")

    async def _handle_game_suggestion_and_poll(self, game_night_id: int, channel: discord.TextChannel):
        """Handle game suggestions and poll creation."""
        game_night_details = events.get_game_night_details(game_night_id)
        if not game_night_details:
            return

        attendees = events.get_attendees_for_game_night(game_night_id)
        attending_user_db_ids = [att.user_id for att in attendees if att.status == "attending"]

        if not attending_user_db_ids:
            await channel.send("No users marked as attending. Cannot finalize game night.")
            return

        suggested_from_users = db_manager.get_suggested_games_for_game_night(game_night_id)
        suggested_from_bot = suggest_games(attending_user_db_ids, group_size=len(attending_user_db_ids))

        all_suggestions = list(set(suggested_from_users + [game.name for game in suggested_from_bot]))

        if not all_suggestions:
            await channel.send("No suitable games found for the attending group.")
            return

        poll_message = await poll_manager.create_game_selection_poll(channel, game_night_id, all_suggestions)
        if poll_message:
            events.update_game_night_poll_message_id(game_night_id, "game", str(poll_message.id))
            await channel.send(f"Game selection poll for Game Night ID {game_night_id} posted. Please vote!")
        else:
            await channel.send("Failed to create game selection poll.")

    async def close_game_poll_job(self, game_night_id, channel_id):
        """Close the availability poll and trigger the game poll via a scheduled job."""
        channel = self.bot.get_channel(int(channel_id))
        if channel:
            await self._handle_game_suggestion_and_poll(game_night_id, channel)

    @app_commands.command(name="configure_weekly_slots",
                          description="Configure the guild's weekly availability time slots for polls.")
    @app_commands.default_permissions(manage_guild=True)
    async def configure_weekly_slots(self, interaction: discord.Interaction):
        """Allow guild administrators to configure the weekly availability time slots for polls."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        view = WeeklyAvailabilityConfigView(self.bot, interaction.guild_id)
        await interaction.followup.send("Configure your weekly availability slots:", view=view, ephemeral=True)

async def _send_scheduled_suggestion(bot, channel_id, group_size=None, preferred_tags=None):
    """Send a scheduled game suggestion message to a channel."""
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return

    all_users = db_manager.get_all_users()
    if not all_users:
        await channel.send("No users found in the database. Cannot suggest games.")
        return

    user_ids = [user.id for user in all_users]
    tags = preferred_tags.split(',') if preferred_tags else None

    suggested_games = suggest_games(user_ids, group_size=group_size, preferred_tags=tags)

    if suggested_games:
        game_names = [game.name for game in suggested_games]
        games_list = "\n".join([f"- {name}" for name in game_names])
        await channel.send(f"**Scheduled Game Suggestion:**\n{games_list}")
    else:
        await channel.send("Could not find suitable games for the scheduled suggestion criteria.")


class WeeklyAvailabilityConfigView(discord.ui.View):
    """A view for configuring weekly availability time slots using a day selector and time slot buttons."""

    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = str(guild_id)
        self.selected_slots = self._load_existing_pattern() # {day_index: [slot_indices]}
        self.current_day_index = 0 # Default to Monday
        self.current_time_page = 0 # Default to first page of time slots
        self.start_selection_slot = {day: None for day in range(7)} # {day_index: start_slot_index}

        self.days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self.time_slots_labels = self._generate_time_slot_labels() # 12:00 AM, 12:30 AM, etc.

        self._add_day_selector()
        self._update_day_view() # Initial display for the current day

    def _load_existing_pattern(self):
        """Load the existing availability pattern from the database."""
        pattern_json = db_manager.get_guild_custom_availability(self.guild_id)
        if pattern_json:
            # Ensure keys are integers
            return {int(k): v for k, v in json.loads(pattern_json).items()}
        return {i: [] for i in range(7)} # Initialize with empty lists for each day

    def _generate_time_slot_labels(self):
        """Generate a list of 1-hour time slot strings (e.g., '12:00 AM', '01:00 AM')."""
        labels = []
        for h in range(24):
            dt_obj = datetime(1, 1, 1, h, 0)
            labels.append(dt_obj.strftime('%I:%M %p'))
        return labels

    def _get_slot_index(self, hour, minute):
        """Convert hour and minute to a 1-hour slot index (0-23)."""
        return hour

    def _get_time_from_index(self, index):
        """Convert a 1-hour slot index back to hour and minute."""
        hour = index
        minute = 0
        return hour, minute

    def _add_day_selector(self):
        """Add a dropdown selector for days of the week."""
        options = []
        for i, day_name in enumerate(self.days_of_week):
            options.append(discord.SelectOption(label=day_name, value=str(i), default=(i == self.current_day_index)))

        select = discord.ui.Select(
            custom_id="day_selector",
            placeholder="Select a day",
            options=options,
            row=0
        )
        select.callback = self.on_day_select
        self.add_item(select)

    def _update_day_view(self):
        """Update the view to show time slots and controls for the current_day_index."""
        # Remove all items except the day selector
        for item in self.children[:]:
            if item.custom_id != "day_selector":
                self.remove_item(item)

        # Add navigation and action buttons
        self.add_item(discord.ui.Button(label="< Prev Page", custom_id="prev_time_page", row=1))
        self.add_item(discord.ui.Button(label="Next Page >", custom_id="next_time_page", row=1))
        clear_label = f"Clear All {self.days_of_week[self.current_day_index]}"
        self.add_item(discord.ui.Button(label=clear_label, style=discord.ButtonStyle.red,
                                        custom_id=f"clear_all_{self.current_day_index}", row=1))
        self.add_item(discord.ui.Button(label="Save", style=discord.ButtonStyle.primary, custom_id="save", row=1))
        self.add_item(discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel", row=1))

        # Determine time slots to display based on current_time_page
        # Page 0: 12 PM - 11 PM (slots 12-23)
        # Page 1: 12 AM - 11 AM (slots 0-11)
        if self.current_time_page == 0:
            time_slots_to_display = self.time_slots_labels[12:] # 12 PM to 11 PM
            start_row_index = 2 # Start time slots from row 2
        else: # self.current_time_page == 1
            time_slots_to_display = self.time_slots_labels[:12] # 12 AM to 11 AM
            start_row_index = 2 # Start time slots from row 2

        current_day_slots = self.selected_slots.get(self.current_day_index, [])

        for i, time_label in enumerate(time_slots_to_display):
            # Calculate global slot index based on the time label
            hour = int(time_label.split(':')[0])
            if 'PM' in time_label and hour != 12:
                hour += 12
            if 'AM' in time_label and hour == 12:
                hour = 0
            slot_global_index = hour

            is_selected = slot_global_index in current_day_slots
            style = discord.ButtonStyle.success if is_selected else discord.ButtonStyle.secondary
            # Distribute buttons across rows 2, 3, 4 (which are Discord rows 3, 4, 5)
            row_offset = i // 5 # 5 buttons per row
            self.add_item(discord.ui.Button(
                label=time_label,
                style=style,
                custom_id=f"slot_{self.current_day_index}_{slot_global_index}",
                row=start_row_index + row_offset
            ))

    async def on_day_select(self, interaction: discord.Interaction):
        """Handle the selection of a day from the dropdown."""
        self.current_day_index = int(interaction.data["values"][0])
        await self.update_view(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original interactor can use the view."""
        # For now, allow anyone to interact for testing.
        # In production, you might want to restrict this to the command invoker or guild admins.
        return True

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks for time slots, navigation, and actions."""
        custom_id = interaction.data["custom_id"]
        parts = custom_id.split('_')

        if parts[0] == "slot":
            day_index = int(parts[1])
            slot_index = int(parts[2])

            # Single slot toggle
            if slot_index in self.selected_slots[day_index]:
                self.selected_slots[day_index].remove(slot_index)
            else:
                self.selected_slots[day_index].append(slot_index)
            self.start_selection_slot[day_index] = None # Ensure range selection is reset

        elif custom_id == "prev_time_page":
            self.current_time_page = (self.current_time_page - 1) % 2 # 2 pages for 24 hours
            await self.update_view(interaction)
        elif custom_id == "next_time_page":
            self.current_time_page = (self.current_time_page + 1) % 2 # 2 pages for 24 hours
            await self.update_view(interaction)

        elif parts[0] == "clear" and parts[1] == "all":
            day_index = int(parts[2])
            self.selected_slots[day_index] = [] # Clear all slots
            self.start_selection_slot[day_index] = None # Clear any pending range selection

        elif custom_id == "save":
            await interaction.response.defer(ephemeral=True)
            # Convert selected_slots to a JSON string
            pattern_json = json.dumps(self.selected_slots)
            db_manager.set_guild_custom_availability(self.guild_id, pattern_json)
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(content="Weekly availability pattern saved!", view=self)
            await interaction.followup.send("Your weekly availability has been saved!", ephemeral=True)
            self.stop()
            return

        elif custom_id == "cancel":
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(content="Weekly availability configuration cancelled.", view=self)
            await interaction.response.send_message("Weekly availability configuration cancelled.", ephemeral=True)
            self.stop()
            return

        await self.update_view(interaction)

    async def update_view(self, interaction: discord.Interaction):
        """Update the view to reflect current selections."""
        self.clear_items() # Clear existing buttons
        self._add_day_selector() # Re-add day selector
        self._update_day_view() # Recreate buttons for the current day
        await interaction.response.edit_message(view=self)

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(GameNightCommands(bot))
