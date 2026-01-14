# Robofocus ASCOM Alpaca Driver

A modern, feature-rich ASCOM Alpaca v1 driver for Robofocus electronic focusers, written in Python with FastAPI.

## Features

### Core Functionality
- ✅ **ASCOM Alpaca API v1** - Full compliance with the standard
- ✅ **Real Hardware Support** - Direct RS-232 serial communication with Robofocus devices
- ✅ **Hardware Simulator** - Built-in virtual focuser for testing without hardware
- ✅ **Hot-Swappable Modes** - Switch between hardware and simulator via web GUI (when disconnected)
- ✅ **UDP Discovery** - Automatic detection in NINA and other ASCOM clients
- ✅ **Web Control Panel** - Modern, responsive web interface for manual control

### Advanced Features
- ✅ **Backlash Compensation** - INDI convention support (signed values: +OUT, -IN)
- ✅ **Temperature Monitoring** - Read focuser temperature sensor (if available)
- ✅ **Auto-Discovery** - Automatically scan and detect Robofocus devices on COM ports
- ✅ **Persistent Settings** - User preferences and hardware settings saved automatically
- ✅ **Movement Monitoring** - Real-time position tracking with caching
- ✅ **Protocol Logging** - Detailed communication logs for debugging
- ✅ **High COM Port Support** - Works with COM10+, COM12+, etc.
- ✅ **Thread-Safe** - Concurrent API requests handled correctly

### Stability Features
- ✅ **Backlash Query Caching** - Prevents movement interruption during polling
- ✅ **Hardware Settling Time** - Prevents position query timeout after movement
- ✅ **Config Auto-Save** - Hardware settings (firmware, max travel, backlash) saved on connection

## Requirements

- **Python 3.8+**
- **Windows** (for serial port access) or Linux/macOS with pyserial
- **Robofocus electronic focuser** (for hardware mode)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/RobofocusAscomAplaca.git
cd RobofocusAscomAplaca
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Driver

```bash
python -m robofocus_alpaca
```

The server will start on:
- **Alpaca API**: `http://localhost:5000/api/v1/focuser/0/`
- **Web GUI**: `http://localhost:5000/`
- **Setup Page**: `http://localhost:5000/setup/v1/focuser/0/setup`
- **UDP Discovery**: Port 32227 (for NINA auto-detection)

## Quick Start

### With NINA (N.I.N.A.)

1. Start the driver: `python -m robofocus_alpaca`
2. In NINA, go to **Equipment → Focuser**
3. Click **Alpaca Discovery** (or manually add `http://localhost:5000`)
4. Select **Robofocus** from the list
5. Click **Choose → Connect**
6. Test with "Move to" button or run Autofocus

### With Web GUI

1. Start the driver
2. Open `http://localhost:5000/` in your browser
3. Go to **Settings** to choose Hardware or Simulator mode
4. If Hardware: scan for device, select COM port, and connect
5. If Simulator: just connect (no hardware needed)
6. Use the control panel to move the focuser

## Configuration

### Config File (config.json)

On first run, the driver uses default settings. To customize, create a `config.json` file:

```json
{
  "server": {
    "ip": "0.0.0.0",
    "port": 5000,
    "discovery_enabled": true
  },
  "serial": {
    "port": "",
    "baud": 9600,
    "timeout_seconds": 5,
    "auto_discover": true,
    "scan_timeout_seconds": 1.0
  },
  "focuser": {
    "step_size_microns": 4.5,
    "max_step": 60000,
    "max_increment": 60000,
    "min_step": 0,
    "polling_interval_moving_ms": 100,
    "polling_interval_idle_sec": 5,
    "backlash_steps": 0
  },
  "logging": {
    "level": "INFO",
    "file": "robofocus_alpaca.log"
  },
  "simulator": {
    "enabled": false,
    "initial_position": 0,
    "movement_speed_steps_per_sec": 500,
    "firmware_version": "002100",
    "temperature_celsius": 16.85,
    "temperature_noise_celsius": 0.0,
    "temperature_drift_per_hour": 0.0
  }
}
```

### User Settings (user_settings.json)

User preferences are automatically saved and persist between sessions:
- **Last used COM port** - Automatically reconnects to last port
- **Maximum increment limit** - Safety limit for single moves
- **Minimum position limit** - Software-side minimum position
- **Mode preference** - Hardware or Simulator (overrides config.json)

These settings are managed via the web GUI and saved automatically.

