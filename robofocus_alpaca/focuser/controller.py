"""
Focuser controller (Layer 2 - State Machine).

Manages focuser state and coordinates between API and protocol layers.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from robofocus_alpaca.protocol.interface import SerialProtocolInterface
from robofocus_alpaca.config.models import FocuserConfig, AppConfig
from robofocus_alpaca.config.loader import save_config
from robofocus_alpaca.utils.exceptions import NotConnectedError, InvalidValueError


logger = logging.getLogger(__name__)


class FocuserController:
    """
    Focuser controller managing state and movement.
    """

    def __init__(
        self,
        protocol: SerialProtocolInterface,
        config: FocuserConfig,
        app_config: Optional[AppConfig] = None,
        config_path: Optional[str] = None
    ):
        """
        Initialize focuser controller.

        Args:
            protocol: Serial protocol implementation (real or simulator).
            config: Focuser configuration.
            app_config: Full application config (for saving). Optional.
            config_path: Path to config.json for saving. Optional.
        """
        self.protocol = protocol
        self.config = config
        self._app_config = app_config
        self._config_path = config_path

        # State
        self._connected = False
        self._position_cache = 0
        self._last_position_update: Optional[datetime] = None
        self._backlash_cache = 0  # Cached backlash value (signed INDI convention)

        # Movement tracking
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_polling = threading.Event()

        logger.info("FocuserController initialized")

    def set_protocol(self, protocol: SerialProtocolInterface) -> None:
        """
        Replace the protocol implementation (e.g., switch between hardware and simulator).

        This can only be done when disconnected.

        Args:
            protocol: New protocol implementation.

        Raises:
            RuntimeError: If focuser is currently connected.
        """
        if self._connected:
            raise RuntimeError("Cannot change protocol while connected. Disconnect first.")

        self.protocol = protocol
        logger.info(f"Protocol changed to {type(protocol).__name__}")

    def _save_config(self) -> None:
        """Save configuration to file if app_config is available."""
        if self._app_config and self._config_path:
            try:
                save_config(self._app_config, self._config_path)
            except Exception as e:
                logger.warning(f"Failed to save config: {e}")

    def save_config(self) -> None:
        """Public method to save configuration."""
        self._save_config()

    @property
    def connected(self) -> bool:
        """Check if focuser is connected."""
        return self._connected and self.protocol.is_connected()

    def connect(self) -> None:
        """
        Connect to focuser hardware.

        Queries hardware settings (max travel, backlash) and updates config.

        Raises:
            DriverError: If connection fails.
        """
        if self._connected:
            logger.warning("Already connected")
            return

        self.protocol.connect()
        self._connected = True

        # Read initial position
        self._position_cache = self.protocol.get_position()
        self._last_position_update = datetime.now()

        # Query hardware settings
        self._query_hardware_settings()

        logger.info(f"Focuser connected at position {self._position_cache}")

    def _query_hardware_settings(self) -> None:
        """Query and log hardware settings after connection, and save to config."""
        config_changed = False

        # Save firmware version
        if hasattr(self.protocol, 'firmware_version') and self.protocol.firmware_version:
            if self.config.firmware_version != self.protocol.firmware_version:
                self.config.firmware_version = self.protocol.firmware_version
                config_changed = True
                logger.info(f"Saved firmware version to config: {self.protocol.firmware_version}")

        # Save serial port
        if self._app_config and hasattr(self.protocol, 'port_name'):
            port_name = self.protocol.port_name
            if self._app_config.serial.port != port_name:
                self._app_config.serial.port = port_name
                config_changed = True
                logger.info(f"Saved serial port to config: {port_name}")

        try:
            # Read max travel from hardware
            hw_max_travel = self.protocol.get_max_travel()
            if hw_max_travel > 0:
                # Update config with hardware value if valid
                if hw_max_travel != self.config.max_step:
                    logger.info(f"Hardware max travel: {hw_max_travel} (config was {self.config.max_step})")
                    self.config.max_step = hw_max_travel
                    config_changed = True
                else:
                    logger.debug(f"Hardware max travel: {hw_max_travel}")
        except Exception as e:
            logger.warning(f"Could not read max travel from hardware: {e}")

        try:
            # Read backlash settings from hardware
            direction, amount = self.protocol.get_backlash()
            direction_str = "IN" if direction == 2 else "OUT"
            # Cache the value (convert to signed INDI convention)
            self._backlash_cache = -amount if direction == 2 else amount
            # Save to config
            if self.config.backlash_steps != self._backlash_cache:
                self.config.backlash_steps = self._backlash_cache
                config_changed = True
            logger.info(f"Hardware backlash: {amount} steps on {direction_str} motion")
        except Exception as e:
            logger.warning(f"Could not read backlash from hardware: {e}")

        # Save config if anything changed
        if config_changed:
            self._save_config()

    def disconnect(self) -> None:
        """Disconnect from focuser hardware."""
        if not self._connected:
            return

        # Stop polling thread
        if self._polling_thread:
            self._stop_polling.set()
            self._polling_thread.join(timeout=5.0)

        self.protocol.disconnect()
        self._connected = False

        logger.info("Focuser disconnected")

    def get_position(self) -> int:
        """
        Get current position.

        Returns cached position if moving, queries hardware if idle.

        Returns:
            Position in steps.

        Raises:
            NotConnectedError: If not connected.
        """
        if not self.connected:
            raise NotConnectedError("Focuser not connected")

        if self.protocol.is_moving():
            # Return cached position during movement
            return self._position_cache
        else:
            # Query hardware when idle
            self._position_cache = self.protocol.get_position()
            self._last_position_update = datetime.now()
            return self._position_cache

    @property
    def is_moving(self) -> bool:
        """
        Check if focuser is moving.

        Returns:
            True if moving, False if idle.
        """
        if not self.connected:
            return False
        return self.protocol.is_moving()

    def move(self, target: int) -> None:
        """
        Move to absolute position (non-blocking).

        Args:
            target: Target position in steps.

        Raises:
            NotConnectedError: If not connected.
            InvalidValueError: If target out of range.
        """
        if not self.connected:
            raise NotConnectedError("Focuser not connected")

        # Validate range
        if target < self.config.min_step or target > self.config.max_step:
            raise InvalidValueError(
                f"Position {target} out of range [{self.config.min_step}, {self.config.max_step}]"
            )

        # Clamp to limits (safety)
        target = max(self.config.min_step, min(target, self.config.max_step))

        # Start movement
        self.protocol.move_absolute(target)

        # Start polling thread if not already running
        if not self._polling_thread or not self._polling_thread.is_alive():
            self._stop_polling.clear()
            self._polling_thread = threading.Thread(
                target=self._poll_movement,
                daemon=True
            )
            self._polling_thread.start()

        logger.info(f"Movement started: {self._position_cache} -> {target}")

    def halt(self) -> None:
        """
        Stop movement immediately.

        Raises:
            NotConnectedError: If not connected.
        """
        if not self.connected:
            raise NotConnectedError("Focuser not connected")

        self.protocol.halt()

        # Update position cache
        time.sleep(0.5)  # Wait for movement to stop
        self._position_cache = self.protocol.get_position()
        self._last_position_update = datetime.now()

        logger.info(f"Movement halted at position {self._position_cache}")

    def get_temperature(self) -> float:
        """
        Read temperature sensor.

        Returns:
            Temperature in degrees Celsius.

        Raises:
            NotConnectedError: If not connected.
            SensorError: If sensor not available.
        """
        if not self.connected:
            raise NotConnectedError("Focuser not connected")

        return self.protocol.get_temperature()

    def _poll_movement(self) -> None:
        """
        Background thread to poll movement status and update position cache.
        """
        logger.debug("Movement polling thread started")

        interval_ms = self.config.polling_interval_moving_ms
        last_position = self._position_cache
        stall_count = 0
        max_stall_count = 5  # ~500ms at 100ms polling

        try:
            while not self._stop_polling.is_set():
                try:
                    # Read asynchronous characters
                    chars = self.protocol.read_async_chars()

                    for char in chars:
                        if char == 'I':
                            # Inward movement
                            self._position_cache -= 1
                            stall_count = 0
                        elif char == 'O':
                            # Outward movement
                            self._position_cache += 1
                            stall_count = 0
                        elif char == 'F':
                            # Finished - force clear moving flag
                            if hasattr(self.protocol, '_is_moving_flag'):
                                self.protocol._is_moving_flag = False
                            logger.info(f"Movement finished signal received")

                    # Check if still moving
                    if not self.protocol.is_moving():
                        logger.debug("Movement polling thread stopping (idle)")
                        break

                    # Stall detection: if no movement chars received for a while,
                    # assume movement finished (in case we missed the 'F' char)
                    if self._position_cache == last_position:
                        stall_count += 1
                        if stall_count >= max_stall_count:
                            logger.warning("Movement stall detected, forcing idle state")
                            if hasattr(self.protocol, '_is_moving_flag'):
                                self.protocol._is_moving_flag = False
                            break
                    else:
                        last_position = self._position_cache
                        stall_count = 0

                    # Sleep
                    time.sleep(interval_ms / 1000.0)

                except Exception as e:
                    logger.error(f"Error in polling thread: {e}")
                    break
        finally:
            # Always update final position when thread exits
            try:
                # Give hardware a moment to settle after movement before querying position
                # Without this delay, the FG command may timeout if sent too soon after 'F' char
                # Keep moving flag True during this settling time so external get_position()
                # calls will return cached value instead of querying hardware
                time.sleep(0.15)  # 150ms settling time

                # NOW clear moving flag and query final position
                if hasattr(self.protocol, '_is_moving_flag'):
                    self.protocol._is_moving_flag = False

                self._position_cache = self.protocol.get_position()
                self._last_position_update = datetime.now()
                logger.debug(f"Polling thread exit, final position: {self._position_cache}")
            except Exception as e:
                logger.error(f"Error getting final position: {e}")

        logger.debug("Movement polling thread stopped")

    def get_backlash(self) -> int:
        """
        Get current backlash compensation value.

        Returns signed value following INDI convention:
        - Positive value = OUT motion compensation
        - Negative value = IN motion compensation
        - Zero = no compensation

        Returns cached value during movement to avoid serial communication issues.

        Returns:
            Backlash amount (-255 to +255).

        Raises:
            NotConnectedError: If not connected.
        """
        if not self.connected:
            raise NotConnectedError("Focuser not connected")

        # Return cached value during movement to avoid "Unexpected response to FB: FD" errors
        # The hardware cannot respond to FB commands while sending async movement chars (I/O/F)
        if self.protocol.is_moving():
            logger.debug(f"Backlash query during movement, returning cached value: {self._backlash_cache}")
            return self._backlash_cache

        # Query hardware when idle and update cache
        direction, amount = self.protocol.get_backlash()

        # Convert to signed value (INDI convention)
        # direction 2 = IN = negative, direction 3 = OUT = positive
        self._backlash_cache = -amount if direction == 2 else amount

        return self._backlash_cache

    def set_backlash(self, value: int) -> None:
        """
        Set backlash compensation.

        Uses signed value following INDI convention:
        - Positive value = compensation added to OUT motion
        - Negative value = compensation added to IN motion
        - Zero = disables compensation

        Args:
            value: Backlash amount (-255 to +255).

        Raises:
            NotConnectedError: If not connected.
            InvalidValueError: If value out of range.
        """
        if not self.connected:
            raise NotConnectedError("Focuser not connected")

        if value < -255 or value > 255:
            raise InvalidValueError(f"Backlash must be -255 to +255, got {value}")

        # Convert signed value to direction + amount
        if value >= 0:
            direction = 3  # OUT motion
            amount = value
        else:
            direction = 2  # IN motion
            amount = -value

        self.protocol.set_backlash(direction, amount)

        # Update cache
        self._backlash_cache = value

        # Update config and save
        if self.config.backlash_steps != value:
            self.config.backlash_steps = value
            self._save_config()

        logger.info(f"Backlash set to {value} ({'OUT' if value >= 0 else 'IN'} motion, {amount} steps)")
