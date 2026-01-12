# Robofocus ASCOM Alpaca Driver

Python-based ASCOM Alpaca middleware driver for Robofocus electronic focuser.

## Features

- ✅ **ASCOM Alpaca API v1** - Full compliance with standard
- ✅ **UDP Discovery** - Auto-detection in NINA
- ✅ **Hardware Simulator** - Test without physical device
- ✅ **Web GUI** - Visual control panel for simulator
- ✅ **High COM Port Support** - Works with COM10, COM12, etc.
- ✅ **Thread-Safe** - Concurrent API requests handled correctly
- ✅ **Temperature Sensor** - Reads ambient temperature

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Driver (Simulator Mode)

```bash
python -m robofocus_alpaca
```

The driver will start with:
- **Alpaca API**: http://localhost:5000/api/v1/focuser/0/
- **Web GUI**: http://localhost:8080 (simulator control panel)
- **UDP Discovery**: Port 32227 (for NINA auto-detection)

### 3. Open Web GUI

Navigate to http://localhost:8080 in your browser to control the simulator:

- **Current Position** - Real-time display
- **Quick Step Controls** - ±1, ±10 steps
- **Custom Steps** - Move by N steps
- **GoTo Position** - Absolute positioning
- **HALT Button** - Emergency stop
- **Temperature** - Simulated sensor reading

### 4. Connect from NINA

1. Open NINA Equipment Manager
2. Click "Alpaca Discovery"
3. Select "Robofocus" from the list
4. Click "Choose" → "Connect"
5. Test with "Move to" button or run Autofocus

## Configuration

Edit `config.json` to customize settings:

```json
{
  "server": {
    "port": 5000,
    "discovery_enabled": true
  },
  "simulator": {
    "enabled": true,
    "movement_speed_steps_per_sec": 500,
    "temperature_celsius": 16.85,
    "web_gui": {
      "enabled": true,
      "port": 8080
    }
  },
  "focuser": {
    "max_step": 60000,
    "step_size_microns": 4.5
  }
}
```

## Development

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
black robofocus_alpaca/
pylint robofocus_alpaca/
```

### Build Standalone Executable

```bash
pyinstaller robofocus_alpaca.spec
```

## API Endpoints

### Alpaca Focuser API

- `GET /api/v1/focuser/0/connected` - Connection status
- `PUT /api/v1/focuser/0/connected` - Connect/disconnect (form: `Connected=true`)
- `GET /api/v1/focuser/0/position` - Current position
- `PUT /api/v1/focuser/0/move` - Move to position (form: `Position=5000`)
- `GET /api/v1/focuser/0/ismoving` - Movement status
- `PUT /api/v1/focuser/0/halt` - Emergency stop
- `GET /api/v1/focuser/0/temperature` - Temperature in °C
- `GET /api/v1/focuser/0/maxstep` - Maximum position
- `GET /api/v1/focuser/0/stepsize` - Step size in microns
- `GET /api/v1/focuser/0/absolute` - Returns `true`
- `GET /api/v1/focuser/0/interfaceversion` - Returns `2`
- `GET /api/v1/focuser/0/driverversion` - Returns `"1.0.0"`
- `GET /api/v1/focuser/0/description` - Device description
- `GET /api/v1/focuser/0/name` - Returns `"Robofocus"`

### Simulator Web API

- `GET /simulator/status` - Get current simulator state (JSON)
- `POST /simulator/move` - Move simulator (JSON: `{"steps": 10, "direction": "out"}` or `{"position": 5000}`)
- `POST /simulator/halt` - Stop movement

## Project Structure

```
robofocus_alpaca/
├── api/                  # FastAPI HTTP server
│   ├── app.py           # Application factory
│   ├── routes.py        # Alpaca endpoints
│   ├── models.py        # Response models
│   ├── discovery.py     # UDP discovery
│   └── error_mapper.py  # Exception → Alpaca errors
├── protocol/            # Serial protocol layer
│   ├── interface.py     # Abstract interface
│   ├── checksum.py      # Checksum utilities
│   └── encoder.py       # Command encoding/parsing
├── focuser/             # Business logic
│   └── controller.py    # State machine
├── simulator/           # Hardware simulator
│   ├── mock_serial.py   # Mock protocol implementation
│   ├── web_api.py       # Web GUI API
│   └── static/          # Web GUI HTML/CSS/JS
│       └── index.html
├── config/              # Configuration
│   ├── models.py        # Pydantic models
│   └── loader.py        # JSON loader
├── utils/               # Utilities
│   ├── exceptions.py    # Custom exceptions
│   └── logging_setup.py # Logging configuration
└── __main__.py          # Entry point
```

## Troubleshooting

### Driver not appearing in NINA

- Check Windows Firewall (allow UDP port 32227)
- Verify driver is running (`python -m robofocus_alpaca`)
- Check logs: `robofocus_alpaca.log`

### Timeout errors

- Increase `serial.timeout_seconds` in config.json
- Check cable connection (if using real hardware)

### Web GUI not loading

- Verify port 8080 is not in use
- Check browser console for errors
- Ensure `simulator.web_gui.enabled=true` in config

## License

MIT License - See LICENSE file

## Credits

- **Author**: Samuele Vecchi
- **Co-Authored**: Claude Sonnet 4.5
- **References**:
  - ASCOM.NGCAT.Focuser (C#)
  - robofocus.cpp (INDI driver)
  - ASCOM Alpaca API Specification v1

## Support

- Issues: https://github.com/yourusername/robofocus-alpaca/issues
- Discussions: NINA Discord, CloudyNights forum
