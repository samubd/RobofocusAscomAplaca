# Implementation Tasks: Robofocus ASCOM Alpaca Driver

## Implementation Status Summary

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 0: Project Setup | ✅ Complete | Repository, config, logging |
| Phase 1: Simulator | ✅ Complete | MockSerialProtocol, Web GUI, Protocol Logs |
| Phase 2: HTTP API | ✅ Complete | FastAPI, IFocuserV3, UDP Discovery, Management API |
| Phase 3: NINA Integration | 🔄 Partial | Basic integration tested, autofocus pending |
| Phase 4: Serial Protocol | ✅ Complete | RobofocusSerial, port scanner, retry logic |
| Phase 5: Hardware Integration | 🔄 Partial | Configuration ready, hardware testing pending |
| Phase 6: Field Testing | ⏳ Pending | Requires real telescope setup |
| Phase 7: Packaging | ⏳ Pending | PyInstaller, documentation |
| Phase 8: Maintenance | 🔄 Ongoing | Advanced features implemented |

**Last Updated:** 2026-01-12

---

## Development Approach: Top-Down

This implementation follows a **top-down strategy**:
1. Build HTTP API layer first with simulator backend
2. Validate API contract with real astronomy client (NINA)
3. Implement serial protocol handler
4. Replace simulator with real hardware
5. Field testing

This approach enables early integration testing and parallel development of API and protocol layers.

---

## Phase 0: Project Setup

### 0.1 Repository and Environment
- [x] 0.1.1 Initialize Python project structure
  - [x] Create directory structure: `robofocus_alpaca/{api,protocol,focuser,simulator,config,utils}`
  - [x] Create `__init__.py` files in each package
  - [x] Create `pyproject.toml` with dependencies (FastAPI, uvicorn, pyserial, pydantic, pytest)
  - [x] Create `requirements.txt` from pyproject.toml

- [x] 0.1.2 Setup version control and CI
  - [x] Initialize git (if not already)
  - [x] Create `.gitignore` (Python, __pycache__, .venv, *.log, config.json)
  - [ ] Create GitHub Actions workflow: `.github/workflows/ci.yml` (pytest, black, pylint)

- [x] 0.1.3 Setup development environment
  - [x] Create virtual environment: `python -m venv .venv`
  - [x] Install dependencies: `pip install -r requirements.txt`
  - [x] Install dev dependencies: `pip install pytest black pylint mypy`
  - [ ] Configure Black formatter (line-length=100)
  - [ ] Configure pylint (pylintrc file)

### 0.2 Configuration System
- [x] 0.2.1 Create Pydantic configuration models
  - [x] Create `config/models.py`:
    - [x] `ServerConfig` (ip, port, discovery_enabled)
    - [x] `SerialConfig` (port, baud, timeout_seconds)
    - [x] `FocuserConfig` (step_size_microns, max_step, min_step, polling intervals)
    - [x] `LoggingConfig` (level, file)
    - [x] `SimulatorConfig` (enabled, initial_position, movement_speed, temperature, latency, error injection)
    - [x] `AppConfig` (root model combining all above)
    - [x] `UserSettings` (last_port, max_increment, min_step) - **ADDED**

- [x] 0.2.2 Create configuration loader
  - [x] Create `config/loader.py`:
    - [x] `load_config(path: str) -> AppConfig` function
    - [x] Handle missing file (use defaults)
    - [x] Handle malformed JSON (raise ConfigurationError with helpful message)
    - [x] Validate config with Pydantic
  - [x] Create `config/user_settings.py` - **ADDED**:
    - [x] `UserSettingsManager` class for persistent user preferences
    - [x] Auto-save on change

- [x] 0.2.3 Create default configuration template
  - [x] Create `config.example.json` with documented defaults
  - [ ] Document each parameter with inline comments (JSON5 style as guide)

### 0.3 Logging Setup
- [x] 0.3.1 Configure Python logging
  - [x] Create `utils/logging_setup.py`:
    - [x] `setup_logging(config: LoggingConfig)` function
    - [ ] Console handler with colored output (using colorlog if available)
    - [x] File handler with rotation (RotatingFileHandler, 10MB max, 5 backups)
    - [x] Structured log format: `[timestamp] LEVEL: message`

