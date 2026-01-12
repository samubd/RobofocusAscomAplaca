# Design Document: Robofocus ASCOM Alpaca Driver

## Context

The Robofocus electronic focuser is a critical component in deep-sky astrophotography workflows, enabling automated focus adjustments during long imaging sessions (4-24 hours). The existing Windows COM-based driver has limitations that cause connection failures on modern systems with USB serial adapters.

This design document outlines the architecture for a Python-based ASCOM Alpaca middleware driver that bridges HTTP REST clients (NINA, Voyager) with RS-232 serial hardware.

### Stakeholders

- **End Users**: Amateur astronomers using NINA for imaging automation
- **Developers**: Maintainers of this driver codebase
- **Hardware**: Robofocus firmware (multiple versions in field)

### Constraints

- Must comply with ASCOM Alpaca API v1 specification (non-negotiable)
- Python 3.9+ (widest Windows 10/11 compatibility)
- Serial communication is inherently synchronous (hardware limitation)
- No control over client behavior (NINA/Voyager polling frequency unknown)

## Goals / Non-Goals

### Goals

1. **Reliability**: 24+ hour uptime during unattended imaging sessions
2. **Compatibility**: Support COM ports beyond COM8 (COM10, COM12, etc.)
3. **Testability**: Simulator mode for development without hardware
4. **Standards Compliance**: Full ASCOM Alpaca v1 conformance
5. **Observability**: Structured logging for troubleshooting field issues

### Non-Goals

1. **Multi-device Support**: Single focuser only (device_id=0 hardcoded)
2. **GUI Configuration**: Config via JSON file only (no UI)
3. **Firmware Updates**: Driver is read-only to firmware
4. **Cross-platform**: Windows-first (Linux/macOS nice-to-have later)

## Decisions

### Decision 1: Three-Layer Architecture

**Choice**: Separate concerns into API, Business Logic, and Protocol layers

```
┌─────────────────────────────────────────┐
│   Layer 3: Alpaca HTTP API (FastAPI)   │  ← NINA / Voyager
├─────────────────────────────────────────┤
│   Layer 2: Focuser State Machine       │  ← Position cache, IsMoving flag
├─────────────────────────────────────────┤
│   Layer 1: Serial Protocol Handler     │  ← Robofocus hardware
└─────────────────────────────────────────┘
```

**Rationale**:
- **Testability**: Each layer can be unit-tested independently
- **Maintainability**: Protocol changes isolated to Layer 1
- **Substitutability**: Simulator swaps Layer 1 implementation

**Alternatives Considered**:
- **Monolithic Design**: Simpler but harder to test, rejected for maintainability
- **Microservices**: Over-engineered for single-device driver, rejected for complexity

### Decision 2: FastAPI for HTTP Server

**Choice**: Use FastAPI with uvicorn ASGI server

**Rationale**:
- **Type Safety**: Pydantic models auto-validate request parameters
- **Performance**: Async support (though serial is sync, future-proofs API)
- **OpenAPI**: Auto-generated docs for debugging
- **Ecosystem**: Well-supported on Windows via pip

**Alternatives Considered**:
- **Flask**: Simpler but lacks async, type validation - rejected
- **aiohttp**: Lower-level, more boilerplate - rejected

### Decision 3: Global Lock for Serial Access

**Choice**: Single `threading.Lock` around all serial write/read operations

```python
class SerialProtocol:
    def __init__(self):
        self._serial_lock = threading.Lock()

    def send_command(self, cmd: str) -> str:
        with self._serial_lock:
            self._port.write(cmd.encode())
            return self._port.read(9)
```

**Rationale**:
- **Safety**: Prevents interleaved writes (corruption)
- **Simplicity**: No complex queue management needed
- **Performance**: Serial is bottleneck, not lock contention

**Alternatives Considered**:
- **Lock-free Queue**: Producer-consumer pattern with dedicated serial thread
  - **Pros**: Cleaner separation, better for high-frequency commands
  - **Cons**: More complex, overkill for typical 1-2 commands/second load
  - **Decision**: Rejected for initial implementation, revisit if profiling shows lock contention

