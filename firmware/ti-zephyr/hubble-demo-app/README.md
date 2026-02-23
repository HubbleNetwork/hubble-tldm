# HubbleNetwork Demo Application


## Prerequisites

Make sure you have a proper Zephyr development environment. Follow the official
[Zephyr Getting Started Guide](https://docs.zephyrproject.org/latest/getting_started/index.html) to install dependencies.

The TI downstream repository for Zephyr is [here](https://github.com/TexasInstruments/simplelink-zephyr/tree/v3.7.0-ti-9.10).

Install SDK version 0.16.9 by following the instructions [here](https://docs.zephyrproject.org/latest/develop/toolchains/zephyr_sdk.html) (replace the version in those instructions with 0.16.9), then set the install directory:

```shell
export ZEPHYR_SDK_INSTALL_DIR=/path/to/zephyr-sdk-0.16.9
```

Python 3.11 is required to use TI's `crc-tool` for adding a CRC to images. On macOS:

```bash
brew install python@3.11
```


## Setup

Clone the repo:

```shell
git clone https://github.com/HubbleNetwork/hubble-tldm.git
```

Enter the correct directory:

```shell
cd hubble-tldm/firmware/ti-zephyr
```

Create and activate a Python 3.11 virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install TI's CRC tooling:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r hubble-demo-app/requirements.txt
```

Set up the west installation:

```shell
west init -l hubble-demo-app
west update
# Export a Zephyr CMake package. This allows CMake to automatically load boilerplate code required for building Zephyr applications.
west zephyr-export
# The Zephyr west extension command, west packages can be used to install Python dependencies.
west packages pip --install
# Install the Zephyr SDK
west sdk install
```


## Build & Flash

To build the application, run the following command:

```shell
cd hubble-demo-app
west build -b $BOARD app
```

where `$BOARD` is the target board.

A list of supported boards can be found via the `west boards` command.

Once you have built the application, run the following command to flash it:

```shell
west flash
```