- [x] 0.3.2 Create logger instances
  - [x] Global logger for each module (api, protocol, focuser, simulator)

---

## Phase 1: Hardware Simulator Implementation

### 1.1 Protocol Interface Definition
- [x] 1.1.1 Create abstract interface
  - [x] Create `protocol/interface.py`:
    - [x] `SerialProtocolInterface` abstract base class
    - [x] Methods: `send_command(cmd: str) -> str`, `connect()`, `disconnect()`, `is_connected() -> bool`
    - [x] Method: `read_async_chars() -> List[str]` for 'I'/'O'/'F' during movement
    - [x] Methods: `get_backlash()`, `set_backlash()` - **ADDED**
    - [x] Methods: `get_max_travel()`, `set_max_travel()` - **ADDED**

### 1.2 Simulator Core
- [x] 1.2.1 Create simulator class structure
  - [x] Create `simulator/mock_serial.py`:
    - [x] `MockSerialProtocol` class implementing `SerialProtocolInterface`
    - [x] Constructor: accept `SimulatorConfig`
    - [x] Internal state: position, is_moving, target_position, firmware_version, backlash, max_limit, motor_config, switch_states

- [x] 1.2.2 Implement command parsing
  - [x] `_parse_command(packet: bytes) -> Tuple[str, int]` method
    - [x] Extract command (first 2 bytes)
    - [x] Extract value (6 ASCII digits)
    - [x] Validate checksum
    - [x] Return (cmd, value) or raise `ChecksumMismatchError`

- [x] 1.2.3 Implement checksum utilities
  - [x] Create `protocol/checksum.py`:
    - [x] `calculate_checksum(message: str) -> int` function
    - [x] `validate_checksum(packet: bytes) -> bool` function

- [x] 1.2.4 Implement command encoder
  - [x] Create `protocol/encoder.py`:
    - [x] `encode_command(cmd: str, value: int) -> bytes` function
    - [x] Zero-pad value to 6 digits
    - [x] Append checksum
    - [x] Return 9 bytes

### 1.3 Simulator Command Handlers
- [x] 1.3.1 Implement FV (Get Version)
  - [x] `_handle_fv() -> bytes` method
    - [x] Return `FV` + firmware_version + checksum

- [x] 1.3.2 Implement FG/FD (Position)
  - [x] `_handle_fg(value: int) -> bytes` method
    - [x] If value == 0: query mode, return current position as `FD` packet
    - [x] Else: movement mode, start background movement, return immediate `FD` with target

- [x] 1.3.3 Implement movement simulation
  - [x] `_start_movement(target: int)` method
    - [x] Cancel previous movement if active
    - [x] Calculate duration: `abs(target - position) / movement_speed`
    - [x] Spawn thread: `threading.Thread(target=self._simulate_movement, args=(target,))`
  - [x] `_simulate_movement(target: int)` method
    - [x] Loop: while position != target
      - [x] Increment/decrement position
      - [x] Queue 'I'/'O' character for async reading
      - [x] Sleep proportional to speed
    - [x] Queue 'F' + final `FD` packet
    - [x] Set is_moving = False

- [x] 1.3.4 Implement FT (Temperature)
  - [x] `_handle_ft() -> bytes` method
    - [x] Get current simulated temperature (with noise/drift if configured)
    - [x] Convert Celsius to raw ADC: `int((celsius + 273.15) * 2)`
    - [x] Return `FT` + raw value + checksum

- [x] 1.3.5 Implement FQ (Halt)
  - [x] `_handle_fq() -> bytes` method
    - [x] Cancel movement thread
    - [x] Queue 'F' + current position packet
    - [x] Set is_moving = False

- [x] 1.3.6 Implement FB (Backlash)
  - [x] `_handle_fb(value: int) -> bytes` method
    - [x] Parse mode from value (digit 1)
    - [x] Parse amount from value (digits 4-6)
    - [x] Store or query backlash config
    - [x] Return echo packet

- [x] 1.3.7 Implement FL (Max Limit)
  - [x] `_handle_fl(value: int) -> bytes` method
    - [x] If value == 0: query mode, return current max_limit
    - [x] Else: set max_limit
    - [x] Return echo packet

