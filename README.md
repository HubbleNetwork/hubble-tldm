# Hubble TLDM - Tool-Less Device Management

A streamlined device provisioning system that eliminates the need for manual tool installation and setup. TLDM (Tool-Less Device Management) automatically downloads all necessary tools, firmware, and dependencies, making device provisioning as simple as running a single command.

## What is Tool-Less Device Management?

**Tool-Less Device Management (TLDM)** means you don't need to:
- Manually install JLink tools
- Download firmware images
- Set up Python environments
- Configure serial ports
- Install dependencies

Everything is automatically downloaded and configured during the provisioning process.

## Quick Start

Provision a device with a single command - no tools to install first:

```bash
curl -s https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/refs/heads/master/provision_merge.sh | bash -s -- --device-id 214cca30-ca6f-48c2-8d7c-55368276471c --key OTQhLHNU385buqYhthomsmwvd+sGRqoE5QIAXcBGg= --board-id xg24_ek2703a
```

## The Tool-Less Advantage

### Traditional Approach (Tool-Heavy)
1. Download and install JLink tools manually
2. Download firmware images separately
3. Set up Python environment
4. Install serial communication libraries
5. Configure device connections
6. Run provisioning scripts

### TLDM Approach (Tool-Less)
1. Run one command
2. Everything else happens automatically

## What This Does

The provisioning script automatically:

1. **Downloads JLink tools** - Professional debugging and programming tools
2. **Downloads firmware** - Board-specific binary firmware image (e.g., `xg24_ek2703a.bin`)
3. **Merges device key** - Embeds the cryptographic key directly into the firmware at a specified offset
4. **Flashes merged firmware** - Programs the device with the firmware containing the embedded key

## Requirements

- **System tools**: `wget`, `curl`, `tar`, `base64` - Usually available by default
- **Hardware**: JLink-compatible device connected via USB

## Supported Boards

Currently, only these boards are supported:

- **[`xg24_ek2703a`](https://docs.zephyrproject.org/latest/boards/silabs/dev_kits/xg24_ek2703a/doc/index.html)**: Silicon Labs EFR32MG24 Development Kit
- **[`nrf21540dk`](https://docs.zephyrproject.org/latest/boards/nordic/nrf21540dk/doc/index.html)**: Nordic nRF21540 Development Kit

## Usage

### Basic Provisioning

```bash
curl -s https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/refs/heads/master/provision_merge.sh | bash -s -- --device-id <device-id> --key <key> --board-id <board-name>
```

### Parameters

- **`--device-id`**: Unique identifier for the device (UUID format)
- **`--key`**: Cryptographic key for the device (base64 encoded)
- **`--board-id`**: Board identifier (must be `xg24_ek2703a` or `nrf21540dk`)
- **`--key-offset`**: (Optional) Memory offset where key should be stored (default: 0x2000)
- **`--provision-option`** Provision option (optional: merge|serial, default: merge)

### Examples

```bash
# Silicon Labs EFR32MG24 Development Kit
curl -s https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/refs/heads/master/provision_merge.sh | bash -s -- --device-id 214cca30-ca6f-48c2-8d7c-55368276471c --key OTQhLHNU385buqYhthomsmwvd+sGRqoE5QIAXcBGg= --board-id xg24_ek2703a

# Nordic nRF21540 Development Kit
curl -s https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/refs/heads/master/provision_merge.sh | bash -s -- --device-id 214cca30-ca6f-48c2-8d7c-55368276471c --key OTQhLHNU385buqYhthomsmwvd+sGRqoE5QIAXcBGg= --board-id nrf21540dk
```

## How Tool-Less Management Works

### 1. Automatic Tool Downloads
The script downloads all necessary components from GitHub:
- **JLink tools**: Professional debugging suite (no manual installation)
- **Firmware images**: Board-specific `.bin` files (no manual download)
- **No Python dependencies**: Direct binary firmware manipulation

### 2. Zero-Configuration Environment Setup
- Downloads and extracts JLink tools automatically
- No Python environment setup required
- No configuration files or manual setup required

### 3. Intelligent Device Programming
- Flashes firmware using automatically downloaded JLinkExe
- **xg24_ek2703a**: Uses EFR32MG24BxxxF1536 device type
- **nRF21540DK**: Uses nRF52840_xxAA device type
- Configurable connection parameters (SWD, speed, etc.)
- No manual JLink configuration needed

### 4. Direct Firmware Key Embedding
- Embeds base64-encoded cryptographic keys directly into firmware
- Configurable key storage offset (default: 0x2000)
- No serial communication or port detection required
- Creates merged firmware file for programming

## File Structure
