"""
Configuration loader for loading and validating config.json.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .models import AppConfig


logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""
    pass


def _create_default_config(config: AppConfig, config_path: Path) -> None:
    """
    Create a default config.json file with helpful documentation.

    Args:
        config: Default AppConfig to save.
        config_path: Path where to create the config file.
    """
    try:
        config_dict = config.model_dump()

        # Add a comment at the top
        save_data = {
            "_comment": "Robofocus Alpaca Driver Configuration (auto-generated). See config.example.json for all options.",
            **config_dict
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2)

        logger.info(f"Created default config file: {config_path}")

    except IOError as e:
        logger.warning(f"Failed to create default config file: {e}")


def load_config(path: Optional[str] = None) -> AppConfig:
    """
    Load configuration from JSON file.

    Args:
        path: Path to config.json file. If None, looks for config.json in current directory.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigurationError: If config file is missing or invalid.
    """
    # Default to config.json in current directory
    if path is None:
        path = "config.json"

    config_path = Path(path)

    # If file doesn't exist, create with defaults
    if not config_path.exists():
        logger.info(
            f"Config file not found: {config_path}. Creating with default configuration."
        )
        config = AppConfig()
        _create_default_config(config, config_path)
        return config

    # Read JSON file
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigurationError(
            f"Invalid JSON in {config_path}: {e}"
        ) from e
    except IOError as e:
        raise ConfigurationError(
            f"Failed to read {config_path}: {e}"
        ) from e

    # Validate with Pydantic
    try:
        config = AppConfig(**config_dict)
    except ValidationError as e:
        # Format validation errors nicely
        errors = []
        for error in e.errors():
            field = " -> ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"  - {field}: {msg}")

        error_message = "Configuration validation failed:\n" + "\n".join(errors)
        raise ConfigurationError(error_message) from e

    logger.info(f"Configuration loaded from {config_path}")
    return config


def save_config(config: AppConfig, path: Optional[str] = None) -> None:
    """
    Save configuration to JSON file.

    Args:
        config: AppConfig instance to save.
        path: Path to config.json file. If None, uses "config.json" in current directory.

    Raises:
        ConfigurationError: If config file cannot be written.
    """
    if path is None:
        path = "config.json"

    config_path = Path(path)

    try:
        # Convert to dict with all values
        config_dict = config.model_dump()

        # Write to file with pretty formatting
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)

        logger.info(f"Configuration saved to {config_path}")

    except IOError as e:
        raise ConfigurationError(f"Failed to write {config_path}: {e}") from e


def create_example_config(path: str = "config.example.json") -> None:
    """
    Create an example configuration file with all default values and documentation.

    Args:
        path: Path where to create the example config file.
    """
    # Create config with defaults
    config = AppConfig()

    # Convert to dict and add comments (as keys with '#' prefix for documentation)
    config_dict = config.model_dump()

    # Write to file with pretty formatting
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=2)

    logger.info(f"Example configuration created: {path}")


if __name__ == "__main__":
    # Generate example config when run as script
    create_example_config()
    print("Created config.example.json with default values")
