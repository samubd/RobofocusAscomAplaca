# Project Context

## Purpose
ASCOM Alpaca middleware driver in Python for controlling Robofocus electronic focuser hardware. Replaces legacy ASCOM COM-based driver to eliminate Windows serial port limitations (COM1-COM8 only) and improve stability on modern 64-bit systems.

## Tech Stack
- Python 3.9+
- FastAPI (REST API framework)
- uvicorn (ASGI server)
- pyserial (serial communication)
- pydantic (data validation)

## Project Conventions

### Code Style
- PEP 8 compliance
- Type hints for all functions
- Black formatter (line length: 100)
- pylint for linting
- Docstrings for public APIs (Google style)

### Architecture Patterns
- **3-Layer Architecture**:
  - Layer 1: Serial Protocol Handler (low-level hardware communication)
  - Layer 2: Focuser State Machine (business logic, state tracking)
  - Layer 3: Alpaca HTTP API (REST endpoint mapping)
- **Thread Safety**: Single global lock for serial port access
- **Non-blocking Operations**: Move commands return immediately, status polled separately
- **Simulator Mode**: Mock hardware for development/testing without physical device

### Testing Strategy
- Unit tests for protocol encoding/decoding (pytest)
- Integration tests with hardware simulator
- Field tests with real Robofocus device
- Continuous integration via GitHub Actions

### Git Workflow
- Main branch for stable releases
- Feature branches: `feature/<name>`
- Commit messages: Conventional Commits format
- Co-authored by: Claude Sonnet 4.5 <noreply@anthropic.com>

## Domain Context

### ASCOM Alpaca Protocol
- RESTful API standard for astronomy devices (v1)
- Discovery via UDP broadcast on port 32227
- HTTP endpoints follow `/api/v1/focuser/{device_id}/` pattern
- Responses in JSON envelope with ClientTransactionID/ServerTransactionID
- Error codes: 0x400-0x5FF range

### Robofocus Hardware
- Electronic focuser for telescopes (deep-sky astrophotography)
- RS-232 serial communication (9600 baud, 8N1)
- Fixed 9-byte command/response protocol
- Supports absolute positioning, temperature sensor, backlash compensation
- Used with clients: NINA, Voyager, Sequence Generator Pro (SGP)

### Astrophotography Workflow
- Focuser integrates in autofocus routines (HFR/FWHM optimization)
- Typical session: 4-8 hours unattended imaging
- Reliability critical: failed focus = lost data
- Temperature compensation needed (focus shifts with temp)

## Important Constraints

### Hardware Limitations
- Serial communication is synchronous (no concurrent commands)
- Firmware timeout: 3-5 seconds per command
- No absolute encoder: power loss = position unknown
- Movement speed fixed by motor configuration (not controllable via API)

### Software Constraints
- Must run on Windows 10/11 64-bit (primary user base)
- Should support high COM port numbers (COM10+)
- Alpaca standard compliance mandatory (NINA compatibility)
- Python environment may be restricted (consider PyInstaller for distribution)

### Performance Requirements
- API response time: <100ms for GET requests
- Move command initiation: <50ms
- Polling overhead: <5% CPU during idle
- Uptime target: 24/7 multi-night sessions

## External Dependencies

### Reference Implementations
- `ASCOM.NGCAT.Focuser` (C# ASCOM driver) - protocol reference
- `robofocus.cpp` (INDI driver) - alternative implementation
- ASCOM Alpaca API specification v1

### Client Software
- NINA (Nighttime Imaging 'N' Astronomy) - primary target
- Voyager Advanced - secondary target
- Sequence Generator Pro (SGP) - tertiary target

### Hardware
- Robofocus electronic focuser (various firmware versions)
- RS-232 serial connection (USB-to-Serial adapters common)
- Windows serial port drivers (CH340, FTDI, etc.)
