"""LogLens: one command to answer what broke, how often, and when it spiked."""

from .parser import LogEntry, parse_lines

__all__ = ["LogEntry", "parse_lines"]
__version__ = "1.0.0"
