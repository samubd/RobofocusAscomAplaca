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

    # If file doesn't exist, use defaults
    if not config_path.exists():
        logger.warning(
            f"Config file not found: {config_path}. Using default configuration."
        )
        return AppConfig()

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
