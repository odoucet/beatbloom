"""User-facing errors that the CLI can report without a traceback."""


class BeatBloomError(Exception):
    """Invalid configuration, unavailable media or failed processing."""
