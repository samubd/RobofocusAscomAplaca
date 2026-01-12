"""
Logging setup with console and file handlers.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from robofocus_alpaca.config.models import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """
    Configure logging for the application.

    Args:
        config: Logging configuration.
    """
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(config.level)

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if config.file:
        try:
            file_handler = RotatingFileHandler(
                config.file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(config.level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info(f"Logging to file: {config.file}")
        except IOError as e:
            logger.error(f"Failed to create log file {config.file}: {e}")

    logger.info(f"Logging initialized at level: {config.level}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Module name (usually __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)
