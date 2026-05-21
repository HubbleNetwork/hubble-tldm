# Hubble TLDM - Tool-Less Device Management

[![PyPI](https://img.shields.io/pypi/v/pyhubbledemo.svg)](https://pypi.org/project/pyhubbledemo)
[![Python](https://img.shields.io/pypi/pyversions/pyhubbledemo.svg)](https://pypi.org/project/pyhubbledemo)
[![License](https://img.shields.io/github/license/HubbleNetwork/pyhubblenetwork)](LICENSE)

A streamlined device provisioning system for the **Hubble Terrestrial Network** that eliminates the need for manual tool installation and setup. TLDM (Tool-Less Device Management) automatically downloads all necessary tools, firmware, and dependencies, making device provisioning as simple as running a single command.

## Quick Start

Provision a device with a single command. Depending on the OS environment, this will download and install necessary tools.

Steps to run:
1. Plug in device via USB (*ensure this is not a power-only cable!*)
1. Open a terminal application
1. Get your organization ID and API access token from Hubble [here](https://dash.hubblenetwork.io/developer/api-tokens)
1. Paste the script below into the terminal, replacing ```<BOARD>``` ```<ORG_ID>``` and ```<API_TOKEN>``` with your values (see supported boards below)
1. Go!

### MacOS (Apple Silicon)

*Note: homebrew must be installed before running. See [here](https://brew.sh/) for installation instructions.*

```bash
brew install pipx && brew install segger-jlink && pipx run pyhubbledemo flash <BOARD> -o <ORG_ID> -t <API_TOKEN>
```
*Note: You will be prompted for a password to install segger-jlink tools (used to flash the firmware to your board)*

If desired, you can optionally install pyhubbledemo via pipx and use it from the command line:
```bash
pipx install pyhubbledemo
hubbledemo flash <BOARD> -o <ORG_ID> -t <API_TOKEN>
```

Or if you do not wish to install, you can run the command without installation:
```bash
pipx run pyhubbledemo flash <BOARD> -o <ORG_ID> -t <API_TOKEN>
```

## Supported Boards

Currently supported boards:
* nrf52dk
* nrf52840dk
* lp_em_cc2755p10
