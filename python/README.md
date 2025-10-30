# Hubble Demo Script

This will enable you to flash a pre-determined set of boards and provision them with your credentials.

## Prerequisites

### OpenOCD Installation

This tool uses OpenOCD for flashing firmware to development boards. OpenOCD is open-source and works with multiple debug probe types:
- **J-Link** debug probes (SEGGER)
- **CMSIS-DAP** compatible debug probes (built into most development kits)

The tool automatically detects which probe is connected.

**macOS:**
```bash
brew install openocd
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install openocd
```

**Windows:**
Download from https://openocd.org/pages/getting-openocd.html

### Supported Boards

- nRF52 DK (`nrf52dk`)
- nRF52840 DK (`nrf52840dk`)
- nRF21540 DK (`nrf21540dk`)
- EFR32MG24 Explorer Kit (`xg24_ek2703a`)
- EFR32MG22 Explorer Kit (`xg22_ek4108a`)

## Installation

```bash
pip install .
```

## Usage

Set your Hubble credentials:
```bash
export HUBBLE_API_TOKEN="your-token"
export HUBBLE_ORG_ID="your-org-id"
```

Flash a board:
```bash
hubbledemo flash <board_name>
```

Example:
```bash
hubbledemo flash nrf52840dk
```