#!/usr/bin/env python
"""
Build script for creating Windows executable of Robofocus ASCOM Alpaca Driver.

Usage:
    python build.py [--sign]

Options:
    --sign    Sign the executable with a code signing certificate
              Requires signtool.exe and CODESIGN_CERT environment variable

This script will:
1. Clean previous build artifacts
2. Run PyInstaller to create the executable
3. Copy default configuration files to the dist folder
4. Optionally sign the executable (if --sign is provided)
"""

import os
import shutil
import subprocess
import sys
import argparse

def clean_build():
    """Remove previous build artifacts."""
    print("Cleaning previous build artifacts...")

    dirs_to_remove = ['build', 'dist']
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            print(f"  Removing {dir_name}/")
            shutil.rmtree(dir_name)

    print("[OK] Clean complete\n")

def run_pyinstaller():
    """Run PyInstaller with the spec file."""
    print("Running PyInstaller...")

    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', 'robofocus_alpaca.spec', '--clean'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("[ERROR] PyInstaller failed!")
        print(result.stderr)
        print(result.stdout)
        sys.exit(1)

    print("[OK] PyInstaller complete\n")

def copy_config_files():
    """Copy default configuration files to dist folder."""
    print("Copying configuration files...")

    dist_dir = os.path.join('dist', 'RobofocusAlpaca')

    # Create config.json example
    config_example = os.path.join(dist_dir, 'config.json.example')
    config_content = """{
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
}"""

    with open(config_example, 'w') as f:
        f.write(config_content)

    print(f"  Created {config_example}")

    # Create README.txt for the distribution
    readme_content = """Robofocus ASCOM Alpaca Driver
==============================

Installation:
1. Extract all files to a folder (e.g., C:\\Program Files\\RobofocusAlpaca)
2. (Optional) Copy config.json.example to config.json and customize settings
3. Run RobofocusAlpaca.exe

Usage:
1. Double-click RobofocusAlpaca.exe to start the driver
2. A console window will open showing the server status
3. Open your browser to http://localhost:5000/ to access the control panel
4. In NINA, use Alpaca Discovery or connect to http://localhost:5000
5. Configure the driver in the Settings page (Hardware or Simulator mode)
6. Click Connect in NINA to start using the focuser

Configuration:
- Settings are saved in user_settings.json (auto-created on first run)
- Advanced configuration can be done in config.json
- Logs are written to robofocus_alpaca.log

Default URLs:
- Control Panel: http://localhost:5000/
- Settings Page: http://localhost:5000/setup/v1/focuser/0/setup
- Protocol Logs: http://localhost:5000/logs.html

Troubleshooting:
- Check robofocus_alpaca.log for error messages
- Ensure no other application is using port 5000
- For COM port issues, use the Scan button in Settings
- Allow UDP port 32227 in Windows Firewall for NINA discovery

For more information, visit: https://github.com/samubd/RobofocusAscomAplaca
"""

    readme_path = os.path.join(dist_dir, 'README.txt')
    with open(readme_path, 'w') as f:
        f.write(readme_content)

    print(f"  Created {readme_path}")
    print("[OK] Configuration files copied\n")

def sign_executable():
    """
    Sign the executable with a code signing certificate.

    Requires:
    - signtool.exe (from Windows SDK)
    - CODESIGN_CERT environment variable pointing to .pfx file
    - CODESIGN_PASSWORD environment variable (optional, for password-protected certs)
    """
    print("Signing executable...")

    cert_path = os.environ.get('CODESIGN_CERT')
    if not cert_path:
        print("[ERROR] CODESIGN_CERT environment variable not set!")
        print("  Set it to the path of your .pfx certificate file")
        return False

    if not os.path.exists(cert_path):
        print(f"[ERROR] Certificate file not found: {cert_path}")
        return False

    exe_path = os.path.join('dist', 'RobofocusAlpaca', 'RobofocusAlpaca.exe')
    if not os.path.exists(exe_path):
        print(f"[ERROR] Executable not found: {exe_path}")
        return False

    # Build signtool command
    cmd = [
        'signtool', 'sign',
        '/f', cert_path,
        '/t', 'http://timestamp.digicert.com',  # Timestamp server
        '/fd', 'SHA256',
        '/d', 'Robofocus ASCOM Alpaca Driver',
    ]

    # Add password if provided
    password = os.environ.get('CODESIGN_PASSWORD')
    if password:
        cmd.extend(['/p', password])

    cmd.append(exe_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[ERROR] Signing failed: {result.stderr}")
            return False
        print("[OK] Executable signed successfully\n")
        return True
    except FileNotFoundError:
        print("[ERROR] signtool.exe not found!")
        print("  Install Windows SDK or add signtool to PATH")
        return False

def main():
    """Main build process."""
    parser = argparse.ArgumentParser(description='Build Robofocus ASCOM Alpaca Driver')
    parser.add_argument('--sign', action='store_true',
                        help='Sign the executable with a code signing certificate')
    args = parser.parse_args()

    print("=" * 60)
    print("Robofocus ASCOM Alpaca Driver - Build Script")
    print("=" * 60)
    print()

    # Check if PyInstaller is installed
    try:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--version'],
                       capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERROR] PyInstaller is not installed!")
        print("  Install it with: pip install pyinstaller")
        sys.exit(1)

    clean_build()
    run_pyinstaller()
    copy_config_files()

    # Sign if requested
    if args.sign:
        if not sign_executable():
            print("[WARN] Build completed but signing failed")
            sys.exit(1)

    print("=" * 60)
    print("[OK] Build complete!")
    print("=" * 60)
    print()
    print(f"Executable location: dist\\RobofocusAlpaca\\RobofocusAlpaca.exe")
    if not args.sign:
        print()
        print("Note: Executable is NOT signed. To sign, run:")
        print("  set CODESIGN_CERT=path\\to\\certificate.pfx")
        print("  python build.py --sign")
    print()
    print("To create an installer, use Inno Setup with installer.iss")
    print()

if __name__ == '__main__':
    main()
