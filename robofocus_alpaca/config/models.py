"""
Configuration models using Pydantic for validation.

All configuration is loaded from config.json and validated at startup.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ServerConfig(BaseModel):
    """HTTP server configuration."""

    ip: str = Field(default="0.0.0.0", description="IP address to bind to")
    port: int = Field(default=5000, ge=1, le=65535, description="HTTP port")
    discovery_enabled: bool = Field(
        default=True, description="Enable UDP discovery protocol"
    )


class SerialConfig(BaseModel):
    """Serial port configuration."""

    port: str = Field(default="", description="Serial port name (e.g., COM12). Empty for auto-discover.")
    baud: int = Field(default=9600, description="Baud rate")
    timeout_seconds: int = Field(
        default=5, ge=1, le=30, description="Read timeout in seconds"
    )
    auto_discover: bool = Field(
        default=True, description="Automatically scan for Robofocus device"
    )
    scan_timeout_seconds: float = Field(
        default=1.0, ge=0.5, le=10.0, description="Timeout per port during auto-discovery scan"
    )


class FocuserConfig(BaseModel):
    """Focuser hardware configuration."""

    step_size_microns: float = Field(
        default=4.5, gt=0, description="Step size in microns"
    )
    max_step: int = Field(
        default=60000, ge=0, description="Maximum position limit"
    )
    max_increment: int = Field(
        default=60000, ge=1, description="Maximum steps per single move"
    )
    min_step: int = Field(
        default=0, ge=0, description="Minimum position limit"
    )
    polling_interval_moving_ms: int = Field(
        default=100, ge=10, le=1000, description="Polling interval during movement (ms)"
    )
    polling_interval_idle_sec: int = Field(
        default=5, ge=1, le=60, description="Polling interval when idle (seconds)"
    )
    firmware_version: Optional[str] = Field(
        default=None, description="Firmware version (read from hardware)"
    )
    backlash_steps: int = Field(
        default=0, ge=-255, le=255, description="Backlash compensation (signed INDI convention)"
    )

    @field_validator("max_step")
    @classmethod
    def validate_max_greater_than_min(cls, v, info):
        """Ensure max_step > min_step."""
        if "min_step" in info.data and v <= info.data["min_step"]:
            raise ValueError(f"max_step ({v}) must be greater than min_step ({info.data['min_step']})")
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )
    file: Optional[str] = Field(
        default="robofocus_alpaca.log",
        description="Log file path (None for console only)"
    )

    @field_validator("level")
    @classmethod
    def validate_level(cls, v):
        """Validate logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class WebGuiConfig(BaseModel):
    """Web GUI configuration for simulator."""

    enabled: bool = Field(default=False, description="Enable web GUI")
    port: int = Field(default=8080, ge=1, le=65535, description="Web GUI port")
    use_path_prefix: bool = Field(
        default=False,
        description="Serve GUI on path prefix instead of separate port"
    )
    polling_interval_ms: int = Field(
        default=250, ge=50, le=2000, description="JavaScript polling interval (ms)"
    )


class SimulatorConfig(BaseModel):
    """Hardware simulator configuration."""

    enabled: bool = Field(default=False, description="Use simulator instead of real hardware")
    initial_position: int = Field(default=0, ge=0, description="Starting position")
    movement_speed_steps_per_sec: int = Field(
        default=500, ge=1, description="Simulated movement speed"
    )
    firmware_version: str = Field(default="002100", description="Firmware version (6 digits)")
    temperature_celsius: float = Field(default=16.85, description="Simulated temperature")
    temperature_noise_celsius: float = Field(
        default=0.0, ge=0, description="Temperature noise amplitude"
    )
    temperature_drift_per_hour: float = Field(
        default=0.0, description="Temperature drift (°C/hour)"
    )
    response_latency_ms: int = Field(
        default=0, ge=0, le=5000, description="Artificial response delay (ms)"
    )
    inject_timeout: bool = Field(default=False, description="Inject timeout errors")
    inject_checksum_error_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Checksum error rate (0.0-1.0)"
    )
    web_gui: WebGuiConfig = Field(default_factory=WebGuiConfig)

    @field_validator("firmware_version")
    @classmethod
    def validate_firmware_version(cls, v):
        """Validate firmware version format."""
        if not v.isdigit() or len(v) != 6:
            raise ValueError("Firmware version must be 6 digits (e.g., '002100')")
        return v


class AppConfig(BaseModel):
    """Root configuration model."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    serial: SerialConfig = Field(default_factory=SerialConfig)
    focuser: FocuserConfig = Field(default_factory=FocuserConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    simulator: SimulatorConfig = Field(default_factory=SimulatorConfig)

    class Config:
        """Pydantic config."""
        extra = "forbid"  # Raise error on unknown fields


class UserSettings(BaseModel):
    """
    User settings that persist locally between sessions.

    These are software-side preferences that are NOT stored in the
    Robofocus hardware (unlike max_travel and backlash which ARE stored
    in hardware).
    """

    last_port: Optional[str] = Field(
        default=None,
        description="Last successfully connected COM port"
    )
    max_increment: int = Field(
        default=60000,
        ge=1,
        le=65535,
        description="Maximum steps per single move command"
    )
    min_step: int = Field(
        default=0,
        ge=0,
        le=65535,
        description="Software minimum position limit"
    )
    zero_offset: int = Field(
        default=0,
        ge=0,
        le=999999,
        description="Hardware position that corresponds to logical zero"
    )
    use_simulator: Optional[bool] = Field(
        default=None,
        description="Use simulator mode instead of real hardware. None = use config.json"
    )

    class Config:
        """Pydantic config."""
        extra = "ignore"  # Ignore unknown fields for forward compatibility
