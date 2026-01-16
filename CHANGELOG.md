# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2025-01-16

### Added
- **Auto-Create Config Files** - `config.json` and `user_settings.json` are created automatically on first startup with sensible defaults, making setup easier for non-technical users

### Fixed
- **Simulator Mode from config.json** - The `simulator.enabled` setting in `config.json` is now respected when user hasn't explicitly set a preference via the GUI. Previously, the server would always try to connect to hardware even with `simulator.enabled: true`

---

## [1.0.0] - 2025-01-15

### Added
- **ASCOM Alpaca API v1** - Full compliance with the ASCOM Alpaca standard
- **Real Hardware Support** - Direct RS-232 serial communication with Robofocus devices
- **Hardware Simulator** - Built-in virtual focuser for testing without hardware
- **Hot-Swappable Modes** - Switch between hardware and simulator via web GUI
- **UDP Discovery** - Automatic detection in NINA and other ASCOM clients (port 32227)
- **Web Control Panel** - Modern, responsive web interface for manual control
- **Backlash Compensation** - INDI convention support (signed values: +OUT, -IN)
- **Temperature Monitoring** - Read focuser temperature sensor
- **Auto-Discovery** - Automatically scan and detect Robofocus devices on COM ports
- **Persistent Settings** - User preferences saved to `user_settings.json`
- **Config Auto-Save** - Hardware settings (firmware, max travel, backlash) saved on connection
- **Movement Monitoring** - Real-time position tracking with intelligent caching
- **Protocol Logging** - Detailed communication logs for debugging
- **High COM Port Support** - Works with COM10+, COM12+, etc.
- **Thread-Safe Operations** - Concurrent API requests handled correctly
- **Windows Installer** - Professional installer with firewall configuration
- **Portable Executable** - Standalone exe that runs without Python

### Fixed
- **Backlash Query Caching** - Prevents movement interruption during NINA polling
- **Hardware Settling Time** - 150ms delay prevents position query timeout after movement

### Technical Details
- Built with FastAPI and Uvicorn
- Pydantic for data validation
- PySerial for serial communication
- PyInstaller for Windows executable
- Inno Setup for Windows installer

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 1.0.1 | 2025-01-16 | Auto-create config files, fix simulator mode |
| 1.0.0 | 2025-01-15 | Initial public release |

[1.0.1]: https://github.com/samubd/RobofocusAscomAplaca/releases/tag/v1.0.1
[1.0.0]: https://github.com/samubd/RobofocusAscomAplaca/releases/tag/v1.0.0
