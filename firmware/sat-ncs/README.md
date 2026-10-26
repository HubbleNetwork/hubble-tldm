# HubbleNetwork Satellite Application (nRF Connect SDK)

Builds the satellite application from `firmware/sat-zephyr` with the nRF
Connect SDK. Nordic Thingy:53 is currently the only board built here, producing
the `thingy53_sat` image published in `merge/`.

Thingy:53 has no on-board debugger, and its satellite radio (with an nRF21540
FEM) is on the nRF5340 network core. Instead of a debug probe, it is flashed
over USB through the MCUboot bootloader it ships with. Only the nRF Connect SDK
builds network core images that this bootloader can pass on to the network
core, so this board has its own workspace.

`hubble-sat-app/thingy53` is the application core image that MCUboot boots,
which only starts the network core. The satellite application is the network
core image, and holds the device key as it does on every other board;
`hubble-sat-app/thingy53/sysbuild/cpunet.overlay` enables its FEM.
`hubbledemo flash` patches the key into the network core image and re-signs
it.

## Getting Started

Needed tools are the same as for `firmware/sat-zephyr`: Python 3 and west.
Set up the workspace from this directory:

```shell
cd hubble-tldm/firmware/sat-ncs
west init -l hubble-sat-app
west update
west zephyr-export
west packages pip --install
pip install -r nrf/scripts/requirements-build.txt -r bootloader/mcuboot/scripts/requirements.txt
west sdk install
west blobs fetch hubblenetwork-sdk
```

Build:

```shell
west build -b thingy53/nrf5340/cpuapp --sysbuild hubble-sat-app/thingy53
```

## Flashing

Remove the top part of the casing, hold **SW2** and move the power switch
**SW1** to ON. Thingy:53 starts in MCUboot serial recovery and shows up on USB
as `Bootloader Thingy:53`. Then either run `hubbledemo flash thingy53_sat`, or
program `build/dfu_application.zip` (placeholder key) with nRF Util:

```shell
nrfutil device program --firmware build/dfu_application.zip --traits mcuboot --serial-number <serial number>
```

Thingy:53 then restarts into the application and shows up on USB as a serial
port; the application's log output stays on the network core and is not
printed there. Repeat these steps to flash again.
