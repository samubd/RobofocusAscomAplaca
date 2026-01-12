# Change: Add COM Port Auto-Discovery

## Why

Users often don't know which COM port their Robofocus is connected to, especially on systems with multiple USB-serial devices. Currently, they must manually try each COM port until they find the correct one. This is error-prone and frustrating, particularly for less technical users.

## What Changes

- **ADDED**: Enumerate all available COM ports on the system
- **ADDED**: Auto-scan feature that probes each COM port with FV command to identify Robofocus devices
- **ADDED**: Display list of available COM ports with device descriptions
- **ADDED**: Mark discovered Robofocus devices with firmware version
- **ADDED**: API endpoint to trigger COM port scan
- **ADDED**: Configuration option for manual COM port selection (existing) vs auto-discovery

## Impact

- Affected specs: `serial-protocol`
- Affected code:
  - `robofocus_alpaca/protocol/robofocus_serial.py` (new file)
  - `robofocus_alpaca/api/routes.py` (new endpoint)
  - `robofocus_alpaca/config/models.py` (new config options)

## Benefits

1. **Better UX**: User clicks "Scan" and driver finds Robofocus automatically
2. **Reliability**: Positive identification via FV response + checksum validation
3. **Diagnostics**: Shows all available COM ports for troubleshooting
4. **Flexibility**: Still allows manual COM port override if needed
