# Change: Add Robofocus ASCOM Alpaca Driver

## Why

The current Robofocus driver is a legacy ASCOM COM-based implementation that has critical limitations on modern Windows systems:

- **Serial Port Limitation**: Limited to COM1-COM8 only, incompatible with modern USB-to-serial adapters that often assign COM10+
- **64-bit Compatibility**: Poor stability on Windows 10/11 64-bit systems
- **Single Client Architecture**: COM-based design limits concurrent access from multiple astronomy applications

These limitations cause frequent connection failures during astrophotography sessions, resulting in lost imaging time and data.

## What Changes

This proposal introduces a complete ASCOM Alpaca middleware driver in Python that acts as a bridge between astronomy clients (NINA, Voyager, SGP) and the Robofocus hardware:

### Core Components

1. **Alpaca HTTP API Server** (Layer 3)
   - RESTful endpoints compliant with ASCOM Alpaca API v1
   - UDP discovery protocol for automatic device detection
   - JSON response envelope with transaction IDs
   - Error handling with standard Alpaca error codes (0x400-0x5FF)

2. **Serial Protocol Handler** (Layer 1)
   - 9-byte fixed-length command/response protocol
   - Checksum validation (modulo 256 on 8 bytes)
   - Support for all Robofocus commands (FV, FG, FD, FT, FB, FL, FC, FP, FS, FQ)
   - Asynchronous movement status characters ('I', 'O', 'F')
   - Thread-safe serial port access with mutex locking

3. **Hardware Simulator** (Development Tool)
   - Mock Robofocus device for testing without hardware
   - Simulates movement with realistic timing
   - Virtual temperature sensor
   - Configurable response delays and error injection

### Features

- **Absolute Positioning**: Move to specific step position (0 to MaxStep)
- **Temperature Reading**: Celsius conversion from raw ADC ((raw/2.0) - 273.15)
- **Movement Control**: Non-blocking move with IsMoving status polling
- **Emergency Halt**: Immediate stop command
- **Backlash Compensation**: Configurable inward/outward backlash (0-255 steps)
- **Position Limits**: Software and hardware travel limits
- **Configuration**: JSON-based configuration file with serial port, polling intervals, limits

### Development Approach

**Top-Down Implementation Strategy**:
1. Phase 1: HTTP API skeleton + Hardware simulator
2. Phase 2: Integration testing (NINA → Alpaca API → Simulator)
3. Phase 3: Serial protocol handler + Real hardware integration
4. Phase 4: Field testing with telescope

This approach enables:
- Early validation of API contract with astronomy clients
- Parallel development of API and protocol layers
- Testing without physical hardware dependency

## Impact

### Affected Capabilities (New Specs)

- **specs/alpaca-driver**: HTTP API endpoints, discovery, error handling
- **specs/serial-protocol**: Robofocus command/response protocol
- **specs/hardware-simulator**: Mock device implementation

### Affected Code

- New Python package structure:
  ```
  robofocus_alpaca/
  ├── api/          # FastAPI endpoints (Layer 3)
  ├── protocol/     # Serial communication (Layer 1)
  ├── focuser/      # State machine (Layer 2)
  ├── simulator/    # Mock hardware
  ├── config/       # Configuration handling
  └── utils/        # Logging, validation
  ```

### Breaking Changes

None (new implementation, not modifying existing code)

### Migration Path

End users will:
1. Install Python driver via pip or standalone executable
2. Configure serial port in config.json
3. Start driver (runs as background service or console app)
4. Connect NINA to `http://localhost:5000` via Alpaca discovery
5. Optionally uninstall legacy COM driver

### Risks

- **Firmware Variants**: Different Robofocus firmware versions may have protocol differences (mitigation: test with multiple devices)
- **Serial Adapter Compatibility**: Some USB-serial chips may have driver issues on Windows (mitigation: document tested adapters)
- **Performance**: Python GIL may impact polling frequency (mitigation: benchmark early, optimize if needed)

### Success Criteria

- Driver discoverable in NINA Equipment Manager
- Complete autofocus session (20+ moves) without errors
- Temperature reading accurate within ±0.5°C
- Halt command stops movement within 500ms
- 24-hour continuous operation without crashes
