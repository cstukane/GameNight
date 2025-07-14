class GameNightError(Exception):
    """Base exception class for Game Night Bot errors."""

    pass

class GameNotFoundError(GameNightError):
    """Raised when a game is not found in the database."""

    pass

class UserNotFoundError(GameNightError):
    """Raised when a user is not found in the database."""

    pass

class PollNotFoundError(GameNightError):
    """Raised when a poll is not found."""

    pass

class InvalidGameNightIDError(GameNightError):
    """Raised when a game night ID is invalid."""

    pass
