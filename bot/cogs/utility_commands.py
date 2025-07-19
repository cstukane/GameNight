import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from peewee import fn

# Import the new, modern library
from xbox.webapi.api.client import XboxLiveClient
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.common.exceptions import AuthenticationException

from data import db_manager
from data.models import VoiceActivity
from steam.fetch_library import fetch_and_store_games
from utils.config import XBOX_CLIENT_ID, XBOX_CLIENT_SECRET, XBOX_REDIRECT_URI
from utils.errors import UserNotFoundError
from utils.logging import logger


class XboxLinkModal(discord.ui.Modal, title="Submit Xbox URL"):
    url_input = discord.ui.TextInput(
        label="Paste the full URL from the blank page here",
        style=discord.TextStyle.long,
        placeholder="https://login.live.com/oauth20_desktop.srf?code=M.12345...",
        required=True,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url_input.value

        if "code=" not in url:
            await interaction.followup.send(
                "That doesn't look like the correct URL. Please make sure you copied the entire URL from the address bar of the blank page after logging in.",
                ephemeral=True,
            )
            return

        try:
            auth_mgr = AuthenticationManager(
                self.bot.web_client, XBOX_CLIENT_ID, XBOX_CLIENT_SECRET, XBOX_REDIRECT_URI
            )
            await auth_mgr.request_tokens(url)

            if not auth_mgr.is_authenticated():
                raise AuthenticationException("Authentication failed with the provided URL.")

            xbl_client = XboxLiveClient(auth_mgr)
            # Assuming gamertag is available from auth_mgr, if not, might need to fetch profile first
            profile = await xbl_client.profile.get_profile_by_gamertag(auth_mgr.gamertag)
            xuid = profile.xuid

            user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
            if not user_db:
                db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
                user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))

            db_manager.set_xbox_tokens(user_db.id, auth_mgr.oauth.refresh_token, xuid)

            await interaction.followup.send("Your Xbox account has been successfully linked! The bot will now sync your played games weekly.", ephemeral=True)

        except Exception as e:
            logger.error(f"An error occurred during Xbox token submission: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}. Please try the `/link_xbox` command again.", ephemeral=True)