### Decision 4: Non-Blocking Move with Polling

**Choice**: `PUT /move` returns immediately, client polls `GET /ismoving`

**Sequence**:
```
Client → PUT /move (pos=5000)
Server → Send FG005000, set flag isMoving=true, return HTTP 200
        [Background: poll position via FD, update cache]
Client → GET /ismoving (repeat every 100-250ms)
Server → Return {"Value": true/false}
```

**Rationale**:
- **Alpaca Standard**: Spec requires non-blocking move operations
- **Responsiveness**: HTTP timeouts avoided (move takes 10-60 seconds)
- **Client Control**: NINA controls polling frequency

**Alternatives Considered**:
- **Blocking Move**: Wait until completion before returning
  - **Rejected**: Violates Alpaca spec, causes HTTP timeouts

### Decision 5: Hardware Simulator as Separate Class

**Choice**: `MockSerialProtocol` implements same interface as `RobofocusSerial`

```python
class SerialProtocolInterface(ABC):
    @abstractmethod
    def send_command(self, cmd: str) -> str: ...

class RobofocusSerial(SerialProtocolInterface):
    def __init__(self, port: str, baud: int): ...

class MockSerialProtocol(SerialProtocolInterface):
    def __init__(self, config: SimulatorConfig): ...
```

**Rationale**:
- **Dependency Injection**: State machine agnostic to hardware vs simulator
- **Testing**: Unit tests use simulator, integration tests use real hardware
- **Development**: No physical device needed for API layer work

**Implementation Details**:
- Simulator maintains virtual position counter
- `time.sleep()` to emulate movement duration
- Configurable error injection (timeout, checksum fail)

### Decision 6: Configuration via JSON File

**Choice**: Single `config.json` loaded at startup

```json
{
  "server": {
    "ip": "0.0.0.0",
    "port": 5000,
    "discovery_enabled": true
  },
  "serial": {
    "port": "COM12",
    "baud": 9600,
    "timeout_seconds": 5
  },
  "focuser": {
    "step_size_microns": 4.5,
    "max_step": 60000,
    "min_step": 0,
    "polling_interval_moving_ms": 100,
    "polling_interval_idle_sec": 5
  },
  "logging": {
    "level": "INFO",
    "file": "robofocus_alpaca.log"
  },
  "simulator": {
    "enabled": false,
    "movement_speed_steps_per_sec": 500
  }
}
```

**Rationale**:
- **User-Friendly**: Text file editable without GUI
- **Validation**: Pydantic models catch typos at startup
- **Portability**: Copy config.json to new machine

**Alternatives Considered**:
- **ASCOM Profile Store** (Windows Registry): Rejected for cross-platform future
- **Environment Variables**: Rejected for poor discoverability

### Decision 7: Temperature Formula Hardcoded

**Choice**: `celsius = (raw_adc / 2.0) - 273.15` (no configurable slope/offset)

**Rationale**:
- **Firmware Standard**: All known Robofocus firmware use this formula
- **Simplicity**: Fewer configuration knobs = fewer user errors
- **Evidence**: Confirmed in both ASCOM.NGCAT.Focuser and robofocus.cpp

**Future Work**: If firmware variants discovered, add `temp_conversion` config section

### Decision 8: Error Mapping to Alpaca Codes

**Choice**: Python exceptions mapped to specific Alpaca ErrorNumber

| Python Exception | Alpaca ErrorNumber | Use Case |
|------------------|-------------------|----------|
| `serial.SerialTimeoutException` | 0x500 (DriverError) | Hardware timeout |
| `ChecksumMismatchError` | 0x500 (DriverError) | Corrupted response |
| `ValueError` (parse fail) | 0x402 (InvalidValue) | Malformed position |
| `NotConnectedError` | 0x407 (NotConnected) | Serial port closed |
| `PortInUseError` | 0x500 (DriverError) | COM port locked |
| `Exception` (uncaught) | 0x500 (DriverError) | Unexpected failure |

