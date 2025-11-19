# HubbleNetwork Demo Application


## Getting Started

Before getting started, make sure you have a proper Zephyr development
environment. Follow the official
[Zephyr Getting Started Guide](https://docs.zephyrproject.org/latest/getting_started/index.html) to install dependencies (the rest of the steps are covered below).

### Additional steps for downstream TI Zephyr

The TI downstream repository for zephyr here [here](https://github.com/TexasInstruments/simplelink-zephyr/tree/v3.7.0-ti-9.10).

* Install SDK version 0.16.9 by following the instructions [here](https://docs.zephyrproject.org/latest/develop/toolchains/zephyr_sdk.html) (note to replace the vesion in the lines to 0.16.9)
* Set the SDK install directory ```export ZEPHYR_SDK_INSTALL_DIR=/path/to/0.16.9-sdk```

### Initialization

To configure this project, run the following (skip the cloning steps if already cloned).

Clone the repo:
```shell
# initialize my-workspace for the demo application (main branch)
git clone https://github.com/HubbleNetwork/hubble-tldm.git
```

Enter the correct directory:
```shell
cd hubble-tldm/firmware/zephyr
```

Optionally first create a Python venv:

```shell
python -m venv .venv
source .venv/bin/activate
```

Then set up the west installation (```pip install west``` if not installed)

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

### Building and running

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
