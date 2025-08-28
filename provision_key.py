#!/usr/bin/env python3
"""
Device Key Provisioning Script for Hubble TLDM

This script provisions a cryptographic key to a device using serial communication.
The device must be listening on the serial port and be ready to receive the key.

Usage: provision_key.py [-h] [-b] <key> <serial_port> <device_type>
"""

import argparse
import base64
import sys
import time
from typing import Optional

import serial
import subprocess


# =============================================================================
# Constants
# =============================================================================
SLEEP_TIME = 0.05
RESET_DELAY = 3


# =============================================================================
# Main Functions
# =============================================================================
def reset_device(device_type: str) -> None:
    """Reset the device using JLinkExe.
    
    Raises:
        SystemExit: If the device reset fails
    """
    try:
        subprocess.run(
            ["JLinkExe"],
            input=f"connect\n{device_type}\nS\n4000\nReset\nexit\n",
            text=True,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error resetting device: {e}", file=sys.stderr)
        sys.exit(1)


def provision_key(key_string: str, serial_port: str, base64_encoded: bool, device_type: str) -> None:
    """Provision a cryptographic key to the device.
    
    Args:
        key_string: The key as a string (either raw or base64 encoded)
        serial_port: Serial port connected to the device
        base64_encoded: Whether the key is base64 encoded
        
    Raises:
        SystemExit: If provisioning fails
    """
    # Reset device first
    print("[INFO] Resetting device...")
    reset_device(device_type)
    
    # Give enough time for reset
    print(f"[INFO] Waiting {RESET_DELAY} seconds for device reset...")
    time.sleep(RESET_DELAY)
    
    # Process key data
    try:
        if base64_encoded:
            print("[INFO] Decoding base64 key...")
            key_data = bytearray(base64.b64decode(key_string))
        else:
            print("[INFO] Using raw key string...")
            key_data = bytearray(key_string.encode('utf-8'))
            
        if len(key_data) != 32:
            print(f"[ERROR] Key size: {len(key_data)} bytes, need to use 32 bytes")
            sys.exit(1)
        print(f"[INFO] Key size: {len(key_data)} bytes")
        
    except base64.binascii.Error as e:
        print(f"Error decoding base64 key: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Open serial connection
    try:
        print(f"[INFO] Opening serial connection to {serial_port}...")
        ser = serial.Serial(port=serial_port, baudrate=115200, timeout=1)
        ser.reset_input_buffer()
    except serial.SerialException as e:
        print(f"Serial connection error: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Provision the key
        print("[INFO] Provisioning key to device...")
        for byte in key_data:
            ser.write(bytes([byte]))
            time.sleep(SLEEP_TIME)
        
        # Provision UTC time (in milliseconds)
        print("[INFO] Provisioning UTC timestamp...")
        utc_ms = int(time.time() * 1000)
        timestamp_frame = f"{utc_ms}\n".encode("ascii")
        
        for byte in timestamp_frame:
            ser.write(bytes([byte]))
            time.sleep(SLEEP_TIME)
            
        print("[SUCCESS] Key provisioning completed successfully!")
        
    finally:
        ser.close()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed command line arguments
        
    Raises:
        SystemExit: If argument parsing fails
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False
    )
    
    parser.add_argument(
        "key",
        help="The key string to provision (raw or base64 encoded)"
    )
    
    parser.add_argument(
        "serial",
        help="Serial port connected to the device"
    )
    
    parser.add_argument(
        "-b", "--base64",
        help="The key is encoded in base64",
        action="store_true",
        default=False
    )

    parser.add_argument(
        "device",
        help="The JLink device type to provision"
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point for the script."""
    try:
        args = parse_arguments()
        provision_key(args.key, args.serial, args.base64, args.device)
    except KeyboardInterrupt:
        print("\n[INFO] Operation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