**Rationale**:
- **Diagnostics**: Client logs show meaningful error codes
- **Robustness**: No unhandled exceptions crash the server

### Decision 9: Asynchronous Movement Status via 'I'/'O'/'F' Characters

**Choice**: Parse streaming characters during move polling

**Protocol**:
- `'I'` (0x49): Inward movement, decrement cached position
- `'O'` (0x4F): Outward movement, increment cached position
- `'F'` (0x46): Movement finished, read final position (FDxxxxxx packet)

**Rationale**:
- **Firmware Behavior**: Robofocus sends these unsolicited during movement
- **Cache Accuracy**: Real-time position updates improve client UX
- **Halt Detection**: 'F' character signals completion

**Implementation**:
```python
while is_moving:
    char = serial.read(1)
    if char == b'I': position -= 1
    elif char == b'O': position += 1
    elif char == b'F':
        response = serial.read(8)  # Read remaining packet
        position = parse_position(response)
        is_moving = False
```

### Decision 10: Halt Command via FQ (Not \r)

**Choice**: Use `FQ000000` + checksum for emergency stop

**Rationale**:
- **ASCOM Reference**: `ASCOM.NGCAT.Focuser` uses FQ
- **Standard Protocol**: Follows 9-byte command format
- **Note**: robofocus.cpp uses `\r` (carriage return) - firmware variant difference

**Risk Mitigation**: Document both methods, test with user's hardware, fallback if needed

### Decision 11: Web GUI for Simulator

**Choice**: Add web-based control panel to simulator for manual testing and debugging

**Features**:
- Real-time position and temperature display
- Manual step controls: ±1, ±10, ±N steps
- Absolute GoTo position input
- HALT button for emergency stop
- Configuration display (speed, limits, firmware version)
- Responsive layout (desktop/tablet)
- Self-contained (no external CDN dependencies)

**Architecture**:
```
┌─────────────────────────────────────────┐
│   Browser (HTML/CSS/JS)                 │
│   ├── Position Display (polling 250ms) │
│   ├── Control Buttons (+1, +10, +N)    │
│   └── AJAX → /simulator/status         │
└─────────────────────────────────────────┘
            ↓ HTTP
┌─────────────────────────────────────────┐
│   FastAPI Web Server                    │
│   ├── Port 8080: Static HTML + API     │
│   └── GET /simulator/status (JSON)     │
│       POST /simulator/move              │
│       POST /simulator/halt              │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│   MockSerialProtocol (Simulator)        │
│   └── Shared state with Alpaca API     │
└─────────────────────────────────────────┘
```

**Rationale**:
- **Development Efficiency**: Manual testing without writing test scripts or curl commands
- **Debugging Tool**: Visual feedback during development and troubleshooting
- **Demo/Training**: Show driver behavior to users without astronomy software
- **Integration Testing**: Verify API and simulator work correctly before hardware available

**Alternatives Considered**:
- **CLI Control**: Text-based commands (e.g., `simulator-cli move 1000`)
  - **Pros**: Simpler to implement, scriptable
  - **Cons**: Poor UX, harder to visualize state
  - **Rejected**: Web GUI provides better visualization and is more intuitive

- **Desktop GUI** (Qt/Tkinter):
  - **Pros**: Native look and feel
  - **Cons**: Additional dependency, platform-specific, harder to deploy
  - **Rejected**: Web GUI works everywhere, no installation needed

- **WebSocket for Real-time**:
  - **Pros**: Lower latency, push updates instead of poll
  - **Cons**: More complex, overkill for 250ms polling
  - **Deferred**: May add in v2.0 if polling proves inadequate

**Implementation Details**:
- Use FastAPI's built-in `StaticFiles` to serve HTML
- Single-page application (SPA) with vanilla JavaScript (no framework)
- RESTful API endpoints for simulator control:
  - `GET /simulator/status` → JSON with position, temperature, is_moving, config
  - `POST /simulator/move` → `{"steps": N, "direction": "in"|"out"}` or `{"position": absolute}`
  - `POST /simulator/halt` → Stop movement immediately