## Web Control Panel

Open `http://localhost:5000/` in your browser to access the full control panel:

### Status Display
- Real-time position, temperature, connection status
- Current mode indicator (Hardware/Simulator)
- Firmware version
- COM port information

### Quick Step Controls
- Move **±1, ±10, ±100, ±1000** steps
- Instant response with visual feedback

### Absolute Positioning
- GoTo any specific position
- Input validation against min/max limits

### Emergency Stop
- **HALT** button to stop movement immediately
- Works during any movement operation

### Calibration
- **Set Zero** - Define current position as zero reference
- **Set Max Extension** - Set maximum travel limit (saved to hardware)
- **Set Min Position** - Set minimum position limit (software-side)
- **Set Max Increment** - Limit maximum steps per move
- **Set Backlash** - Configure backlash compensation (±255 steps, saved to hardware)

### Protocol Logs
- View real-time serial communication
- Filter by direction (sent/received)
- Statistics (total messages, errors, retries)
- Clear logs button

## Settings Page

Access `http://localhost:5000/setup/v1/focuser/0/setup` for configuration:

### Mode Selection
- **Hardware** - Real Robofocus device via serial port
- **Simulator** - Virtual device for testing
- Switch modes on-the-fly (only when disconnected)
- Preference saved and persists across restarts

### COM Port Selection (Hardware Mode)
- **Scan** - Auto-detect Robofocus devices on all ports
- **Port List** - View available COM ports
- **Connect/Disconnect** - Manage connection
- Auto-saves last used port

## API Endpoints

### ASCOM Alpaca API

Standard ASCOM Alpaca v1 endpoints:

- `GET /api/v1/focuser/0/connected` - Connection status
- `PUT /api/v1/focuser/0/connected` - Connect/disconnect
- `GET /api/v1/focuser/0/position` - Current position
- `PUT /api/v1/focuser/0/move` - Move to absolute position
- `GET /api/v1/focuser/0/ismoving` - Movement status
- `PUT /api/v1/focuser/0/halt` - Emergency stop
- `GET /api/v1/focuser/0/temperature` - Temperature in °C
- `GET /api/v1/focuser/0/maxstep` - Maximum position
- `GET /api/v1/focuser/0/maxincrement` - Maximum single move
- `GET /api/v1/focuser/0/stepsize` - Step size in microns
- `GET /api/v1/focuser/0/absolute` - Returns `true`
- `GET /api/v1/focuser/0/backlash` - Backlash compensation value (IFocuserV4)
- `PUT /api/v1/focuser/0/backlash` - Set backlash (IFocuserV4)
- `GET /api/v1/focuser/0/interfaceversion` - Returns `3` (IFocuserV4)
- `GET /api/v1/focuser/0/driverversion` - Returns `"1.0.0"`
- `GET /api/v1/focuser/0/description` - Device description
- `GET /api/v1/focuser/0/name` - Returns `"Robofocus"`

### Web GUI API

Custom endpoints for web interface:

- `GET /gui/status` - Complete focuser status (JSON)
- `GET /gui/ports` - List available COM ports
- `POST /gui/scan` - Scan for Robofocus devices
- `POST /gui/connect` - Connect to specific port
- `POST /gui/disconnect` - Disconnect
- `POST /gui/move` - Move focuser (relative or absolute)
- `POST /gui/halt` - Stop movement
- `POST /gui/set-zero` - Set zero point
- `POST /gui/set-max` - Set max extension
- `POST /gui/set-min` - Set min position
- `POST /gui/set-max-increment` - Set max increment
- `POST /gui/set-backlash` - Set backlash
- `GET /gui/logs` - Get protocol logs
- `POST /gui/logs/clear` - Clear logs
- `GET /gui/mode` - Get current mode (hardware/simulator)
- `PUT /gui/mode` - Switch mode

## Architecture

The driver is organized in three layers:

1. **API Layer** - FastAPI endpoints for ASCOM Alpaca and Web GUI
2. **Controller Layer** - State machine, movement tracking, position caching
3. **Protocol Layer** - Serial communication and device abstraction

### Key Components

