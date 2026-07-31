# HubbleNetwork Satellite Application

Continuously builds Hubble satellite packets and transmits them in a loop.
This is the satellite counterpart to the BLE beacon in `firmware/zephyr`, and
it produces the `nrf54l15dk_sat` image published in `merge/`.

The master key is a placeholder at build time and is patched into the ELF by
`hubbledemo flash` after the device is registered with the Hubble cloud, so
the workflow here is the same as the BLE demo application.

Each packet carries a 4 byte payload: the device uptime in seconds,
big-endian. The payload is encrypted along with the rest of the packet.
`hubble_sat_packet_get()` only accepts payload lengths of 0, 4, 9 or 13 bytes
and rejects anything else with `-EINVAL`, and a longer payload means a larger
PDU and more airtime per transmission.

> [!NOTE]
> Satellite functionality is pre-production and not yet ready for production
> deployments.

## Getting Started

Before getting started, make sure you have a proper Zephyr development
environment. Follow the official
[Zephyr Getting Started Guide](https://docs.zephyrproject.org/latest/getting_started/index.html) to install dependencies (the rest of the steps are covered below).

### Initialization

Clone the repo:
```shell
git clone https://github.com/HubbleNetwork/hubble-tldm.git
```

Enter the correct directory:
```shell
cd hubble-tldm/firmware/sat-zephyr
```

Optionally first create a Python venv:

```shell
python -m venv .venv
source .venv/bin/activate
```

Then set up the west installation (```pip install west``` if not installed)

```shell
west init -l hubble-sat-app
west update
# Export a Zephyr CMake package. This allows CMake to automatically load boilerplate code required for building Zephyr applications.
west zephyr-export
# The Zephyr west extension command, west packages can be used to install Python dependencies.
west packages pip --install
# Install the Zephyr SDK
west sdk install
```

### Satellite radio blobs

The satellite radio implementation for Nordic SoCs ships as a prebuilt static
library rather than source. These are **not** fetched by `west update`; pull
them in explicitly once after setting up the workspace:

```shell
west blobs fetch hubblenetwork-sdk
```

Without this the build fails to link the satellite radio. Run
`west blobs list hubblenetwork-sdk` to see what is available and whether it has
been fetched.

### Building and running

To build the application, run the following command:

```shell
cd hubble-sat-app
west build -b nrf54l15dk/nrf54l15/cpuapp app
```

Once you have built the application, run the following command to flash it:

```shell
west flash
```

A locally built image carries the placeholder key and will not produce
decodable traffic. Use `hubbledemo flash nrf54l15dk_sat` to get an image
provisioned with a real device key.

## Supported boards

| Board | Target |
|-------|--------|
| Nordic nRF54L15 DK | `nrf54l15dk/nrf54l15/cpuapp` |

The SDK also supports satellite on `nrf21540dk`, `thingy53/nrf5340/cpunet`,
`xg24_rb4187c`, and `xiao_mg24`. Adding one means adding an entry to
`merge/md.json`; the CI matrix is generated from that file.