- [x] 1.3.8 Implement FC (Motor Config)
  - [x] `_handle_fc(value: int) -> bytes` method
    - [x] Parse duty/delay/ticks from value digits
    - [x] Store or query motor_config
    - [x] Return echo packet

- [x] 1.3.9 Implement FP (Power Switches)
  - [x] `_handle_fp(value: int) -> bytes` method
    - [x] If value == 0: query mode, return switch states
    - [x] Else: toggle switch (extract switch number from value)
    - [x] Return `FP` + switch states + checksum

- [x] 1.3.10 Implement FS (Sync Position)
  - [x] `_handle_fs(value: int) -> bytes` method
    - [x] Set position = value (no movement)
    - [x] Return no response or acknowledgment (check real hardware behavior)

### 1.4 Simulator Testing
- [ ] 1.4.1 Write unit tests for simulator
  - [ ] Create `tests/test_simulator.py`:
    - [ ] Test FV command
    - [ ] Test FG movement (verify 'I'/'O'/'F' characters)
    - [ ] Test FG query
    - [ ] Test FT temperature
    - [ ] Test FQ halt
    - [ ] Test FL, FB, FC, FP, FS commands
    - [ ] Test checksum validation (valid and invalid)
    - [ ] Test concurrent position queries
    - [ ] Test movement cancellation

- [ ] 1.4.2 Test error injection
  - [ ] Test timeout injection
  - [ ] Test checksum error injection
  - [ ] Test disconnect injection

### 1.5 Protocol Logging - **ADDED**
- [x] 1.5.1 Create protocol logger
  - [x] Create `protocol/logger.py`:
    - [x] `ProtocolMessage` dataclass (timestamp, direction, raw_hex, raw_bytes, decoded, error)
    - [x] `ProtocolLogger` class with circular buffer (max 500 messages)
    - [x] Thread-safe with `threading.Lock`
    - [x] Methods: `log_tx()`, `log_rx()`, `log_error()`, `get_messages()`, `get_stats()`, `clear()`
    - [x] Command decoding with descriptions
    - [x] Global instance via `get_protocol_logger()`

- [x] 1.5.2 Integrate logging into protocols
  - [x] Add logging to `RobofocusSerial._send_command_internal()`
  - [x] Add logging to `MockSerialProtocol` commands
  - [x] Log TX with command and value
  - [x] Log RX with decoded response and checksum validation

- [x] 1.5.3 Create protocol logs API endpoints
  - [x] `GET /gui/logs` - retrieve messages with limit/offset
  - [x] `POST /gui/logs/clear` - clear all logs
  - [x] `PUT /gui/logs/enabled` - enable/disable logging

- [x] 1.5.4 Create protocol logs viewer page
  - [x] Create `static/logs.html`:
    - [x] Table with Timestamp, Direction, Raw Hex, Decoded columns
    - [x] Color-coded direction (TX=green, RX=blue, ERR=red)
    - [x] Color-coded byte view (Header=blue, Command=purple, Value=green, Checksum=red)
    - [x] Statistics display (TX count, RX count, errors, total)
    - [x] Auto-refresh checkbox (1 second interval)
    - [x] Auto-scroll checkbox (newest at bottom)
    - [x] Clear logs button
    - [x] Navigation links to Control Panel and Setup

### 1.6 Web GUI Implementation

- [x] 1.6.1 Create GUI API endpoints
  - [x] Create `api/gui_api.py`:
    - [x] `GET /gui/status` endpoint - returns position, target, is_moving, temperature, firmware, max_step, connected, mode
    - [x] `GET /gui/ports` endpoint - list available COM ports
    - [x] `POST /gui/scan` endpoint - scan for Robofocus devices
    - [x] `POST /gui/connect` endpoint - connect to specified port
    - [x] `POST /gui/disconnect` endpoint - disconnect
    - [x] `POST /gui/move` endpoint - relative or absolute movement
    - [x] `POST /gui/halt` endpoint - stop movement
    - [x] `POST /gui/set-zero` endpoint - set current position as zero
    - [x] `POST /gui/set-max` endpoint - set max travel (saves to hardware)
    - [x] `POST /gui/set-min` endpoint - set min limit (saves to user_settings)
    - [x] `POST /gui/set-max-increment` endpoint - set max increment (saves to user_settings)
    - [x] `POST /gui/set-backlash` endpoint - set backlash (saves to hardware)