- AJAX polling every 250ms (configurable)
- Embedded CSS (minimal framework, e.g., <100 lines custom styles)
- Responsive design with media queries

**Testing**:
- Unit tests: REST API endpoints return correct JSON
- Integration tests: Web GUI commands update simulator state
- Manual tests: Use GUI during Phase 2 (API layer development)

**Deployment**:
- Enabled only when `simulator.enabled=true` and `simulator.web_gui.enabled=true`
- Port configurable (default 8080), separate from Alpaca API (port 5000)
- Optional: Single-port mode with path prefix `/simulator/gui`

**Future Enhancements** (v2.0+):
- Error injection controls (inject timeout, checksum error)
- Movement speed adjustment slider
- Temperature drift/noise controls
- Movement history chart (last 100 moves)
- WebSocket streaming for sub-100ms updates

## Risks / Trade-offs

### Risk 1: Firmware Protocol Variations

**Risk**: Different Robofocus firmware versions may have incompatible protocols

**Likelihood**: Medium (observed FQ vs \r discrepancy)

**Impact**: High (driver non-functional for some users)

**Mitigation**:
1. Add firmware version detection via `FV` command response
2. Implement protocol adapters for known variants
3. Beta testing with multiple hardware versions
4. Document supported firmware in README

### Risk 2: Python GIL Performance

**Risk**: Global Interpreter Lock may bottleneck during high-frequency polling

**Likelihood**: Low (typical polling 100-250ms, well above GIL impact)

**Impact**: Medium (sluggish UI in NINA)

**Mitigation**:
1. Benchmark early in Phase 1 (simulator stress test)
2. If needed: Rewrite Layer 1 in Rust with Python bindings
3. Monitor CPU usage during field tests

### Risk 3: Serial Adapter Driver Issues

**Risk**: Some USB-to-serial chipsets have buggy Windows drivers (e.g., CH340)

**Likelihood**: Medium (known issue in community)

**Impact**: Medium (driver works but unreliable)

**Mitigation**:
1. Document recommended adapters (FTDI FT232)
2. Add diagnostic mode: log raw serial bytes
3. Implement reconnection logic on timeout

### Risk 4: Thread Safety Bug in isMoving Flag

**Risk**: Race condition if multiple clients call `/move` simultaneously

**Likelihood**: Low (typical usage: single NINA instance)

**Impact**: High (corrupted state, erratic movement)

**Mitigation**:
1. Make `is_moving` flag thread-safe (use `threading.Event`)
2. Add integration test: concurrent API calls from multiple threads
3. Log warning if move requested while already moving

## Migration Plan

### Phase 0: Pre-Release

1. Package Python code as wheel: `pip install robofocus-alpaca`
2. Alternative: PyInstaller standalone executable (`robofocus_alpaca.exe`)
3. Create Windows installer (optional): NSIS or WiX

### Phase 1: Alpha Testing

1. Select 3-5 users with different hardware/firmware
2. Provide installation instructions + config template
3. Collect logs from 24-hour imaging sessions
4. Iterate on bug fixes

### Phase 2: Beta Release

1. Publish on GitHub Releases
2. Announce on NINA Discord / CloudyNights forum
3. Document installation in NINA wiki
4. Monitor issue tracker for common problems

### Phase 3: Stable Release

1. Version 1.0.0 after 3+ successful field tests
2. Consider submission to ASCOM Alpaca device repository
3. Optional: Legacy COM driver deprecation notice

### Rollback Plan

If critical issues found:
1. Document workaround (downgrade to legacy COM driver)
2. Hotfix release within 48 hours
3. Post-mortem analysis, add regression test

## Open Questions

### Q1: Should we support multiple focuser instances?

**Context**: Some rigs have dual focuser setups (refractor + coma corrector)

**Current Decision**: Deferred to v2.0

**Rationale**: KISS principle, validate single-device first

### Q2: How to handle power loss position recovery?

**Context**: Robofocus has no absolute encoder, position lost on reboot

