"""
ESP32 Boot configuration for Robofocus.

This file runs on every boot, before main.py.
Keep it minimal to ensure reliable startup.
"""

# Disable debug REPL on UART0 if needed for Robofocus communication
# (We use UART2 instead, so this is not necessary)

# Import garbage collector early
import gc

# Run garbage collection to maximize available memory
gc.collect()

# Print boot message
print("\n[boot] Robofocus ESP32 booting...")
print(f"[boot] Free memory: {gc.mem_free():,} bytes")
