from __future__ import annotations


class ScoutError(Exception):
    """Base class for all scout-raised exceptions."""


class ConfigError(ScoutError):
    """Bad CLI flag or invalid config file content."""


class ScoutIOError(ScoutError):
    """Cannot read or write files required for the run."""


class DiscoveryError(ScoutError):
    """Cannot resolve or walk the project root."""


# Exit code constants (§12.2)
EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_CONFIG_ERROR = 2
EXIT_IO_ERROR = 3
EXIT_PARSE_ERROR = 4
EXIT_INTERRUPT = 130
