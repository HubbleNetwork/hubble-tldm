#!/usr/bin/env bash
# Device Provisioning Script for Hubble TLDM
# This script downloads necessary tools and firmware, then programs the device.

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
BASE_URL="https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/refs/heads/master"
JLINK_TAR="jlink.tar.gz"
PYTHON_SCRIPT="provision_key.py"
TAR_DIR="JLink_V862"
JLINK_EXE=""

# =============================================================================
# Command Line Argument Parsing
# =============================================================================
DEVICE_ID=""
KEY=""
BOARD_ID=""
JLINK_DEVICE=""
PROVISION_OPTION="merge"

while [[ $# -gt 0 ]]; do
    case $1 in
        --device-id)
            DEVICE_ID="$2"
            shift 2
            ;;
        --key)
            KEY="$2"
            shift 2
            ;;
        --board-id)
            BOARD_ID="$2"
            shift 2
            ;;
        --provision-option)
            PROVISION_OPTION="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 --device-id <id> --key <key> --board-id <board> [--provision-option <merge|serial>]"
            echo "  --device-id         Device identifier (required)"
            echo "  --key               Device key (required)"
            echo "  --board-id          Board identifier (required, e.g., efr32mg24-dk)"
            echo "  --provision-option  Provision option (optional: merge|serial, default: merge)"
            echo "  --help, -h          Show this help message"
            exit 0
            ;;
        *)
            echo "[WARNING] Unknown argument: $1" >&2
            echo "Use --help for usage information" >&2
            shift
            ;;
    esac
done

# =============================================================================
# Validation
# =============================================================================
if [[ -z "$DEVICE_ID" ]] || [[ -z "$KEY" ]] || [[ -z "$BOARD_ID" ]]; then
    echo "[ERROR] --device-id, --key, and --board-id are required" >&2
    echo "Usage: $0 --device-id <id> --key <key> --board-id <board> [--provision-option <merge|serial>]" >&2
    echo "Use --help for more information" >&2
    exit 1
fi

# validate provision option
if [[ "$PROVISION_OPTION" != "serial" && "$PROVISION_OPTION" != "merge" ]]; then
    echo "[ERROR] --provision-option must be either 'serial' or 'merge' (got: $PROVISION_OPTION)" >&2
    exit 1
fi

# Validate board ID
case "$BOARD_ID" in
    xg24_ek2703a)
        JLINK_DEVICE="EFR32MG24BxxxF1536"
        ;;
    nrf21540dk)
        JLINK_DEVICE="nRF52840_xxAA"
        ;;
    *)
        echo "[ERROR] Unsupported board ID: $BOARD_ID" >&2
        echo "[ERROR] Supported boards: xg24_ek2703a, nrf21540dk" >&2
        exit 1
        ;;
esac

# Set firmware filename based on board ID
FIRMWARE_IMAGE="${PROVISION_OPTION}/${BOARD_ID}.elf"

echo "[INFO] Starting device provisioning..."
echo "[INFO] Device ID: $DEVICE_ID"
echo "[INFO] Board ID: $BOARD_ID"
echo "[INFO] Firmware: $FIRMWARE_IMAGE"

# =============================================================================
# Download and Extract JLink Tools
# =============================================================================
# Prefer system JLinkExe if present
SYSTEM_JLINK="$(command -v JLinkExe || true)"

if [[ -n "$SYSTEM_JLINK" ]]; then
    echo "[INFO] Using system JLinkExe at: $SYSTEM_JLINK"
    JLINK_EXE="$SYSTEM_JLINK"
else
    echo "[INFO] System JLinkExe not found; using bundled tools"

    if [[ -d "$TAR_DIR" ]]; then
        echo "[INFO] JLink tools already exist, skipping download"
    else
        echo "[INFO] Downloading JLink tools package..."
        if ! wget -q "$BASE_URL/$JLINK_TAR" -O "$JLINK_TAR"; then
            echo "[ERROR] Failed to download JLink tools" >&2
            exit 1
        fi

        if ! tar -xzf "$JLINK_TAR"; then
            echo "[ERROR] Failed to extract JLink tools" >&2
            exit 1
        fi
    fi

    JLINK_EXE="$TAR_DIR/JLinkExe"

    if [[ ! -f "$JLINK_EXE" ]]; then
        echo "[ERROR] JLink executable not found at $JLINK_EXE" >&2
        exit 1
    fi
    if [[ ! -x "$JLINK_EXE" ]]; then
        chmod +x "$JLINK_EXE"
    fi
    export PATH="$(pwd)/$TAR_DIR:$PATH"
