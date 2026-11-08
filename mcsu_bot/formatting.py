"""Small shared formatting helpers used by both the bot and the GUI."""


def format_signed(value) -> str:
    """Format an ELO/reward delta with an explicit sign: +60, 0, -15."""
    number = int(value or 0)
    return f"+{number}" if number > 0 else str(number)
