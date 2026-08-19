# HubbleNetwork Satellite Application

Continuously builds Hubble satellite packets and transmits them in a loop.
This is the satellite counterpart to the BLE beacon in `firmware/zephyr`, and
it produces the `nrf21540dk_sat` and `xg24_rb4187c_sat` images published in
`merge/`.

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
library rather than source. Silicon Labs SoCs are the other way around: the
radio is compiled from source, but against Silicon Labs' RAIL library, which is
itself a blob in `hal_silabs`. Neither is fetched by `west update`; pull them in
explicitly once after setting up the workspace:

```shell
west blobs fetch hubblenetwork-sdk
west blobs fetch hal_silabs
```

Without these the build fails to link the satellite radio. Run
`west blobs list <module>` to see what is available and whether it has been
fetched.

### Building and running

To build the application, run the following command:

```shell
cd hubble-sat-app
west build -b nrf21540dk/nrf52840 app
```

Once you have built the application, run the following command to flash it:

```shell
west flash
```

A locally built image carries the placeholder key and will not produce
decodable traffic. Use `hubbledemo flash nrf21540dk_sat` to get an image
provisioned with a real device key.

## Supported boards

| Board | Target | Notes |
|-------|--------|-------|
| Nordic nRF21540 DK | `nrf21540dk/nrf52840` | Uses the nRF52 blob; the SDK drives the on-board FEM around each transmission |
| Silicon Labs xG24-RB4187C | `xg24_rb4187c` | 19.5 dBm PA part (`EFR32MG24B220`); radio board, needs a WSTK/Pro Kit mainboard to run |

### A board must have a power amplifier

Reaching a satellite needs far more link budget than terrestrial BLE. A board
whose radio tops out around 0 dBm with no front-end module (FEM/PA) will build
and transmit happily, but the signal will not be received. The failure mode is
silent: the firmware reports success on every packet and nothing shows up in
the satellite console.

The nRF21540 DK qualifies because of its FEM, not because of its SoC. The
nRF54L15 DK was evaluated and **deliberately excluded** for exactly this
reason — it builds and runs, but at 0 dBm with no front-end it cannot close the
link. Do not add it back.

Silicon Labs xG24 parts have the same trap in a subtler form. They come in
10 dBm and 19.5 dBm variants, and the part number encodes which: the digit
before the flash size is `1` for 10 dBm and `2` for 19.5 dBm. The SDK asks the
radio for 20 dBm and RAIL quietly clamps that to whatever the part supports, so
a 10 dBm part gives up 10 dB with nothing in the log to show for it. Only
`xg24_rb4187c` (`EFR32MG24B220`) is a 19.5 dBm board. The xG24 Explorer Kit
(`xg24_ek2703a`, `EFR32MG24B210`) and Dev Kit (`xg24_dk2601b`,
`EFR32MG24B310`) are 10 dBm parts — both build cleanly, and neither should be
used for satellite.

The SDK compiles satellite support for `thingy53/nrf5340/cpunet` and
`xiao_mg24` as well, but SDK support alone is not sufficient — confirm the
board has a PA and check its output power before adding it. Adding one means
adding an entry to `merge/md.json`; the CI matrix is generated from that file.