- [x] 1.6.2 Create HTML control panel
  - [x] Create `static/index.html`:
    - [x] Status Display: Position, Temperature, Firmware, Connection status
    - [x] Movement Controls: IN/OUT buttons with step sizes (1, 10, 100, 1000)
    - [x] Absolute Position: GoTo input and button
    - [x] Emergency HALT button
    - [x] Calibration section: Set Zero, Set Min, Set Max, Set Max Increment, Set Backlash
    - [x] Configuration Display: All current parameters
    - [x] Navigation links to Setup and Protocol Logs pages

- [x] 1.6.3 Add embedded CSS styling
  - [x] Dark theme with professional astronomy software appearance
  - [x] Responsive layout
  - [x] Color-coded status indicators

- [x] 1.6.4 Add JavaScript functionality
  - [x] Auto-polling status (1 second interval)
  - [x] All button event handlers
  - [x] Input validation
  - [x] Error display

- [x] 1.6.5 Create ASCOM Setup page
  - [x] Create setup page at `/setup/v1/focuser/0/setup`
  - [x] Display current mode, connection status, COM port, firmware
  - [x] COM port selection with Scan/Connect/Disconnect buttons
  - [x] Accessible from NINA gear icon

- [ ] 1.6.6 Write integration tests for web GUI
  - [ ] Create `tests/test_web_gui.py`:
    - [ ] Use FastAPI TestClient
    - [ ] Test all GUI endpoints

---

## Phase 2: HTTP API Layer (Alpaca Server)

### 2.1 FastAPI Application Setup
- [x] 2.1.1 Create FastAPI app
  - [x] Create `api/app.py`:
    - [x] `create_app(config: AppConfig) -> FastAPI` factory function
    - [x] Enable CORS middleware
    - [x] Add exception handlers (catch-all for DriverError)

- [x] 2.1.2 Create response models
  - [x] Create `api/models.py`:
    - [x] `AlpacaResponse` Pydantic model (Value, ClientTransactionID, ServerTransactionID, ErrorNumber, ErrorMessage)
    - [x] Helper function: `make_response(value: Any, client_id: int = 0, error: Optional[Exception] = None) -> AlpacaResponse`

- [x] 2.1.3 Create transaction ID counter
  - [x] Thread-safe global counter

### 2.2 Focuser State Machine (Layer 2)
- [x] 2.2.1 Create focuser controller
  - [x] Create `focuser/controller.py`:
    - [x] `FocuserController` class
    - [x] Constructor: accept `protocol: SerialProtocolInterface`, `config: FocuserConfig`
    - [x] Properties: position, is_moving, temperature, connected
    - [x] Methods: connect(), disconnect(), move(target), halt()

- [x] 2.2.2 Implement position caching
  - [x] `_cached_position: int` attribute
  - [x] `_last_position_update: datetime` attribute
  - [x] `get_position() -> int` method

- [x] 2.2.3 Implement movement tracking
  - [x] `move(target: int)` method with limit clamping
  - [x] Background movement monitoring with position tracking

- [x] 2.2.4 Implement halt
  - [x] `halt()` method - sends FQ command

- [x] 2.2.5 Implement temperature reading
  - [x] `get_temperature() -> float` method with LM335 conversion

### 2.3 API Endpoints
- [x] 2.3.1 Create router
  - [x] Create `api/routes.py`:
    - [x] `router = APIRouter(prefix="/api/v1/focuser/0")`
    - [x] Dependency injection for focuser controller

- [x] 2.3.2 Implement common endpoints
  - [x] `GET /connected`: return connected status
  - [x] `PUT /connected`: accept Connected=true/false
  - [x] `GET /position`: return current position
  - [x] `PUT /move`: accept Position=int (non-blocking)
  - [x] `GET /ismoving`: return movement status
  - [x] `PUT /halt`: stop movement
  - [x] `GET /temperature`: return converted temperature

- [x] 2.3.3 Implement property endpoints
  - [x] `GET /absolute`: return True
  - [x] `GET /maxstep`: return max_step (from hardware)
  - [x] `GET /maxincrement`: return max_increment (from config)
  - [x] `GET /stepsize`: return step_size_microns
  - [x] `GET /tempcomp`: return False
  - [x] `GET /tempcompavailable`: return False

