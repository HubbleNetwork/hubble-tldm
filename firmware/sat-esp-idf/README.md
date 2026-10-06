# HubbleNetwork Satellite Application (ESP-IDF)
Continuously builds Hubble satellite packets and transmits them in a loop on
Espressif SoCs. It produces the ESP satellite images published in `merge/`.

The master key is a placeholder at build time and is patched into the image by
`hubbledemo flash` after the device is registered with the Hubble cloud.

Each packet carries a 4 byte payload: the device uptime in seconds, big-endian.
The payload is encrypted along with the rest of the packet.
`hubble_sat_packet_get()` only accepts payload lengths of 0, 4, 9 or 13 bytes
and rejects anything else with `-EINVAL`, and a longer payload means a larger
PDU and more airtime per transmission.

## Getting Started

This firmware uses **ESP-IDF**. The Hubble Device SDK comes from the
[ESP Component Registry](https://components.espressif.com/components/hubblenetwork/hubble-device-sdk)
at the exact version pinned in `hubble-sat-app/main/idf_component.yml`, and is
downloaded into `managed_components/` on the first build.

Needed tools:
- [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c6/get-started/index.html) v6.1 or later

## Environment Setup

After installing esp-idf, set up your environment.

### Windows

ESP-IDF does not support MSys, which is used by Git Bash. You must use PowerShell.

If you installed ESP-IDF with the ESP-IDF Installation Manager (EIM), run its
activation script:

```ps1
. "C:\Espressif\tools\Microsoft.v<esp_idf_version>.PowerShell_profile.ps1"
```

If you cloned ESP-IDF and ran its `install.ps1`, run `export.ps1` from the
clone instead.

### Linux & macOS

```sh
source ~/esp/esp-idf/export.sh
```

## Building

```shell
cd firmware/sat-esp-idf/hubble-sat-app
idf.py set-target esp32c6
idf.py build
idf.py merge-bin -o merged.bin
```

## Flashing

A locally built image carries the placeholder key and will not produce decodable
traffic. Use `hubbledemo flash esp32c6_sat` to get an image provisioned
with a real device key.

## Source code

The source code is directly copied from the SDK's
[sat-continuous sample](https://github.com/HubbleNetwork/hubble-device-sdk/tree/main/samples/esp-idf/sat-continuous).
`main.c` is modified to use an easily modifiable master key and to send
uptime in seconds as a payload.

## Supported boards

Images are built per chip, not per board. The firmware touches no board
pins, so an image runs on any board with that chip, as long as the board:

- has at least 2 MB of flash (the ESP-IDF default the image is built for),
- needs no GPIO set up to route the radio to its antenna (some boards, such
  as the Seeed XIAO ESP32C6, have an RF switch that does), and
- resets into the ROM bootloader over USB without pressing BOOT, as
  Espressif's dev kits do, so `hubbledemo` can flash it unattended.

| Board id | Target | Validated on | Notes |
|----------|--------|--------------|-------|
| `esp32c6_sat` | `esp32c6` | ESP32-C6-DevKitM-1 | Integrated PA, up to +20 dBm |

### A board must have a power amplifier

Reaching a satellite needs far more link budget than terrestrial BLE. A board
whose radio tops out around 0 dBm with no front-end module (FEM/PA) will build
and transmit happily, but the signal will not be received. The failure mode is
silent: the firmware reports success on every packet and nothing shows up in
the satellite console.
