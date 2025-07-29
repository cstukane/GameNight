import re
import discord

from data import db_manager


class AvailabilityPollView(discord.ui.View):
    """A persistent view for handling game night availability polls."""

    def __init__(self, game_night_id: int = None):
        """Initialize the AvailabilityPollView."""
        super().__init__(timeout=None)  # Polls should persist
        self.game_night_id = game_night_id

    async def _get_game_night_id_from_interaction(self, interaction: discord.Interaction) -> int | None:
        """Extracts the game_night_id from the message embed."""
        if self.game_night_id:
            return self.game_night_id
        
        try:
            embed = interaction.message.embeds[0]
            title = embed.title
            match = re.search(r"\(ID: (\d+)\)", title)
            if match:
                return int(match.group(1))
        except (IndexError, AttributeError, TypeError, ValueError):
            return None
        return None

    async def _handle_availability(self, interaction: discord.Interaction, status: str):
        """Generic handler for availability button clicks."""
        game_night_id = await self._get_game_night_id_from_interaction(interaction)
        if not game_night_id:
            await interaction.response.send_message("Error: Could not identify the game night for this poll.", ephemeral=True)
            return

        user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
        if user_db_id:
            db_manager.set_attendee_status(game_night_id, user_db_id, status)
            await interaction.response.send_message(f"You've marked yourself as **{status.title()}**!", ephemeral=True)
        else:
            await interaction.response.send_message("Error: Could not register your availability.", ephemeral=True)

    @discord.ui.button(label="Attending", style=discord.ButtonStyle.success, custom_id="availability_attending")
    async def attending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the 'Attending' button click, updating the user's status."""
        await self._handle_availability(interaction, "attending")

    @discord.ui.button(label="Maybe", style=discord.ButtonStyle.primary, custom_id="availability_maybe")
    async def maybe_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the 'Maybe' button click, updating the user's status."""
        await self._handle_availability(interaction, "maybe")

    @discord.ui.button(label="Not Attending", style=discord.ButtonStyle.danger, custom_id="availability_not_attending")
    async def not_attending_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the 'Not Attending' button click, updating the user's status."""
        await self._handle_availability(interaction, "not_attending")


async def create_availability_poll(channel: discord.TextChannel, game_night_id: int, scheduled_time: str):
    """Create a Discord poll for users to mark their availability for a game night."""
    embed = discord.Embed(
        title=f"Game Night Availability Poll (ID: {game_night_id})",
        description=(
            f"Game night is scheduled for **{scheduled_time}**.\n\n"
            "Click a button below to indicate your availability:"
        ),
        color=discord.Color.blue()
    )

    view = AvailabilityPollView(game_night_id)
    message = await channel.send(embed=embed, view=view)
    return message


class GameSelectionView(discord.ui.View):
    """A persistent view for handling game selection polls."""

    def __init__(self, game_night_id: int, games: list):
        """Initialize the GameSelectionView."""
        super().__init__(timeout=None)
        self.game_night_id = game_night_id
        self.games = games

        for i, game_name in enumerate(self.games):
            if i >= 25:  # Discord limit for components per message
                break
            self.add_item(discord.ui.Button(label=game_name, custom_id=f"game_vote_{game_night_id}_{game_name}"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only human users can interact with the view."""
        return not interaction.user.bot

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        """Handle errors that occur within the view."""
        await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

    @discord.ui.button(label="Close Poll", style=discord.ButtonStyle.danger, custom_id="close_game_poll_button")
    async def close_poll_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Inform the user how to properly close the poll."""
        await interaction.response.send_message(
            "Please use the `/close_game_poll` command to finalize the game selection.", ephemeral=True
        )

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle clicks on the dynamic game vote buttons."""
        custom_id = interaction.data["custom_id"]
        if custom_id.startswith("game_vote_"):
            parts = custom_id.split("_")
            game_night_id = int(parts[2])
            game_name = "_".join(parts[3:])  # Rejoin if game name has underscores

            user_db_id = db_manager.add_user(str(interaction.user.id), interaction.user.display_name)
            game = db_manager.get_game_by_name(game_name)

            if user_db_id and game:
                db_manager.add_game_vote(game_night_id, user_db_id, game.id)
                await interaction.response.send_message(f"You voted for {game_name}!", ephemeral=True)
            else:
                await interaction.response.send_message("Error recording your vote.", ephemeral=True)


async def create_game_selection_poll(channel: discord.TextChannel, game_night_id: int, suggested_games: list):
    """Create a Discord poll for users to vote on suggested games."""
    if not suggested_games:
        await channel.send(f"No games to suggest for Game Night ID {game_night_id}.")
        return None

    embed = discord.Embed(
        title=f"Game Selection Poll for Game Night (ID: {game_night_id})",
        description="Vote for the game you'd like to play!\n\nClick the button for your chosen game:",
        color=discord.Color.green()
    )

    view = GameSelectionView(game_night_id, suggested_games)
    message = await channel.send(embed=embed, view=view)
    return message


async def get_poll_results(message: discord.Message):
    """Retrieve the results of a button-based poll message (deprecated)."""
    # This function is now deprecated as availability is tracked in the database
    # and game votes are tracked in the database.
    return {}


async def get_game_poll_winner(game_night_id: int):
    """Determine the winner of a game selection poll based on database votes."""
    votes = db_manager.get_game_votes(game_night_id)
    if not votes:
        return None

    vote_counts = {}
    for vote in votes:
            game_details = await db_manager.get_game_details(vote.game_id)
            if game_details:
                vote_counts[game_details] = vote_counts.get(game_details, 0) + 1

    if not vote_counts:
        return None

    winner = max(vote_counts, key=vote_counts.get)
    return winner