**Options**:
- A) Require manual homing routine (move to physical stop)
- B) Save position to file, restore on startup (risky if moved manually)
- C) Expose "Sync" command to set arbitrary position

**Current Decision**: Option C (ASCOM Alpaca supports sync method)

### Q3: Should we implement backlash compensation in driver or rely on NINA?

**Context**: Both driver (via FB command) and NINA can handle backlash

**Current Decision**: Expose hardware backlash (FB command) but default disabled, let NINA manage

**Rationale**: Gives user choice, avoids double-compensation

### Q4: Logging verbosity in production?

**Context**: DEBUG logs helpful but generate large files

**Current Decision**: INFO default, DEBUG enabled via config for troubleshooting

**Future**: Add log rotation (10MB max, 5 files)

## Implementation Notes

### Checksum Calculation

```python
def calculate_checksum(message: str) -> int:
    """
    Calculate Robofocus checksum (sum of ASCII values mod 256).

    Args:
        message: 8-character string (e.g., "FG002500")

    Returns:
        Checksum byte (0-255)
    """
    assert len(message) == 8
    return sum(ord(c) for c in message) % 256
```

### Command Encoding

```python
def encode_command(cmd: str, value: int) -> bytes:
    """
    Encode command as 9-byte packet.

    Args:
        cmd: Two-letter command (e.g., "FG")
        value: 6-digit integer (zero-padded)

    Returns:
        9 bytes: cmd + value + checksum
    """
    message = f"{cmd}{value:06d}"
    checksum = calculate_checksum(message)
    return message.encode('ascii') + bytes([checksum])
```

### Response Parsing

```python
def parse_response(packet: bytes) -> dict:
    """
    Parse 9-byte response packet.

    Args:
        packet: Raw bytes from serial port

    Returns:
        {"cmd": "FD", "value": 2500, "checksum_valid": True}

    Raises:
        ChecksumMismatchError: If checksum validation fails
    """
    if len(packet) != 9:
        raise ValueError(f"Expected 9 bytes, got {len(packet)}")

    message = packet[:8].decode('ascii')
    checksum_received = packet[8]
    checksum_calculated = calculate_checksum(message)

    if checksum_received != checksum_calculated:
        raise ChecksumMismatchError(
            f"Expected {checksum_calculated}, got {checksum_received}"
        )

    cmd = message[:2]
    value_str = message[2:8]

    return {
        "cmd": cmd,
        "value": int(value_str),
        "checksum_valid": True
    }
```

## Testing Strategy

### Unit Tests (pytest)

- Protocol encoding/decoding: `test_protocol.py`
- Checksum calculation: `test_checksum.py`
- Configuration validation: `test_config.py`
- Error mapping: `test_errors.py`

### Integration Tests

- API with simulator: `test_api_simulator.py`
  - Verify all endpoints return correct JSON envelope
  - Test discovery protocol (UDP)
  - Concurrent request handling (threading)

### Field Tests

- Real hardware: `field_test_checklist.md`
  - Connect/disconnect cycles (10x)
  - Full range movement (0 → MaxStep → 0)
  - Temperature reading accuracy (compare with external sensor)
  - Halt during movement (50% completion point)
  - 24-hour soak test (log all errors)

### Performance Benchmarks

- API latency: `benchmark_api.py`
  - Target: GET /position < 50ms (p99)
  - Target: PUT /move < 30ms (response time, not completion)

- Serial throughput: `benchmark_serial.py`
  - Measure commands/second (baseline)
  - Profile with cProfile if < 10 cmds/sec

## Future Enhancements (Post v1.0)

1. **Multi-device Support**: Multiple focusers on different COM ports
2. **REST API Extensions**: Backlash compensation endpoints
3. **WebSocket Streaming**: Real-time position updates (reduce polling)
4. **Windows Service**: Run as background service (no console window)
5. **GUI Config Tool**: Electron app for non-technical users
6. **Metrics Export**: Prometheus exporter for monitoring
7. **Firmware Upgrade**: Safe firmware flashing via driver (risky!)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-12
**Authors**: Samuele Vecchi, Claude Sonnet 4.5