- [x] 2.3.4 Implement metadata endpoints
  - [x] `GET /interfaceversion`: return 3 (IFocuserV3)
  - [x] `GET /driverversion`: return version string
  - [x] `GET /driverinfo`: return driver description
  - [x] `GET /description`: return device description
  - [x] `GET /name`: return "Robofocus"
  - [x] `GET /supportedactions`: return []

- [x] 2.3.5 Implement IFocuserV3 backlash endpoints - **ADDED**
  - [x] `GET /backlash`: return current backlash (signed: +OUT, -IN)
  - [x] `PUT /backlash`: set backlash (persists to hardware via FB command)

### 2.4 UDP Discovery
- [x] 2.4.1 Create discovery server
  - [x] Create `api/discovery.py`:
    - [x] `DiscoveryServer` class
    - [x] Listen on UDP port 32227
    - [x] Respond to "alpacadiscovery1" with JSON: `{"AlpacaPort": <http_port>}`
    - [x] Run in background thread

- [x] 2.4.2 Integrate discovery with app
  - [x] Start discovery server when HTTP server starts
  - [x] Stop discovery when server stops

### 2.5 Error Handling
- [x] 2.5.1 Create exception classes
  - [x] Create `utils/exceptions.py`:
    - [x] `RobofocusException` base class
    - [x] `NotConnectedError` (ErrorNumber 1031)
    - [x] `DriverError` (ErrorNumber 1280)
    - [x] `InvalidValueError` (ErrorNumber 1026)
    - [x] `ProtocolError` (ErrorNumber 1280)
    - [x] `SerialTimeoutError` (ErrorNumber 1280)
    - [x] `ChecksumMismatchError` (ErrorNumber 1280)

- [x] 2.5.2 Error handling in responses
  - [x] Map exceptions to Alpaca ErrorNumber and ErrorMessage
  - [x] Return proper JSON error responses

### 2.6 Management API - **ADDED**
- [x] 2.6.1 Create management endpoints
  - [x] `GET /management/apiversions`: return [1]
  - [x] `GET /management/v1/configureddevices`: return device list
  - [x] `GET /management/v1/description`: return server description

### 2.7 API Testing
- [ ] 2.7.1 Write integration tests with simulator
  - [ ] Create `tests/test_api.py`

- [ ] 2.7.2 Test discovery protocol
  - [ ] Create `tests/test_discovery.py`

---

## Phase 3: NINA Integration Testing

### 3.1 Local Testing
- [x] 3.1.1 Start driver with simulator
  - [x] Run: `python -m robofocus_alpaca` entry point implemented
  - [x] HTTP server starts on configurable port (default 5000)
  - [x] Discovery server active on UDP 32227
  - [x] Startup logging implemented

- [x] 3.1.2 Configure NINA
  - [x] NINA Equipment Manager compatible
  - [x] Alpaca Discovery working
  - [x] "Robofocus" appears in device list
  - [x] Setup page accessible from gear icon

- [ ] 3.1.3 Manual operation tests in NINA
  - [ ] Full NINA workflow testing
  - [ ] Position updates during movement
  - [ ] Temperature reading validation

- [ ] 3.1.4 Autofocus routine test
  - [ ] V-curve autofocus testing
  - [ ] Multiple move commands
  - [ ] Optimal position convergence

### 3.2 Debugging and Refinement
- [x] 3.2.1 Monitor API logs
  - [x] Protocol Logs page implemented
  - [x] TX/RX message logging
  - [x] Real-time monitoring

- [ ] 3.2.2 Performance tuning
  - [ ] Response latency measurement
  - [ ] Performance optimization if needed

- [ ] 3.2.3 Fix any issues
  - [ ] Address compatibility issues as discovered

---

## Phase 4: Serial Protocol Implementation

### 4.1 Real Serial Protocol Handler
- [x] 4.1.1 Create serial class
  - [x] Create `protocol/robofocus_serial.py`:
    - [x] `RobofocusSerial` class implementing `SerialProtocolInterface`
    - [x] Constructor: accept `SerialConfig`
    - [x] Use pyserial: `import serial`