```
robofocus_alpaca/
├── api/                    # FastAPI HTTP server
│   ├── app.py             # Application factory
│   ├── routes.py          # Alpaca endpoints
│   ├── gui_api.py         # Web GUI API
│   ├── models.py          # Response models
│   └── discovery.py       # UDP discovery server
├── protocol/              # Serial protocol layer
│   ├── interface.py       # Abstract protocol interface
│   ├── robofocus_serial.py # Real hardware protocol
│   ├── port_scanner.py    # COM port auto-discovery
│   ├── checksum.py        # Checksum utilities
│   └── logger.py          # Protocol message logging
├── focuser/               # Business logic
│   └── controller.py      # State machine and caching
├── simulator/             # Hardware simulator
│   ├── mock_serial.py     # Mock protocol implementation
│   └── web_api.py         # Simulator control API
├── config/                # Configuration management
│   ├── models.py          # Pydantic validation models
│   ├── loader.py          # JSON config loader
│   └── user_settings.py   # Persistent user preferences
├── static/                # Web GUI assets
│   ├── index.html         # Control panel
│   └── logs.html          # Protocol logs viewer
├── utils/                 # Utilities
│   ├── exceptions.py      # Custom exceptions
│   └── logging_setup.py   # Logging configuration
└── __main__.py            # Entry point
```

## Robofocus Protocol

The driver implements the Robofocus RS-232 serial protocol:

- **Baud Rate**: 9600, 8N1
- **Packet Format**: 9 bytes (command + 6-digit hex value + 2-byte checksum)
- **Asynchronous Movement**: Hardware sends 'I' (inward), 'O' (outward), 'F' (finished) during motion
- **Commands**: FG (position), FI/FO (move), FQ (halt), FT (temperature), FB (backlash), FD (max travel), etc.
- **Checksum**: XOR of all bytes (command + value)

## Development

### Running in Development Mode

```bash
# With auto-reload (requires uvicorn)
uvicorn robofocus_alpaca.__main__:app --reload --port 5000

# With custom config
python -m robofocus_alpaca --config my_config.json
```

### Debugging

Enable debug logging in `config.json`:

```json
{
  "logging": {
    "level": "DEBUG",
    "file": "robofocus_alpaca.log"
  }
}
```

View detailed protocol logs:
- In browser: `http://localhost:5000/logs.html`
- In file: `robofocus_alpaca.log`

### Project Dependencies

- **FastAPI** - Modern web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation
- **pyserial** - Serial port communication

## Troubleshooting

### Driver not appearing in NINA

- Check Windows Firewall (allow UDP port 32227)
- Verify driver is running: `python -m robofocus_alpaca`
- Check logs: `robofocus_alpaca.log`
- Try manual connection in NINA: `http://localhost:5000`

### Timeout errors during movement

- **Issue**: "Command FG retry" warnings after movement
- **Fixed in v1.0**: Automatic 150ms settling delay prevents this

### Movement takes too long / interrupted

- **Issue**: "Unexpected response to FB: FD" during movement
- **Fixed in v1.0**: Backlash queries return cached value during movement

### COM port not found

- Verify Robofocus is powered on and connected
- Check Device Manager (Windows) for COM port number
- Try manual port specification in `config.json`: `"serial": {"port": "COM12"}`
- Use **Scan** button in Settings page to auto-detect

### Web GUI not loading

- Verify port 5000 is not in use by another application
- Check browser console for errors
- Try accessing directly: `http://127.0.0.1:5000/`

### Cannot switch mode

- **Error**: "Cannot switch mode while connected"
- **Solution**: Disconnect first, then switch mode in Settings

## Known Issues

- Position query requires 150ms settling time after movement completes (hardware limitation)
- Some older Robofocus firmware versions may not support all commands (backlash, max travel)
- Windows Firewall may block UDP discovery - allow port 32227

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes with clear, descriptive commits
4. Add tests if applicable
5. Update documentation (README, docstrings)
6. Push to your fork: `git push origin feature/amazing-feature`
7. Open a Pull Request with a clear description

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

- **Author**: Samuele Vecchi
- **Co-Authored**: Claude Sonnet 4.5
- **References**:
  - ASCOM.NGCAT.Focuser (C# reference implementation)
  - robofocus.cpp (INDI driver)
  - ASCOM Alpaca API Specification v1

## Acknowledgments

- **ASCOM Initiative** - For the Alpaca API standard
- **Robofocus** - For the excellent focuser hardware
- **FastAPI** - For the modern Python web framework
- **NINA** - For inspiration and testing support
- **Astrophotography Community** - For feedback and testing

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/RobofocusAscomAplaca/issues)
- **Discussions**: NINA Discord, CloudyNights forum
- **Pull Requests**: Always welcome!

---

**Made with ❤️ for the astrophotography community**
