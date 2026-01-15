"""
User settings persistence for software preferences.

These settings are stored locally and persist between sessions.
Unlike hardware settings (max_travel, backlash) which are stored
in the Robofocus device, these are purely software-side preferences.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .models import UserSettings


logger = logging.getLogger(__name__)

# Default settings file location (next to config.json)
DEFAULT_SETTINGS_FILE = "user_settings.json"


class UserSettingsManager:
    """
    Manages loading and saving of user settings.

    Settings are automatically saved when modified.
    """

    def __init__(self, path: Optional[str] = None):
        """
        Initialize settings manager.

        Args:
            path: Path to settings file. If None, uses default location.
        """
        self._path = Path(path or DEFAULT_SETTINGS_FILE)
        self._settings = self._load()

    def _load(self) -> UserSettings:
        """Load settings from file, or create defaults if not found."""
        if not self._path.exists():
            logger.info(f"User settings file not found: {self._path}. Creating with defaults.")
            settings = UserSettings()
            self._create_default_file(settings)
            return settings

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Migration: convert old use_simulator=false to None
            # Old default was False, now we use None to mean "use config.json"
            # If use_simulator is False, treat it as "never explicitly set"
            if data.get("use_simulator") is False:
                logger.info("Migrating old user_settings: use_simulator=false -> None")
                data["use_simulator"] = None

            settings = UserSettings(**data)
            logger.info(f"User settings loaded from {self._path}")
            return settings

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in {self._path}: {e}. Using defaults.")
            return UserSettings()
        except ValidationError as e:
            logger.warning(f"Invalid settings in {self._path}: {e}. Using defaults.")
            return UserSettings()
        except IOError as e:
            logger.warning(f"Failed to read {self._path}: {e}. Using defaults.")
            return UserSettings()

    def _create_default_file(self, settings: UserSettings) -> None:
        """
        Create a new settings file with defaults and helpful comments.

        Since JSON doesn't support comments, we create a clean JSON file
        and the field descriptions are in the model itself.
        """
        try:
            data = {
                "_comment": "Robofocus Alpaca Driver - User Settings (auto-generated)",
                "last_port": settings.last_port,
                "max_increment": settings.max_increment,
                "min_step": settings.min_step,
                # Note: use_simulator is intentionally omitted when None
                # to let config.json be the source of truth
            }

            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Created default user settings file: {self._path}")

        except IOError as e:
            logger.warning(f"Failed to create default settings file: {e}")

    def save(self) -> bool:
        """
        Save current settings to file.

        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            data = self._settings.model_dump()

            # Don't save use_simulator if None (let config.json be the source of truth)
            if data.get("use_simulator") is None:
                del data["use_simulator"]

            # Add helpful comment for users
            save_data = {
                "_comment": "Robofocus Alpaca Driver - User Settings",
                **data
            }

            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2)

            logger.debug(f"User settings saved to {self._path}")
            return True

        except IOError as e:
            logger.error(f"Failed to save settings to {self._path}: {e}")
            return False

    @property
    def settings(self) -> UserSettings:
        """Get current settings (read-only access)."""
        return self._settings

    @property
    def last_port(self) -> Optional[str]:
        """Get last used COM port."""
        return self._settings.last_port

    @last_port.setter
    def last_port(self, value: Optional[str]) -> None:
        """Set last used COM port and save."""
        if self._settings.last_port != value:
            self._settings.last_port = value
            self.save()
            logger.info(f"Saved last_port: {value}")

    @property
    def max_increment(self) -> int:
        """Get max increment limit."""
        return self._settings.max_increment

    @max_increment.setter
    def max_increment(self, value: int) -> None:
        """Set max increment limit and save."""
        if value < 1 or value > 65535:
            raise ValueError(f"max_increment must be 1-65535, got {value}")
        if self._settings.max_increment != value:
            self._settings.max_increment = value
            self.save()
            logger.info(f"Saved max_increment: {value}")

    @property
    def min_step(self) -> int:
        """Get minimum step limit."""
        return self._settings.min_step

    @min_step.setter
    def min_step(self, value: int) -> None:
        """Set minimum step limit and save."""
        if value < 0 or value > 65535:
            raise ValueError(f"min_step must be 0-65535, got {value}")
        if self._settings.min_step != value:
            self._settings.min_step = value
            self.save()
            logger.info(f"Saved min_step: {value}")

    @property
    def use_simulator(self) -> Optional[bool]:
        """Get simulator mode preference. None means use config.json."""
        return self._settings.use_simulator

    @use_simulator.setter
    def use_simulator(self, value: bool) -> None:
        """Set simulator mode preference and save."""
        if self._settings.use_simulator != value:
            self._settings.use_simulator = value
            self.save()
            mode = "simulator" if value else "hardware"
            logger.info(f"Saved use_simulator: {value} (mode: {mode})")


# Global instance (initialized by app startup)
_manager: Optional[UserSettingsManager] = None


def init_user_settings(path: Optional[str] = None) -> UserSettingsManager:
    """
    Initialize the global user settings manager.

    Args:
        path: Path to settings file. If None, uses default location.

    Returns:
        Initialized UserSettingsManager instance.
    """
    global _manager
    _manager = UserSettingsManager(path)
    return _manager


def get_user_settings() -> UserSettingsManager:
    """
    Get the global user settings manager.

    Returns:
        UserSettingsManager instance.

    Raises:
        RuntimeError: If settings not initialized.
    """
    if _manager is None:
        raise RuntimeError("User settings not initialized. Call init_user_settings() first.")
    return _manager
