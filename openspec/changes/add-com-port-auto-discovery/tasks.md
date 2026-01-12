# Implementation Tasks: COM Port Auto-Discovery

## 1. Core Serial Protocol

- [x] 1.1 Create `protocol/robofocus_serial.py` implementing `SerialProtocolInterface`
- [x] 1.2 Implement `connect()` method with FV handshake validation
- [x] 1.3 Implement `disconnect()` method
- [x] 1.4 Implement `send_command()` with serial lock
- [x] 1.5 Implement `read_async_chars()` for movement tracking
- [x] 1.6 Add retry logic (3 attempts, 500ms delay)
- [x] 1.7 Add raw packet logging at DEBUG level

## 2. COM Port Enumeration

- [x] 2.1 Create `protocol/port_scanner.py` module
- [x] 2.2 Implement `list_available_ports()` using `serial.tools.list_ports`
- [x] 2.3 Return list of `PortInfo` objects with: name, description, hardware_id
- [x] 2.4 Filter out known non-serial ports (Bluetooth virtual, etc.)

## 3. Auto-Discovery Logic

- [x] 3.1 Implement `scan_for_robofocus()` function
- [x] 3.2 For each available port:
  - [x] 3.2.1 Open with 1-second timeout (fast scan)
  - [x] 3.2.2 Send FV command
  - [x] 3.2.3 Validate response checksum
  - [x] 3.2.4 If valid: mark as Robofocus, store firmware version
  - [x] 3.2.5 Close port
- [x] 3.3 Return list of discovered devices with port name + firmware version
- [x] 3.4 Handle exceptions gracefully (port busy, timeout, etc.)

## 4. Configuration Updates

- [x] 4.1 Add `serial.auto_discover: bool` config option (default: true)
- [x] 4.2 Add `serial.scan_timeout_seconds: float` config option (default: 1.0)
- [x] 4.3 Keep existing `serial.port` for manual override
- [x] 4.4 Update config.example.json with new options

## 5. API Endpoints

- [x] 5.1 Add `GET /api/v1/management/ports` endpoint
  - [x] Returns list of available COM ports
- [x] 5.2 Add `POST /api/v1/management/scan` endpoint
  - [x] Triggers Robofocus scan
  - [x] Returns discovered devices with firmware versions
- [x] 5.3 Add `PUT /api/v1/management/select-port` endpoint
  - [x] Allows runtime port selection

## 6. Integration

- [x] 6.1 Update `__main__.py` to use auto-discovery if enabled
- [x] 6.2 If multiple Robofocus found: use first one, log warning
- [x] 6.3 If no Robofocus found: log error, exit gracefully
- [x] 6.4 Store selected port in app state

## 7. Testing

- [ ] 7.1 Unit tests for port enumeration (mock serial.tools.list_ports)
- [ ] 7.2 Unit tests for scan logic (mock serial responses)
- [ ] 7.3 Integration test: scan with simulator
- [x] 7.4 Manual test with real hardware (if available)