- [x] 4.1.2 Implement connect/disconnect
  - [x] `connect()` method:
    - [x] Open serial port: `serial.Serial(port, baud, timeout=timeout_seconds)`
    - [x] Configure: 8N1, no flow control
    - [x] Send FV handshake command
    - [x] Validate response (firmware version)
    - [x] Store firmware version for diagnostics
    - [x] Query max travel (FL command) on connect
    - [x] Query backlash (FB command) on connect
  - [x] `disconnect()` method:
    - [x] Close serial port
    - [x] Set connected flag to False

- [x] 4.1.3 Implement command sending
  - [x] `_send_command_internal(cmd: str, value: int) -> bytes` method:
    - [x] Acquire serial lock
    - [x] Flush input/output buffers
    - [x] Encode command with checksum
    - [x] Write 9 bytes to serial port
    - [x] Read 9 bytes response
    - [x] Validate checksum
    - [x] Release lock
    - [x] Protocol logging integration
    - [x] Return response packet

- [x] 4.1.4 Implement async character reading
  - [x] `read_async_chars() -> List[str]` method:
    - [x] Check if bytes available (non-blocking)
    - [x] Read available single bytes
    - [x] Return list of 'I', 'O', or 'F' characters

- [x] 4.1.5 Implement timeout handling
  - [x] Serial timeout configuration
  - [x] Raise `SerialTimeoutError` on timeout

- [x] 4.1.6 Implement retry logic
  - [x] `_send_with_retry(cmd, value, max_attempts=3) -> bytes` method
  - [x] Retry on timeout or checksum error
  - [x] Logging for retry attempts

### 4.2 COM Port Discovery - **ADDED**
- [x] 4.2.1 Create port scanner
  - [x] Create `protocol/port_scanner.py`:
    - [x] `scan_ports()` - list available COM ports
    - [x] `find_robofocus()` - scan and find Robofocus devices
    - [x] FV handshake validation for each port
    - [x] Configurable timeout

### 4.3 Serial Protocol Testing
- [ ] 4.3.1 Write unit tests with mock serial port
  - [ ] Create `tests/test_serial_protocol.py`

- [ ] 4.3.2 Manual testing with hardware
  - [ ] Verify all commands with real hardware

---

## Phase 5: Hardware Integration

### 5.1 Switch from Simulator to Real Hardware
- [x] 5.1.1 Configuration system ready
  - [x] `config.json` supports `simulator.enabled=false`
  - [x] `serial.port` configurable
  - [x] Auto-discovery as fallback

- [ ] 5.1.2 Test basic connectivity
  - [ ] Start driver with real hardware
  - [ ] Verify serial port opens successfully
  - [ ] Verify FV handshake succeeds
  - [ ] Check firmware version in logs

- [ ] 5.1.3 Test movements
  - [ ] Physical movement verification
  - [ ] Position tracking accuracy
  - [ ] Halt during movement

### 5.2 Calibration and Tuning
- [x] 5.2.1 Calibration features implemented
  - [x] Set Zero position via GUI
  - [x] Set Max via GUI (saves to hardware FL command)
  - [x] Set Min via GUI (saves to user_settings)
  - [x] Step size configurable

- [ ] 5.2.2 Hardware calibration
  - [ ] Determine physical step size
  - [ ] Set travel limits on real hardware
  - [ ] Temperature sensor calibration

### 5.3 Stress Testing
- [ ] 5.3.1 Long movement cycles
- [ ] 5.3.2 Rapid position queries
- [ ] 5.3.3 24-hour soak test

---

## Phase 6: Field Testing

### 6.1 Telescope Integration
- [ ] 6.1.1 Install on imaging rig
  - [ ] Deploy driver on Windows imaging PC
  - [ ] Configure COM port for Robofocus
  - [ ] Start driver as background process or service

- [ ] 6.1.2 Connect NINA
  - [ ] Open NINA, connect to Alpaca driver
  - [ ] Verify connection stable during imaging session

- [ ] 6.1.3 Full imaging sequence test
  - [ ] Start NINA sequence:
    - [ ] Slew to target
    - [ ] Autofocus
    - [ ] Take exposures (10-20 images)
    - [ ] Refocus every 1 hour
  - [ ] Verify autofocus succeeds each time
  - [ ] Verify no connection drops
  - [ ] Check image quality (focus sharp)

