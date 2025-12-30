#!/usr/bin/env python3
"""
Logging Utilities

Consistent logging setup and progress tracking utilities.
Extracted from utils.py and standardized across modules.
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


# Color codes for terminal output
class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Background colors
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for different log levels"""

    COLORS = {
        'DEBUG': Colors.DIM + Colors.CYAN,
        'INFO': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'CRITICAL': Colors.BG_RED + Colors.WHITE + Colors.BOLD
    }

    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Colors.RESET}"

        return super().format(record)


def setup_logging(
    level: int = logging.INFO,
    log_format: Optional[str] = None,
    log_file: Optional[Path] = None,
    use_colors: bool = True,
    include_timestamp: bool = True
) -> None:
    """
    Setup logging configuration with consistent formatting.

    Args:
        level: Logging level (default: INFO)
        log_format: Custom format string (optional)
        log_file: Optional file path for logging
        use_colors: Use colored output for console (default: True)
        include_timestamp: Include timestamp in logs (default: True)
    """
    # Default format
    if log_format is None:
        if include_timestamp:
            log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        else:
            log_format = '%(name)s - %(levelname)s - %(message)s'

    # Setup handlers
    handlers = []

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    if use_colors and sys.stdout.isatty():
        console_handler.setFormatter(ColoredFormatter(log_format))
    else:
        console_handler.setFormatter(logging.Formatter(log_format))
    handlers.append(console_handler)

    # File handler (no colors)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True  # Override any existing configuration
    )


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Get a logger with consistent configuration.

    Args:
        name: Logger name (typically __name__)
        level: Optional logging level override

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger


class ProgressLogger:
    """
    Progress logger for long-running operations.

    Usage:
        progress = ProgressLogger("Processing files", total=100)
        for i in range(100):
            progress.update(i + 1, f"Processing file {i}")
        progress.complete()
    """

    def __init__(
        self,
        task_name: str,
        total: int,
        logger: Optional[logging.Logger] = None,
        log_interval: int = 10
    ):
        """
        Initialize progress logger.

        Args:
            task_name: Name of task being tracked
            total: Total number of items to process
            logger: Logger instance (creates new if None)
            log_interval: Log progress every N items
        """
        self.task_name = task_name
        self.total = total
        self.logger = logger or logging.getLogger(__name__)
        self.log_interval = log_interval
        self.current = 0
        self.start_time = datetime.now()

    def update(self, current: int, message: Optional[str] = None) -> None:
        """
        Update progress.

        Args:
            current: Current progress count
            message: Optional status message
        """
        self.current = current

        # Log at intervals or significant milestones
        if (current % self.log_interval == 0 or
            current == self.total or
            current == 1):

            percent = (current / self.total * 100) if self.total > 0 else 0
            elapsed = (datetime.now() - self.start_time).total_seconds()

            # Estimate remaining time
            if current > 0:
                rate = current / elapsed
                remaining = (self.total - current) / rate if rate > 0 else 0
                eta_str = f", ETA: {remaining:.0f}s"
            else:
                eta_str = ""

            msg = f"{self.task_name}: {current}/{self.total} ({percent:.0f}%{eta_str})"
            if message:
                msg += f" - {message}"

            self.logger.info(msg)

    def increment(self, message: Optional[str] = None) -> None:
        """Increment progress by 1."""
        self.update(self.current + 1, message)

    def complete(self, message: Optional[str] = None) -> None:
        """Mark task as complete and log summary."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.total / elapsed if elapsed > 0 else 0

        msg = f"{self.task_name}: Complete ({self.total} items in {elapsed:.1f}s, {rate:.1f} items/s)"
        if message:
            msg += f" - {message}"

        self.logger.info(msg)


class LogSection:
    """
    Context manager for logging sections with clear boundaries.

    Usage:
        with LogSection("Database Migration"):
            # ... do migration work ...
            # Logs will be clearly marked
    """

    def __init__(
        self,
        section_name: str,
        logger: Optional[logging.Logger] = None,
        level: int = logging.INFO,
        separator: str = "="
    ):
        """
        Initialize log section.

        Args:
            section_name: Name of section
            logger: Logger instance (creates new if None)
            level: Logging level for section markers
            separator: Character for section separators
        """
        self.section_name = section_name
        self.logger = logger or logging.getLogger(__name__)
        self.level = level
        self.separator = separator
        self.start_time = None

    def __enter__(self):
        """Start section logging."""
        self.start_time = datetime.now()
        separator_line = self.separator * 60

        self.logger.log(self.level, separator_line)
        self.logger.log(self.level, f"{self.section_name}")
        self.logger.log(self.level, separator_line)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End section logging with duration."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        if exc_type is not None:
            self.logger.error(
                f"{self.section_name} FAILED after {elapsed:.1f}s: {exc_val}"
            )
        else:
            self.logger.log(
                self.level,
                f"{self.section_name} completed in {elapsed:.1f}s"
            )

        self.logger.log(self.level, self.separator * 60)

        return False  # Don't suppress exceptions


def log_exception(logger: logging.Logger, exc: Exception, context: str = "") -> None:
    """
    Log exception with full traceback and context.

    Args:
        logger: Logger instance
        exc: Exception to log
        context: Optional context description
    """
    import traceback

    msg = f"Exception occurred"
    if context:
        msg += f" during {context}"
    msg += f": {type(exc).__name__}: {exc}"

    logger.error(msg)
    logger.debug("Traceback:\n" + "".join(traceback.format_tb(exc.__traceback__)))


def configure_third_party_loggers(level: int = logging.WARNING) -> None:
    """
    Configure noisy third-party loggers to reduce spam.

    Args:
        level: Level for third-party loggers (default: WARNING)
    """
    noisy_loggers = [
        'urllib3',
        'requests',
        'git',
        'matplotlib',
        'PIL',
        'anthropic',
        'httpx',
        'httpcore'
    ]

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(level)