class XboxLinkView(discord.ui.View):
    def __init__(self, bot, auth_url: str):
        super().__init__(timeout=300)  # 5-minute timeout
        self.bot = bot

        # Define buttons in order
        self.add_item(discord.ui.Button(label="Step 1: Open Microsoft Login", style=discord.ButtonStyle.link, url=auth_url))
        self.add_item(discord.ui.Button(label="Step 2: Paste URL", style=discord.ButtonStyle.primary, custom_id="paste_url_button"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "paste_url_button":
            modal = XboxLinkModal(self.bot)
            await interaction.response.send_modal(modal)
            return False # Stop further processing
        return True # Allow other interactions if any


class UtilityCommands(commands.Cog):
    """A cog for utility and profile-related commands."""

    def __init__(self, bot):
        """Initialize the UtilityCommands cog."""
        self.bot = bot

    @app_commands.command(name="ping", description="Responds with Pong!")
    async def ping(self, interaction: discord.Interaction):
        """Check if the bot is online."""
        await interaction.response.send_message("Pong!", ephemeral=True)

    @app_commands.command(name="profile", description="Displays a user's profile and a link to their game library.")
    @app_commands.describe(user="The user whose profile you want to view. Defaults to yourself.")
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display a user's profile with stats and a link to their web library."""
        await interaction.response.defer()

        target_user = user or interaction.user
        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} does not have a profile yet.")

        # --- Profile Stats ---
        games_count = len(db_manager.get_user_game_ownerships(user_db.id))
        game_pass_status = "Yes" if user_db.has_game_pass else "No"

        embed = discord.Embed(
            title=f"{target_user.display_name}'s Profile",
            color=target_user.color,
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="Total Games Owned", value=str(games_count), inline=True)
        embed.add_field(name="Has Game Pass", value=game_pass_status, inline=True)

        # --- Link to Web Library ---
        base_url = os.getenv("BASE_URL")
        view = discord.ui.View()

        if base_url:
            library_url = f"{base_url}/library/{target_user.id}"
            view.add_item(
                discord.ui.Button(label="Browse Full Game Library", style=discord.ButtonStyle.link, url=library_url)
            )
        else:
            embed.set_footer(text="Web library link is not configured by the bot owner.")

        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="set_steam_id", description="Sets your Steam ID for automatic library syncing.")
    @app_commands.describe(steam_id="Your 64-bit Steam ID.")
    async def set_steam_id(self, interaction: discord.Interaction, steam_id: str):
        """Set a user's Steam ID and sync their library."""
        await interaction.response.defer(ephemeral=True)
        if not steam_id.isdigit() or len(steam_id) != 17:
            help_message = (
                "**Invalid Steam ID format.**\nPlease provide your **64-bit Steam ID**, which is a 17-digit number.\n\n"
                "**How to find your Steam ID:**\n1. Go to a site like [SteamID.io](https://steamid.io/).\n"
                "2. Enter your Steam profile name or URL.\n3. Look for the value labeled **steamID64**."
            )
            await interaction.followup.send(help_message, ephemeral=True)
            return

        db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        await fetch_and_store_games(user_db, steam_id)
        await interaction.followup.send("Your Steam library has been successfully synced!", ephemeral=True)

    # @app_commands.command(name="link_xbox", description="Links your Xbox account for library syncing.")
    # async def link_xbox(self, interaction: discord.Interaction):
        """Initiate the Xbox account linking process using a modal."""
        await interaction.response.defer(ephemeral=True)

        # --- FIX START ---
        # Check if the required configuration variables are present.
        if not XBOX_CLIENT_ID or not XBOX_CLIENT_SECRET:
            logger.error("XBOX_CLIENT_ID or XBOX_CLIENT_SECRET is not configured.")
            await interaction.followup.send(
                "The bot's Xbox integration is not configured correctly. Please contact the bot administrator.",
                ephemeral=True
            )
            return
        # --- FIX END ---

        try:
            auth_mgr = AuthenticationManager(
                self.bot.web_client, XBOX_CLIENT_ID, XBOX_CLIENT_SECRET, XBOX_REDIRECT_URI
            )
            auth_url = auth_mgr.generate_authorization_url()

            embed = discord.Embed(
                title="Link your Xbox Account",
                description=(
                    "**Step 1:** Click the button below to sign in to your Microsoft account.\n\n"
                    "**Step 2:** After signing in, you will be sent to a **blank white page**. "
                    "Copy the entire URL from your browser's address bar.\n\n"
                    "**Step 3:** Come back here and click the `Paste URL` button to finish."
                ),
                color=discord.Color.green()
            )

            view = XboxLinkView(self.bot, auth_url)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"An error occurred during Xbox linking setup: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred during Xbox linking setup: {e}", ephemeral=True)

    @app_commands.command(name="help", description="Displays a list of all available commands.")
    async def help(self, interaction: discord.Interaction):
        """Show a help message with a list of commands."""
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="Game Night Bot Help",
            description="Here's how you can use me:",
            color=discord.Color.blue()
        )

        # Get all commands from the bot's command tree
        all_commands = self.bot.tree.get_commands()

        # Categorize commands
        categorized_commands = {
            "General & Profile": [],
            "Game Management": [],
            "Game Night Organization": [],
            "Admin Commands": []
        }

        for command in all_commands:
            # Skip commands that are not visible or are subcommands
            if command.parent or command.name == "help":
                continue

            command_info = f"**/{command.name}** - {command.description}"

            # Simple categorization based on command name or cog
            if command.name in ["ping", "profile", "set_steam_id", "link_xbox", "set_gamepass_status", "set_reminder_offset", "wrapped_discord", "wrapped_history", "set_voice_notifications"]:
                categorized_commands["General & Profile"].append(command_info)
            elif command.name in ["add_game", "manage_games", "view_library", "suggest_games"]:
                categorized_commands["Game Management"].append(command_info)
            elif command.name in ["setup_game_night", "set_game_night_availability", "set_weekly_availability"]:
                categorized_commands["Game Night Organization"].append(command_info)
            elif command.name in ["set_main_channel", "set_voice_notification_channel", "set_availability"]: # set_availability is configure_weekly_slots
                categorized_commands["Admin Commands"].append(command_info)
            else:
                # Fallback for any uncategorized commands
                categorized_commands["General & Profile"].append(command_info)


        # Add fields to the embed for each category
        for category, commands_list in categorized_commands.items():
            if commands_list:
                embed.add_field(name=category, value="\n".join(commands_list), inline=False)

        embed.set_footer(text="Find your Steam ID at steamid.io.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="set_weekly_availability", description="Set your recurring weekly availability for game nights.")
    @app_commands.describe(
        available_days=(
            "Comma-separated day names (e.g., 'Monday,Wed') "
            "or numbers (0=Mon, 6=Sun)."
        )
    )
    async def set_weekly_availability(self, interaction: discord.Interaction, available_days: str):
        """Set a user's recurring weekly availability."""
        await interaction.response.defer(ephemeral=True)
        day_mapping = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        processed_days = []
        input_days = [d.strip().lower() for d in available_days.split(',')]
        if "none" in input_days:
            final_availability_string, display_message = "", "none"
        else:
            for day in input_days:
                if day.isdigit() and 0 <= int(day) <= 6:
                    processed_days.append(day)
                elif day in day_mapping:
                    processed_days.append(str(day_mapping[day]))
                else:
                    error_msg = f"Invalid day '{day}'. Use day names or numbers (0-6)."
                    await interaction.followup.send(error_msg, ephemeral=True)
                    return
            final_availability_string = ",".join(sorted(list(set(processed_days))))
            display_message = available_days
        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        db_manager.set_user_weekly_availability(user_db_id, final_availability_string)
        await interaction.followup.send(
            f"Your weekly availability has been set to: **{display_message}**.", ephemeral=True
        )

    @app_commands.command(name="set_gamepass_status", description="Set your Game Pass status and sync your library.")
    @app_commands.describe(has_game_pass="True if you have Game Pass, False otherwise.")
    async def set_gamepass_status(self, interaction: discord.Interaction, has_game_pass: bool):
        """Set a user's Game Pass status and syncs their library."""
        await interaction.response.defer(ephemeral=True)

        # Ensure the user exists in the DB first
        db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))

        if not user_db:
             await interaction.followup.send("Could not find or create your user profile. Please try again.", ephemeral=True)
             return

        # 1. Update the user's status in the database
        db_manager.set_user_game_pass_status(user_db.id, has_game_pass)
        status_text = 'enabled' if has_game_pass else 'disabled'
        await interaction.followup.send(
            f"Your Game Pass status has been set to **{status_text}**. Syncing your library now, this may take a moment...", ephemeral=True
        )

        # 2. Call our new central function to do the heavy lifting
        try:
            await db_manager.sync_user_game_pass_library(user_db.id, has_game_pass)
            await interaction.edit_original_response(
                content=f"Your Game Pass status is **{status_text}** and your library has been updated!"
            )
        except Exception as e:
            logger.error(f"Error during manual Game Pass sync for user {interaction.user.id}: {e}", exc_info=True)
            await interaction.edit_original_response(
                content="Something went wrong during the library sync. Please try again later."
            )

    @app_commands.command(name="set_voice_notifications", description="Toggle voice activity notifications for yourself.")
    @app_commands.describe(enabled="True to enable, False to disable.")
    async def set_voice_notifications(self, interaction: discord.Interaction, enabled: bool):
        """Toggle whether the user receives voice activity notifications."""
        await interaction.response.defer(ephemeral=True)
        user_db = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        db_manager.set_user_voice_notifications(user_db.id, enabled)
        status = "enabled" if enabled else "disabled"
        await interaction.followup.send(f"Voice activity notifications have been {status} for you.", ephemeral=True)

    @app_commands.command(name="set_reminder_offset", description="Set your default game night reminder offset.")
    @app_commands.describe(
        offset_minutes="The time before a game night to send a reminder."
    )
    @app_commands.choices(offset_minutes=[
        app_commands.Choice(name="15 Minutes", value=15), app_commands.Choice(name="30 Minutes", value=30),
        app_commands.Choice(name="1 Hour", value=60), app_commands.Choice(name="2 Hours", value=120),
        app_commands.Choice(name="24 Hours", value=1440),
    ])
    async def set_reminder_offset(self, interaction: discord.Interaction, offset_minutes: app_commands.Choice[int]):
        """Set the user's preferred reminder offset for game nights."""
        await interaction.response.defer(ephemeral=True)
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You are not registered. Please add a game first.")
        db_manager.set_user_reminder_offset(user_db.id, offset_minutes.value)
        await interaction.followup.send(f"Your reminder offset is set to **{offset_minutes.name}**.", ephemeral=True)

    @app_commands.command(name="wrapped_discord", description="Shows your voice activity statistics for a year.")
    @app_commands.describe(year="The year for which to show statistics (defaults to current year).")
    async def discord_wrapped(self, interaction: discord.Interaction, year: int = None):
        """Show a user's voice activity stats for a given year."""
        await interaction.response.defer()
        target_year = year or datetime.now().year
        user_db = db_manager.get_user_by_discord_id(str(interaction.user.id))
        if not user_db:
            raise UserNotFoundError("You don't have any recorded activity yet.")
        start_date, end_date = datetime(target_year, 1, 1), datetime(target_year + 1, 1, 1)
        total_time_seconds = (VoiceActivity
                              .select(fn.SUM(VoiceActivity.duration_seconds))
                              .where(VoiceActivity.user == user_db,
                                     VoiceActivity.join_time >= start_date,
                                     VoiceActivity.join_time < end_date,
                                     VoiceActivity.duration_seconds.is_null(False))
                              .scalar() or 0)
        total_hours = round(total_time_seconds / 3600, 2)
        unique_days = (VoiceActivity
                       .select(fn.COUNT(fn.DISTINCT(fn.date(VoiceActivity.join_time))))
                       .where(VoiceActivity.user == user_db,
                              VoiceActivity.join_time >= start_date,
                              VoiceActivity.join_time < end_date)
                       .scalar() or 0)
        total_joins = (VoiceActivity.select()
                       .where(VoiceActivity.user == user_db,
                              VoiceActivity.join_time >= start_date,
                              VoiceActivity.join_time < end_date).count())
        game_nights_attended = db_manager.get_attended_game_nights_count(user_db.id, start_date, end_date)
        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Discord Wrapped {target_year}", color=discord.Color.purple()
        )
        embed.add_field(name="Total Time in Voice", value=f"{total_hours} hours", inline=False)
        embed.add_field(name="Days Joined Voice", value=f"{unique_days} days", inline=False)
        embed.add_field(name="Total Joins", value=f"{total_joins} times", inline=False)
        embed.add_field(name="Game Nights Attended", value=f"{game_nights_attended} nights", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="wrapped_history", description="Shows a user's past game night attendance.")
    @app_commands.describe(user="The user whose game night history you want to view. Defaults to yourself.")
    async def game_night_history(self, interaction: discord.Interaction, user: discord.Member = None):
        """Show a user's game night attendance history."""
        await interaction.response.defer()
        target_user = user or interaction.user
        user_db = db_manager.get_user_by_discord_id(str(target_user.id))
        if not user_db:
            raise UserNotFoundError(f"{target_user.display_name} has no recorded game night history.")
        game_nights = db_manager.get_user_game_night_history(user_db.id)
        embed = discord.Embed(title=f"{target_user.display_name}'s Game Night History", color=discord.Color.green())
        if not game_nights:
            embed.description = "No game nights attended yet."
        else:
            lines = [
                f"**{gn.scheduled_time:%Y-%m-%d %I:%M %p}**: "
                f"{gn.selected_game.title if gn.selected_game else '(Game not selected)'}"
                for gn in game_nights
            ]
            embed.description = "\n".join(lines[:10])
            if len(lines) > 10:
                embed.set_footer(text=f"Showing 10 of {len(lines)} attended game nights.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="set_voice_notification_channel", description="Sets the channel for voice activity notifications.")
    @app_commands.describe(channel="The channel to send voice activity notifications to.")
    @app_commands.default_permissions(manage_guild=True)
    async def set_voice_notification_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the guild's voice activity notification channel."""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return
        db_manager.set_guild_voice_notification_channel(str(interaction.guild.id), str(channel.id))
        await interaction.followup.send(f"Voice activity notifications will now be sent to {channel.mention}.")

    @app_commands.command(name="set_main_channel", description="Sets the main channel for polls and announcements.")
    @app_commands.describe(channel="The channel to set as the main channel.")
    @app_commands.default_permissions(manage_guild=True)
    async def set_main_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the guild's main channel for announcements."""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
            return
        db_manager.set_guild_main_channel(str(interaction.guild.id), str(channel.id))
        await interaction.followup.send(f"Main channel has been set to {channel.mention}.")


async def setup(bot):
    """Load the UtilityCommands cog."""
    await bot.add_cog(UtilityCommands(bot))
