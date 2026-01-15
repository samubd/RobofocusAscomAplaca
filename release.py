#!/usr/bin/env python
"""
Release script for Robofocus ASCOM Alpaca Driver.

Usage:
    python release.py [--version X.Y.Z]

This script will:
1. Run the build script to create the executable
2. Create a portable ZIP package
3. Display instructions for creating GitHub release
"""

import os
import shutil
import subprocess
import sys
import argparse
import zipfile
import re


def get_version_from_changelog():
    """Extract latest version from CHANGELOG.md."""
    try:
        with open('CHANGELOG.md', 'r', encoding='utf-8') as f:
            content = f.read()
            # Look for [X.Y.Z] pattern
            match = re.search(r'\[(\d+\.\d+\.\d+)\]', content)
            if match:
                return match.group(1)
    except FileNotFoundError:
        pass
    return "1.0.0"


def update_version_in_files(version):
    """Update version number in various files."""
    print(f"Updating version to {version}...")

    # Update installer.iss
    iss_path = 'installer.iss'
    if os.path.exists(iss_path):
        with open(iss_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(
            r'#define MyAppVersion ".*?"',
            f'#define MyAppVersion "{version}"',
            content
        )
        with open(iss_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Updated {iss_path}")

    # Update __init__.py if exists
    init_path = os.path.join('robofocus_alpaca', '__init__.py')
    if os.path.exists(init_path):
        with open(init_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(
            r'__version__ = ".*?"',
            f'__version__ = "{version}"',
            content
        )
        with open(init_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Updated {init_path}")


def run_build():
    """Run the build script."""
    print("\n" + "=" * 60)
    print("Building executable...")
    print("=" * 60 + "\n")

    result = subprocess.run([sys.executable, 'build.py'], capture_output=False)
    if result.returncode != 0:
        print("[ERROR] Build failed!")
        sys.exit(1)


def create_portable_zip(version):
    """Create portable ZIP package."""
    print("\nCreating portable ZIP package...")

    dist_dir = os.path.join('dist', 'RobofocusAlpaca')
    if not os.path.exists(dist_dir):
        print("[ERROR] dist/RobofocusAlpaca not found. Run build first.")
        sys.exit(1)

    # Create release directory
    release_dir = 'release'
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir)
    os.makedirs(release_dir)

    # Create ZIP file
    zip_name = f'RobofocusAlpaca_v{version}_Portable.zip'
    zip_path = os.path.join(release_dir, zip_name)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)

    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"  Created: {zip_path} ({zip_size:.1f} MB)")

    return zip_path


def generate_release_notes(version):
    """Generate release notes from CHANGELOG."""
    print("\nGenerating release notes...")

    notes = f"""## Robofocus ASCOM Alpaca Driver v{version}

### Downloads

| File | Description |
|------|-------------|
| `RobofocusAlpaca_v{version}_Portable.zip` | Portable version - extract and run |
| `RobofocusAlpaca_Setup_{version}.exe` | Windows installer (if available) |

### Quick Start

1. Download the portable ZIP or installer
2. Extract/Install the application
3. Run `RobofocusAlpaca.exe`
4. Open NINA and use Alpaca Discovery to find the focuser
5. Connect and enjoy!

### Note for First-Time Users

Windows SmartScreen may show a warning because the executable is not digitally signed.
Click "More info" -> "Run anyway" to proceed. This is normal for open-source software.

### System Requirements

- Windows 10/11
- .NET Framework is NOT required
- No Python installation needed

### What's New

See [CHANGELOG.md](CHANGELOG.md) for full details.
"""

    notes_path = os.path.join('release', 'RELEASE_NOTES.md')
    with open(notes_path, 'w', encoding='utf-8') as f:
        f.write(notes)

    print(f"  Created: {notes_path}")
    return notes_path


def print_github_instructions(version):
    """Print instructions for creating GitHub release."""
    print("\n" + "=" * 60)
    print("GITHUB RELEASE INSTRUCTIONS")
    print("=" * 60)
    print(f"""
1. Commit all changes:
   git add .
   git commit -m "Release v{version}"

2. Create and push tag:
   git tag -a v{version} -m "Release v{version}"
   git push origin main
   git push origin v{version}

3. Create GitHub Release:
   - Go to: https://github.com/samubd/RobofocusAscomAplaca/releases/new
   - Select tag: v{version}
   - Title: Robofocus ASCOM Alpaca Driver v{version}
   - Copy content from: release/RELEASE_NOTES.md
   - Upload files from: release/

4. Files to upload:
   - release/RobofocusAlpaca_v{version}_Portable.zip

5. (Optional) If you have Inno Setup installed:
   - Compile installer.iss
   - Upload: installer_output/RobofocusAlpaca_Setup_{version}.exe
""")


def main():
    parser = argparse.ArgumentParser(description='Create release packages')
    parser.add_argument('--version', type=str, help='Version number (e.g., 1.0.0)')
    parser.add_argument('--skip-build', action='store_true', help='Skip build step')
    args = parser.parse_args()

    print("=" * 60)
    print("Robofocus ASCOM Alpaca Driver - Release Script")
    print("=" * 60)

    # Determine version
    version = args.version or get_version_from_changelog()
    print(f"\nRelease version: {version}")

    # Update version in files
    update_version_in_files(version)

    # Run build
    if not args.skip_build:
        run_build()

    # Create packages
    zip_path = create_portable_zip(version)
    notes_path = generate_release_notes(version)

    # Print instructions
    print_github_instructions(version)

    print("\n" + "=" * 60)
    print("[OK] Release preparation complete!")
    print("=" * 60)
    print(f"\nRelease files are in: release/")
    print(f"  - {os.path.basename(zip_path)}")
    print(f"  - RELEASE_NOTES.md")


if __name__ == '__main__':
    main()