fi

# =============================================================================
# Download Firmware Image
# =============================================================================
mkdir -p "$(dirname "$FIRMWARE_IMAGE")"

if [[ -f "$FIRMWARE_IMAGE" ]]; then
    echo "[INFO] Firmware image already exists, skipping download"
else
    echo "[INFO] Downloading firmware image for board: $BOARD_ID..."
    if ! wget -q "$BASE_URL/$FIRMWARE_IMAGE" -O "$FIRMWARE_IMAGE"; then
        echo "[ERROR] Failed to download firmware image: $FIRMWARE_IMAGE" >&2
        echo "[ERROR] Make sure the firmware file exists at: $BASE_URL/$FIRMWARE_IMAGE" >&2
        exit 1
    fi
fi

# =============================================================================
# Python Environment Setup
# =============================================================================
echo "[INFO] Setting up Python virtual environment..."

# Download provision_key.py if it doesn't exist
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "[INFO] Downloading $PYTHON_SCRIPT..."
    if ! wget -q "$BASE_URL/$PYTHON_SCRIPT" -O "$PYTHON_SCRIPT"; then
        echo "[ERROR] Failed to download $PYTHON_SCRIPT" >&2
        exit 1
    fi
fi

# Download requirements.txt if it doesn't exist
if [[ ! -f "requirements.txt" ]]; then
    echo "[INFO] Downloading requirements.txt..."
    if ! wget -q "$BASE_URL/requirements.txt" -O "requirements.txt"; then
        echo "[ERROR] Failed to download requirements.txt" >&2
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [[ ! -d ".venv" ]]; then
    echo "[INFO] Creating Python virtual environment..."
    if ! python3 -m venv .venv; then
        echo "[ERROR] Failed to create virtual environment" >&2
        exit 1
    fi
fi

# Activate virtual environment and install requirements
echo "[INFO] Installing Python dependencies..."
source .venv/bin/activate
if ! pip install -r requirements.txt; then
    echo "[ERROR] Failed to install Python dependencies" >&2
    exit 1
fi

echo "[SUCCESS] Python environment setup completed"

# =============================================================================
# Flash Firmware
# =============================================================================

# if using merge, then need to merge first before flash
if [[ "$PROVISION_OPTION" == "merge" ]]; then
    echo "[INFO] Merging device ID and key into firmware image..."
    if ! python3 embed-key.py "$FIRMWARE_IMAGE" --key "$KEY"; then
        echo "[ERROR] Failed to merge device ID and key into firmware" >&2
        exit 1
    fi
    echo "[SUCCESS] Merged device ID and key into firmware image"
fi

echo "[INFO] Flashing firmware using JLinkExe..."
if ! printf "r\nloadfile $FIRMWARE_IMAGE\nr\ng\nqc\n" | JLinkExe \
      -device "$JLINK_DEVICE" \
      -if SWD \
      -speed 4000 \
      -autoconnect 1; then
    echo "[ERROR] Firmware flashing failed" >&2
    exit 1
fi

# =============================================================================
# Serial Port Detection (if using serial provisioning)
# =============================================================================
if [[ "$PROVISION_OPTION" == "serial" ]]; then

    echo "[INFO] Auto-detecting USB modem serial port..."

    # Find USB modem TTY devices
    usb_ttys=$(ls /dev/tty.usbmodem* 2>/dev/null | sort)

    if [[ -z "$usb_ttys" ]]; then
        echo "[ERROR] No USB modem TTY devices found" >&2
        echo "[INFO] Please ensure your device is connected via USB" >&2
        echo "[INFO] Available TTY devices:" >&2
        ls /dev/tty* 2>/dev/null | sort >&2
        exit 1
    fi

    # Select the first USB modem TTY device
    SERIAL_PORT=$(echo "$usb_ttys" | head -n 1)
    echo "[SUCCESS] Using serial port: $SERIAL_PORT"

# =============================================================================
# Run Python Provisioning
# =============================================================================
    echo "[INFO] Running Python provisioning with device ID and key..."
    echo "[INFO] Using serial port: $SERIAL_PORT"
    echo "[INFO] Using Python from virtual environment: $(which python3)"

    if ! python3 "$PYTHON_SCRIPT" --base64 "$KEY" "$SERIAL_PORT" "$JLINK_DEVICE"; then
        echo "[ERROR] Python provisioning failed" >&2
        exit 1
    fi
fi

echo "[SUCCESS] Device programmed successfully!"
echo "[INFO] Device ID: $DEVICE_ID has been provisioned"
