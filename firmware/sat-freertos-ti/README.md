# HubbleNetwork Satellite Application
Continuously builds Hubble satellite packets and transmits them in a loop on the
**TI CC2755P10 LaunchPad**. This uses FreeRTOS and produces the `lp_em_cc2755p10_sat` image published
in `merge/`.

The master key is a placeholder at build time and is patched into the ELF by
`hubbledemo flash` after the device is registered with the Hubble cloud.

Each packet carries a 4 byte payload: the device uptime in seconds, big-endian.
The payload is encrypted along with the rest of the packet.
`hubble_sat_packet_get()` only accepts payload lengths of 0, 4, 9 or 13 bytes
and rejects anything else with `-EINVAL`, and a longer payload means a larger
PDU and more airtime per transmission.

## Getting Started

This firmware uses **FreeRTOS**. Many other examples, even for this hardware,
use Zephyr. The set up process is different here.

`firmware/ti-zephyr` is not a counterexample.
It is BLE only, using Zephyr's Bluetooth stack, so it needs no TI-specific SDK code at all.

Needed tools:
- [TI SimpleLink Low Power F3 SDK](https://www.ti.com/tool/download/SIMPLELINK-LOWPOWER-F3-SDK)
- SysConfig
- TI Clang

## Building

```shell
cd firmware/sat-freertos-ti
git clone --depth 1 --branch "$(cat sdk-revision)" \
  https://github.com/HubbleNetwork/hubble-device-sdk.git hubble-device-sdk

cd hubble-sat-app
export TICLANG_ARMCOMPILER=/path/to/ti/ti-cgt-armllvm
export SIMPLELINK_LOWPOWER_F3_SDK_INSTALL_DIR=/path/to/ti/simplelink_lowpower_f3_sdk
export SYSCONFIG_TOOL=/path/to/ti/sysconfig/sysconfig_cli.sh
make -f lp_em_cc2755p10.mk
```

Update the paths above to where you downloaded the referenced tools.

That produces `build/hubble-sat-app.out`, which CI publishes as
`merge/lp_em_cc2755p10_sat.elf`.

> [!NOTE]
> If on windows and using cmd or PowerShell, use
> `sysconfig_cli.bat` instead of `sysconfig_cli.sh`.

## Flashing

A locally built image carries the placeholder key and will not produce decodable
traffic. Use `hubbledemo flash lp_em_cc2755p10_sat` to get an image provisioned
with a real device key.

The CC2755P10 LaunchPad uses an on-board XDS110 debugger rather than a J-Link,
so this board uses `generate-hex` method in `merge/md.json`: `hubbledemo` writes a
`.hex` and you must manually flash it with UniFlash or CCS.

## Source code

The source code is directly copied from the SDK's sat-continuous sample.
`lp_em_cc2755p10.mk` is loosely modified to fit the file structure here.
`main.c` is modified to use a easily modifiable master key and to send uptime
in seconds as a payload.

## Supported boards

| Board | Target | Notes |
|-------|--------|-------|
| TI CC2755P10 LaunchPad | `lp_em_cc2755p10` | Integrated PA; XDS110 debugger, so `generate-hex` rather than `jlink-flash` |

### A board must have a power amplifier

Reaching a satellite needs far more link budget than terrestrial BLE. A board
whose radio tops out around 0 dBm with no front-end module (FEM/PA) will build
and transmit happily, but the signal will not be received. The failure mode is
silent: the firmware reports success on every packet and nothing shows up in
the satellite console.
