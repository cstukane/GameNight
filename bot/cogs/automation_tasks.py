# Standard library imports
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

# Third-party imports
import discord
from discord.ext import commands
from icalendar import Calendar, Event

# Local application imports
from bot import events, poll_manager, reminders
from bot.game_suggester import suggest_games
from data import db_manager
from steam.steamgriddb_api import get_game_image
from utils.logging import logger


class AvailabilityPollView(discord.ui.View):
    """A discord.ui.View for handling weekly availability polls."""

    def __init__(self, suggested_slots, original_interactor_id, poll_id):
        """Initialize the view with buttons for each time slot and a submit button.

        Args:
        ----
            suggested_slots (list[datetime]): A list of suggested time slots.
            original_interactor_id (int): The Discord ID of the user who initiated the poll.
            poll_id (int): The ID of the poll from the database.

        """
        super().__init__(timeout=None)  # Persist view across bot restarts
        self.suggested_slots = suggested_slots
        self.original_interactor_id = original_interactor_id
        self.poll_id = poll_id
        # {user_id: [selected_slot_index, ...]}
        self.selected_slots = defaultdict(list)

        # Create buttons for each slot
        for i, slot in enumerate(suggested_slots):
            button = discord.ui.Button(
                label=slot.strftime('%a %I:%M %p'),
                style=discord.ButtonStyle.secondary,
                custom_id=f"slot_{i}"
            )
            self.add_item(button)

        self.add_item(discord.ui.Button(
            label="Submit Availability",
            style=discord.ButtonStyle.primary,
            custom_id="submit_availability"
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Allow all interactions to be processed by the button handlers.

        Args:
        ----
            interaction (discord.Interaction): The interaction to check.

        Returns:
        -------
            bool: Always True to allow the interaction to proceed.

        """
        return True

    async def on_timeout(self):
        """Disable all view components when the timeout is reached."""
        # This won't be called if timeout=None, but is good practice
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle user clicks on availability slot buttons and the submit button.

        This method updates the button styles to show selection, saves the user's
        response upon submission, and checks if the poll can be closed early.

        Args:
        ----
            interaction (discord.Interaction): The button click interaction.

        """
        custom_id = interaction.data["custom_id"]
        user_id = str(interaction.user.id)

        if custom_id.startswith("slot_"):
            slot_index = int(custom_id.replace("slot_", ""))

            if user_id not in self.selected_slots:
                # Fetch existing responses if view was re-created
                user_db = db_manager.get_user_by_discord_id(user_id)
                if user_db:
                    poll_response = db_manager.get_poll_response(
                        self.poll_id, user_db.id)
                    if poll_response and poll_response.selected_options:
                        self.selected_slots[user_id] = [
                            int(opt) for opt in poll_response.selected_options.split(',')
                        ]

            if slot_index in self.selected_slots[user_id]:
                self.selected_slots[user_id].remove(slot_index)
            else:
                self.selected_slots[user_id].append(slot_index)

            # Visually update the buttons based on the user's current selection
            for item in self.children:
                if item.custom_id and item.custom_id.startswith("slot_"):
                    s_index = int(item.custom_id.split("_")[1])
                    item.style = discord.ButtonStyle.success if s_index in self.selected_slots[
                        user_id] else discord.ButtonStyle.secondary

            await interaction.response.edit_message(view=self)

        elif custom_id == "submit_availability":
            user_db_id = db_manager.add_user(
                user_id, interaction.user.display_name)
            if user_db_id is None:
                await interaction.response.send_message(
                    "Error: Could not find or create user in database.", ephemeral=True
                )
                return

            selected_indices = self.selected_slots[user_id]
            selected_options_str = ",".join(map(str, sorted(selected_indices)))

            db_manager.record_poll_response(
                self.poll_id, user_db_id, selected_options_str)

            if selected_indices:
                selected_datetimes = [self.suggested_slots[i]
                                      for i in selected_indices]
                times_str = ', '.join(
                    [dt.strftime('%a %I:%M %p') for dt in selected_datetimes])
                confirmation_msg = f"Your availability for: {times_str} has been recorded."
            else:
                confirmation_msg = "You selected no times. Your previous responses are cleared."

            await interaction.response.send_message(confirmation_msg, ephemeral=True)

            # Check for early poll closure
            expected_count = db_manager.get_expected_participant_count(
                self.poll_id)
            responded_count = db_manager.get_poll_response_count(self.poll_id)
            if expected_count is not None and expected_count > 0 and responded_count >= expected_count:
                logger.info(
                    f"All expected participants have responded to poll {self.poll_id}. Closing early.")
                cog = interaction.client.get_cog('AutomationTasks')
                if cog:
                    poll = db_manager.get_poll_by_id(self.poll_id)
                    if poll:
                        await cog.close_availability_poll_job(
                            self.poll_id, poll.channel_id, poll.message_id
                        )


class AutomationTasks(commands.Cog):
    """A cog for handling automated tasks like polls and event scheduling."""

    def __init__(self, bot):
        """Initialize the AutomationTasks cog.

        Args:
        ----
            bot (commands.Bot): The instance of the Discord bot.

        """
        self.bot = bot

    def _generate_ics_file(self, game_night_id, scheduled_time, game_name="Game Night", duration_hours=3):
        """Generate an .ics calendar file for a game night event.

        Args:
        ----
            game_night_id (int): The ID of the game night.
            scheduled_time (datetime): The start time of the event.
            game_name (str, optional): The name of the game. Defaults to "Game Night".
            duration_hours (int, optional): The duration of the event in hours. Defaults to 3.

        Returns:
        -------
            str: The filename of the generated .ics file.

        """
        cal = Calendar()
        cal.add('prodid', '-//Game Night Bot//mxm.dk//')
        cal.add('version', '2.0')

        event = Event()
        event.add('summary', game_name)
        event.add('dtstart', scheduled_time)
        event.add('dtend', scheduled_time + timedelta(hours=duration_hours))
        event.add('dtstamp', datetime.now())
        event.add('description', f"Game Night featuring {game_name}")

        cal.add_component(event)

        filename = f"game_night_{game_night_id}.ics"
        with open(filename, 'wb') as f:
            f.write(cal.to_ical())
        return filename

    async def start_game_suggestion_poll(self, game_night_id, channel_id):
        """Start a poll to decide which game to play for a scheduled game night.

        It fetches attendees, gets game suggestions based on their libraries,
        and creates a poll in the specified channel.

        Args:
        ----
            game_night_id (int): The ID of the game night.
            channel_id (str): The ID of the channel where the poll will be sent.

        """
        logger.info(
            f"Starting game suggestion poll for game night {game_night_id}...")
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.error(
                f"Channel {channel_id} not found for game suggestion poll.")
            return

        game_night_details = events.get_game_night_details(game_night_id)
        if not game_night_details:
            logger.error(
                f"Game night {game_night_id} not found for game suggestion poll.")
            return

        attendees = events.get_attendees_for_game_night(game_night_id)
        attending_discord_ids = [
            att.user.discord_id for att in attendees if att.status == "attending"]
        attending_user_db_ids = [
            db_manager.get_user_by_discord_id(did).id for did in attending_discord_ids
            if db_manager.get_user_by_discord_id(did)
        ]

        if not attending_user_db_ids:
            await channel.send("No attending users found. Cannot suggest games.")
            return

        group_size = len(attending_user_db_ids)
        suggested_games = suggest_games(
            attending_user_db_ids, group_size=group_size)

        if not suggested_games:
            await channel.send("Could not find any suitable games for the group.")
            return

        top_suggested_games = suggested_games[:3]
        suggested_game_names = [game.name for game in top_suggested_games]

        embed = discord.Embed(
            title="Game Suggestion Poll",
            description="Vote for the game you'd like to play!",
            color=discord.Color.blue()
        )

        for game in top_suggested_games:
            cover_art_url = get_game_image(game.name, image_type="grid")
            value = f"Players: {game.min_players or '?'} - {game.max_players or '?'}\n"
            if cover_art_url:
                value += f"[Cover Art]({cover_art_url})\n"
            embed.add_field(name=game.name, value=value, inline=False)

        game_poll_message = await poll_manager.create_game_selection_poll(
            channel, game_night_id, suggested_game_names)
        if game_poll_message:
            events.update_game_night_poll_message_id(
                game_night_id, "game", str(game_poll_message.id))
            await channel.send(embed=embed, content="A game suggestion poll has been created!")

            poll_end_time = datetime.now() + timedelta(hours=48)
            self.bot.scheduler.add_job(
                self.close_game_suggestion_poll_job, 'date', run_date=poll_end_time,
                args=[game_night_id, str(channel.id),
                      str(game_poll_message.id)]
            )
        else:
            logger.error(
                f"Failed to create game selection poll for {game_night_id}.")

    async def close_game_suggestion_poll_job(self, game_night_id, channel_id, message_id):
        """Close the game suggestion poll, determine a winner, and update the event.

        Args:
        ----
            game_night_id (int): The ID of the game night being decided.
            channel_id (str): The ID of the channel containing the poll.
            message_id (str): The ID of the poll message.

        """
        logger.info(
            f"Closing game suggestion poll for game night {game_night_id}...")
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.error(
                f"Channel {channel_id} not found for closing game poll {game_night_id}.")
            return

        game_night_details = events.get_game_night_details(game_night_id)
        if not game_night_details:
            logger.error(
                f"Game night {game_night_id} not found for closing game poll.")
            return

        try:
            message = await channel.fetch_message(int(message_id))
            if message and message.view:
                for item in message.view.children:
                    item.disabled = True
                await message.edit(view=message.view)
        except discord.NotFound:
            logger.warning(
                f"Game poll message {message_id} not found in channel {channel_id}.")

        winner = await poll_manager.get_game_poll_winner(message)

        if winner:
            game = db_manager.get_game_by_name(winner)
            if game:
                db_manager.update_game_night_selected_game(game_night_id, game.id)

                # Generate and send final .ics file with game name
                ics_filename = self._generate_ics_file(
                    game_night_id, game_night_details.scheduled_time, game.name
                )
                if ics_filename:
                    msg = (f"The game for Game Night {game_night_id} is: **{game.name}**! "
                           "Get ready to play!")
                    await channel.send(msg, file=discord.File(ics_filename))
                    os.remove(ics_filename)  # Clean up the .ics file after sending
                else:
                    msg = (f"The game for Game Night {game_night_id} is: **{game.name}**! "
                           "Get ready to play! (Could not generate .ics file)")
                    await channel.send(msg)

                # Schedule individual reminders for attendees
                attendees = events.get_attendees_for_game_night(game_night_id)
                for attendee in attendees:
                    user_db = db_manager.get_user_by_discord_id(attendee.user.discord_id)
                    if user_db and user_db.default_reminder_offset_minutes is not None:
                        offset = user_db.default_reminder_offset_minutes
                        reminder_time = game_night_details.scheduled_time - timedelta(minutes=offset)
                        if reminder_time > datetime.now():
                            job_args = [
                                self.bot, user_db.discord_id, game_night_id,
                                game.name, game_night_details.scheduled_time
                            ]
                            self.bot.scheduler.add_job(
                                reminders.send_game_night_reminder, 'date',
                                run_date=reminder_time, args=job_args
                            )
                # Schedule a final 30-minute reminder for all attendees
                final_reminder_time = game_night_details.scheduled_time - timedelta(minutes=30)
                if final_reminder_time > datetime.now():
                    for attendee in attendees:
                        user_db = db_manager.get_user_by_discord_id(attendee.user.discord_id)
                        if user_db:
                            job_args = [
                                self.bot, user_db.discord_id, game_night_id,
                                game.name, game_night_details.scheduled_time
                            ]
                            self.bot.scheduler.add_job(
                                reminders.send_game_night_reminder, 'date',
                                run_date=final_reminder_time, args=job_args
                            )
            else:
                await channel.send(f"Could not find game '{winner}' in the database. Game night not finalized.")
        else:
            await channel.send(f"Could not determine a winning game for Game Night {game_night_id}.")

    async def start_weekly_availability_poll(self):
        """Initiate a server-wide poll to find the best time for a game night.

        It generates time slots, filters them based on user-set weekly availability,
        and sends a poll to the designated planning channel.
        """
        logger.info("Starting weekly availability poll...")
        guild_id = self.bot.guilds[0].id if self.bot.guilds else None
        if not guild_id:
            logger.error("Bot is not in any guilds.")
            return

        custom_pattern_json = db_manager.get_guild_custom_availability(str(guild_id))
        potential_slots = []

        if custom_pattern_json:
            custom_pattern = json.loads(custom_pattern_json)
            today = datetime.now()
            for i in range(7):  # Iterate through the next 7 days
                current_day = today + timedelta(days=i)
                day_of_week_num = current_day.weekday()  # 0=Monday, 6=Sunday

                # Get selected slots for this day from the custom pattern
                selected_slot_indices = custom_pattern.get(str(day_of_week_num), [])
                for slot_index in selected_slot_indices:
                    # Convert slot index back to hour and minute
                    hour = slot_index // 2
                    minute = 30 if slot_index % 2 == 1 else 0
                    potential_slots.append(
                                            current_day.replace(hour=hour, minute=minute, second=0)
                    )
        else:
            # Fallback to existing hardcoded logic if no custom pattern
            today = datetime.now()
            for i in range(7):
                day = today + timedelta(days=i)
                if day.weekday() < 5:  # Mon-Fri
                    for hour in [19, 20, 21]:
                        potential_slots.append(
                            day.replace(hour=hour, minute=0, second=0, microsecond=0))
                else:  # Sat-Sun
                    for hour in [14, 16, 18, 20]:
                        potential_slots.append(
                            day.replace(hour=hour, minute=0, second=0, microsecond=0))

        all_users_weekly_availability = db_manager.get_all_users_weekly_availability()
        filtered_slots = []
        for slot in potential_slots:
            day_of_week_num = slot.weekday()
            is_any_user_available = False
            for _, available_days_str in all_users_weekly_availability.items():
                if available_days_str:
                    available_days_nums = [
                        int(d) for d in available_days_str.split(',')]
                    if day_of_week_num in available_days_nums:
                        is_any_user_available = True
                        break
            if is_any_user_available:
                filtered_slots.append(slot)

        if not filtered_slots:
            logger.info("No suitable game night slots found.")
            return

        embed = discord.Embed(
            title="Weekly Game Night Availability Poll",
            description="Please select all times you are available for a game night this week.",
            color=discord.Color.gold()
        )

        suggested_slots_json = json.dumps(
            [slot.isoformat() for slot in filtered_slots])
        all_active_users = db_manager.get_all_users()
        expected_participants_discord_ids = [
            user.discord_id for user in all_active_users]
        expected_participants_discord_ids_json = json.dumps(
            expected_participants_discord_ids)

        target_channel_id = db_manager.get_guild_planning_channel(
            str(guild_id))
        target_channel = self.bot.get_channel(
            int(target_channel_id)) if target_channel_id else None

        if not target_channel:
            logger.error(
                f"No planning channel for guild {guild_id}. Use /set_planning_channel.")
            return

        message = await target_channel.send(embed=embed)
        poll_end_time = datetime.now() + timedelta(hours=48)
        poll_id = db_manager.create_poll(
            poll_message_id=str(message.id),
            channel_id=str(target_channel.id),
            poll_type='availability',
            start_time=datetime.now(),
            end_time=poll_end_time,
            suggested_slots_json=suggested_slots_json,
            expected_participants_json=expected_participants_discord_ids_json
        )
        if poll_id is None:
            logger.error("Failed to create poll entry in database.")
            await message.edit(content="Error creating poll.", embed=None, view=None)
            return

        view = AvailabilityPollView(filtered_slots, self.bot.user.id, poll_id)
        await message.edit(embed=embed, view=view)
        logger.info(
            f"Sent weekly availability poll to channel {target_channel_id}")

        self.bot.scheduler.add_job(
            self.close_availability_poll_job, 'date', run_date=poll_end_time,
            args=[poll_id, str(target_channel.id), str(message.id)]
        )

    async def close_availability_poll_job(self, poll_id, channel_id, message_id):
        """Close the availability poll, schedule a game night, and start a game poll.

        Args:
        ----
            poll_id (int): The ID of the poll to close.
            channel_id (str): The ID of the channel where the poll resides.
            message_id (str): The ID of the poll message.

        """
        logger.info(f"Closing availability poll {poll_id}...")
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.error(
                f"Channel {channel_id} not found for closing poll {poll_id}.")
            return

        poll = db_manager.get_poll_by_id(poll_id)
        if not poll:
            logger.error(f"Poll {poll_id} not found in database.")
            return

        db_manager.update_poll_status(poll_id, 'closed')

        try:
            message = await channel.fetch_message(int(message_id))
            if message and message.view:
                for item in message.view.children:
                    item.disabled = True
                await message.edit(view=message.view)
        except discord.NotFound:
            logger.warning(
                f"Poll message {message_id} not found in channel {channel_id}.")

        poll_responses = db_manager.get_poll_responses(poll_id)
        suggested_slots = [datetime.fromisoformat(
            dt_str) for dt_str in json.loads(poll.suggested_slots_json)]

        slot_votes = defaultdict(int)
        for response in poll_responses:
            if response.selected_options:
                user_selected_options = [
                    int(opt) for opt in response.selected_options.split(',')]
                for slot_index in user_selected_options:
                    if slot_index < len(suggested_slots):
                        slot_votes[slot_index] += 1

        if not slot_votes:
            await channel.send("No one responded to the availability poll. Game night not scheduled.")
            return

        most_popular_slot_index = max(slot_votes, key=slot_votes.get)
        scheduled_time = suggested_slots[most_popular_slot_index]

        organizer_user_db = db_manager.get_all_users()[
            0]  # Placeholder organizer
        game_night_id = events.add_game_night_event(
            organizer_user_db.id, scheduled_time, str(channel.id)
        )

        if game_night_id:
            ics_filename = self._generate_ics_file(
                game_night_id, scheduled_time, "Game Night")
            if ics_filename:
                msg = (f"Availability poll closed! Game night scheduled for: "
                       f"{scheduled_time.strftime('%A, %B %d at %I:%M %p')}")
                await channel.send(msg, file=discord.File(ics_filename))
                os.remove(ics_filename)
            else:
                await channel.send(f"Game night scheduled: {scheduled_time.strftime('%A, %B %d at %I:%M %p')}.")

            await self.start_game_suggestion_poll(game_night_id, str(channel.id))
        else:
            await channel.send("Failed to schedule game night based on poll results.")


async def setup(bot):
    """Add the cog to the bot.

    Args:
    ----
        bot (commands.Bot): The instance of the Discord bot.

    """
    await bot.add_cog(AutomationTasks(bot))
