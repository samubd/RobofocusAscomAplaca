"""
Main entry point for Robofocus ASCOM Alpaca Driver.

Usage:
    python -m robofocus_alpaca [--config CONFIG_PATH]
"""

import argparse
import sys
import logging
import signal
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from robofocus_alpaca.config.loader import load_config, ConfigurationError
from robofocus_alpaca.config.models import AppConfig, SerialConfig
from robofocus_alpaca.config.user_settings import init_user_settings, get_user_settings
from robofocus_alpaca.utils.logging_setup import setup_logging
from robofocus_alpaca.api.app import create_app
from robofocus_alpaca.api.routes import router as focuser_router
from robofocus_alpaca.api.gui_api import router as gui_router
from robofocus_alpaca.api.discovery import DiscoveryServer
from robofocus_alpaca.focuser.controller import FocuserController
from robofocus_alpaca.simulator.mock_serial import MockSerialProtocol
from robofocus_alpaca.simulator.web_api import router as simulator_router
from robofocus_alpaca.protocol.robofocus_serial import RobofocusSerial
from robofocus_alpaca.protocol.port_scanner import find_first_robofocus, list_available_ports


logger = logging.getLogger(__name__)


# Global resources for cleanup
discovery_server = None
focuser_controller = None


def signal_handler(signum, frame):
    """Handle shutdown signals (SIGINT, SIGTERM)."""
    logger.info(f"Received signal {signum}, shutting down...")

    # Stop discovery server
    if discovery_server:
        discovery_server.stop()

    # Disconnect focuser
    if focuser_controller:
        focuser_controller.disconnect()

    sys.exit(0)


def main():
    """Main application entry point."""
    global discovery_server, focuser_controller

    # Parse arguments
    parser = argparse.ArgumentParser(description="Robofocus ASCOM Alpaca Driver")
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to configuration file (default: config.json)"
    )
    args = parser.parse_args()

    # Load configuration
    try:
        config = load_config(args.config)
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    setup_logging(config.logging)

    logger.info("=" * 60)
    logger.info("Robofocus ASCOM Alpaca Driver v1.0.0")
    logger.info("=" * 60)

    # Initialize user settings (persisted preferences)
    user_settings = init_user_settings()
    logger.info(f"User settings loaded (last_port: {user_settings.last_port or 'none'})")

    # Apply user settings to focuser config
    if user_settings.max_increment != config.focuser.max_increment:
        logger.info(f"Using saved max_increment: {user_settings.max_increment}")
        config.focuser.max_increment = user_settings.max_increment

    if user_settings.min_step != config.focuser.min_step:
        logger.info(f"Using saved min_step: {user_settings.min_step}")
        config.focuser.min_step = user_settings.min_step

    # Determine mode: user preference overrides config.json
    # This allows runtime mode switching via GUI
    use_simulator = user_settings.use_simulator
    if use_simulator != config.simulator.enabled:
        logger.info(f"User preference overrides config: use_simulator={use_simulator}")

    # Create protocol instance (simulator or real hardware)
    if use_simulator:
        logger.info("Using SIMULATOR mode")
        protocol = MockSerialProtocol(config.simulator)
    else:
        logger.info("Using REAL HARDWARE mode")

        # Determine which port to use
        port_to_use = None

        # Priority 1: Port explicitly specified in config
        if config.serial.port:
            port_to_use = config.serial.port
            logger.info(f"Using manually specified port: {port_to_use}")

        # Priority 2: Last successfully used port from user settings
        elif user_settings.last_port:
            port_to_use = user_settings.last_port
            logger.info(f"Trying last used port: {port_to_use}")

        # Priority 3: If auto-discover is enabled, scan for Robofocus
        if not port_to_use and config.serial.auto_discover:
            logger.info("Auto-discovering Robofocus device...")

            # List available ports for user information
            available_ports = list_available_ports()
            if available_ports:
                logger.info(f"Available COM ports: {', '.join(p.name for p in available_ports)}")
            else:
                logger.warning("No COM ports found on system")

            # Scan for Robofocus
            device = find_first_robofocus(
                timeout_seconds=config.serial.scan_timeout_seconds
            )

            if device:
                port_to_use = device.port
                logger.info(f"Auto-discovered Robofocus on {port_to_use} (firmware: {device.firmware_version})")
            else:
                logger.error("No Robofocus device found on any COM port")
                logger.error("Please connect the device or specify port manually in config.json")
                sys.exit(1)

        # No port available
        if not port_to_use:
            logger.error("No serial port specified and auto-discover is disabled")
            logger.error("Please set 'serial.port' in config.json or enable 'serial.auto_discover'")
            sys.exit(1)

        # Create serial config with discovered port
        serial_config = SerialConfig(
            port=port_to_use,
            baud=config.serial.baud,
            timeout_seconds=config.serial.timeout_seconds,
            auto_discover=config.serial.auto_discover,
            scan_timeout_seconds=config.serial.scan_timeout_seconds,
        )

        # Create real serial protocol
        protocol = RobofocusSerial(serial_config)

    # Create focuser controller with full config for saving
    focuser_controller = FocuserController(
        protocol,
        config.focuser,
        app_config=config,
        config_path=args.config
    )

    # Create FastAPI app
    app = create_app(config)

    # Store dependencies in app.state for access by route handlers
    app.state.focuser = focuser_controller
    app.state.simulator = protocol if use_simulator else None
    app.state.config = config
    app.state.user_settings = user_settings

    # Include simulator API routes if in simulator mode
    if use_simulator:
        app.include_router(simulator_router)

    # Include Alpaca API routes
    app.include_router(focuser_router)

    # Include GUI API routes (works in both modes)
    app.include_router(gui_router)

    # Mount unified static files for web GUI (works in both modes)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        logger.info("Web GUI enabled")
    else:
        logger.warning(f"Static directory not found: {static_dir}")

    # Determine which port the server will use
    server_port = config.server.port

    # Start discovery server with the actual server port
    if config.server.discovery_enabled:
        discovery_server = DiscoveryServer(server_port)
        try:
            discovery_server.start()
        except Exception as e:
            logger.error(f"Failed to start discovery server: {e}")
            logger.warning("Continuing without discovery (NINA won't auto-detect)")

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start server
    logger.info(f"Starting Alpaca API server on {config.server.ip}:{server_port}")
    logger.info(f"Web GUI available at http://localhost:{server_port}/")
    logger.info("Press Ctrl+C to stop")

    try:
        uvicorn.run(
            app,
            host=config.server.ip,
            port=server_port,
            log_level=config.logging.level.lower(),
            access_log=False  # Disable noisy HTTP access logs
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if discovery_server:
            discovery_server.stop()
        if focuser_controller:
            focuser_controller.disconnect()

        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