### 6.2 Multi-Night Testing
- [ ] 6.2.1 Run for 3 consecutive nights
  - [ ] 4-8 hour sessions each night
  - [ ] Different targets and sequences
  - [ ] Collect logs from each night

- [ ] 6.2.2 Analyze logs
  - [ ] Count total API requests
  - [ ] Count errors/retries
  - [ ] Measure average response times
  - [ ] Identify any issues or warnings

- [ ] 6.2.3 User feedback
  - [ ] Ask alpha testers for subjective experience
  - [ ] Identify usability issues
  - [ ] Collect feature requests

---

## Phase 7: Packaging and Deployment

### 7.1 Standalone Executable
- [ ] 7.1.1 Create PyInstaller spec
  - [ ] Write `robofocus_alpaca.spec`
  - [ ] Include all dependencies (FastAPI, uvicorn, pyserial)
  - [ ] Embed default config.example.json
  - [ ] Set icon (telescope/focuser icon)

- [ ] 7.1.2 Build executable
  - [ ] Run: `pyinstaller robofocus_alpaca.spec`
  - [ ] Test on clean Windows VM (no Python installed)
  - [ ] Verify executable runs and serves API

### 7.2 Documentation
- [ ] 7.2.1 Write user manual
  - [ ] Create `docs/USER_GUIDE.md`:
    - [ ] Installation instructions
    - [ ] Configuration guide
    - [ ] NINA setup steps
    - [ ] Troubleshooting section

- [ ] 7.2.2 Write developer documentation
  - [ ] Create `docs/DEVELOPER.md`:
    - [ ] Architecture overview
    - [ ] How to run tests
    - [ ] How to add new commands
    - [ ] Protocol reference

- [ ] 7.2.3 Update README
  - [ ] Project description
  - [ ] Quick start guide
  - [ ] Features list
  - [ ] Links to docs

### 7.3 Release
- [ ] 7.3.1 Create GitHub release
  - [ ] Tag version: `v1.0.0`
  - [ ] Write release notes
  - [ ] Attach standalone executable (.exe)
  - [ ] Attach config.example.json

- [ ] 7.3.2 Publish to PyPI (optional)
  - [ ] Create PyPI account
  - [ ] Build wheel: `python -m build`
  - [ ] Upload: `twine upload dist/*`

- [ ] 7.3.3 Announce release
  - [ ] Post on NINA Discord
  - [ ] Post on CloudyNights forum
  - [ ] Update ASCOM Alpaca device list (if applicable)

---

## Phase 8: Maintenance and Future Work

### 8.1 Bug Fixes
- [ ] 8.1.1 Monitor issue tracker
- [ ] 8.1.2 Release hotfixes

### 8.2 Feature Enhancements
- [x] 8.2.1 Implemented advanced features
  - [x] Backlash compensation endpoints (IFocuserV3 GET/PUT /backlash)
  - [x] FB command integration with hardware persistence
  - [x] FL command for max travel with hardware persistence
  - [x] User settings persistence (max_increment, min_step, last_port)
  - [x] Protocol logging for debugging
  - [ ] Motor configuration endpoints (FC command) - simulator only
  - [ ] Power switch control (FP command) - simulator only
  - [ ] Multi-device support (multiple COM ports)

- [ ] 8.2.2 Performance optimizations
  - [ ] Profile with cProfile
  - [ ] Optimize hot paths if needed

### 8.3 Compatibility
- [ ] 8.3.1 Test with other clients
  - [ ] Voyager Advanced
  - [ ] Sequence Generator Pro (SGP)
  - [ ] PHD2 guiding (if applicable)

- [ ] 8.3.2 Test on other platforms
  - [ ] Linux (Ubuntu/Debian)
  - [ ] macOS (if hardware adapter available)

---

## Definition of Done

Each task is considered complete when:
- Code is written and passes unit tests
- Code follows PEP 8 and passes pylint
- Type hints added and mypy validation passes
- Functionality tested manually (if applicable)
- Logs and error messages are clear and helpful
- Documentation updated (inline comments, docstrings)

**Overall project is complete when:**
- All tasks marked `[x]`
- Full imaging session with NINA succeeds
- 24-hour soak test passes with zero crashes
- User documentation published
- v1.0.0 release created on GitHub
