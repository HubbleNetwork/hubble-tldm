import os
import struct
from pathlib import Path

import pytest
from esptool.bin_image import ESP32C6FirmwareImage, ELFSection, LoadFirmwareImage

from hubbledemo.cloud import fetch_bin, fetch_elf
from hubbledemo.espmgr import _app_partitions, locate_key, patch_image

APP_OFFSET = 0x10000
KEY = bytes(range(32))
# What the firmware's key.c initialises master_key to.
PLACEHOLDER = b"\x01" + b"\x00" * 31

# ESP32-C6 DROM, where const data such as master_key lives in a real build.
DROM_ADDR = 0x42800020
KEY_OFFSET_IN_RODATA = 40


def _partition_entry(ptype: int, subtype: int, offset: int, size: int, label: str) -> bytes:
    return (
        b"\xaa\x50"
        + struct.pack("<BBII", ptype, subtype, offset, size)
        + label.encode().ljust(16, b"\x00")
        + b"\x00" * 4
    )


def _app_image(rodata: bytes, rodata_addr: int) -> bytes:
    """An ESP32-C6 app image laid out by esptool itself, digest appended."""
    image = ESP32C6FirmwareImage()
    image.entrypoint = 0x40800000
    image.segments = [
        ELFSection(b".iram0.text", 0x40800000, b"\x13\x00\x00\x00" * 64, flags=0),
        ELFSection(b".flash.rodata", rodata_addr, rodata, flags=0),
    ]
    image.append_digest = True
    return image.save(None)


def _merged_image() -> bytes:
    """Bootloader stand-in, partition table at 0x8000 and the app at 0x10000."""
    rodata = b"\x11" * KEY_OFFSET_IN_RODATA + PLACEHOLDER + b"\x22" * 24
    image = bytearray(b"\xff" * APP_OFFSET)
    image[0:16] = b"\xe9" + b"\x00" * 15
    table = (
        _partition_entry(0x01, 0x02, 0x9000, 0x6000, "nvs")
        + _partition_entry(0x01, 0x01, 0xF000, 0x1000, "phy_init")
        + _partition_entry(0x00, 0x00, APP_OFFSET, 0x100000, "factory")
    )
    image[0x8000 : 0x8000 + len(table)] = table
    return bytes(image) + _app_image(rodata, DROM_ADDR)


def _load_app(merged: bytes):
    return LoadFirmwareImage("esp32c6", merged[APP_OFFSET:])


def _patch(merged: bytes, expected: bytes = PLACEHOLDER):
    return patch_image(merged, DROM_ADDR + KEY_OFFSET_IN_RODATA, expected, KEY)


def test_patched_image_checksum_and_digest_verify_with_esptool():
    patched = _patch(_merged_image())
    app = _load_app(patched)

    assert app.checksum == app.calculate_checksum()
    assert app.stored_digest == app.calc_digest
    assert KEY in b"".join(seg.data for seg in app.segments)


def test_patch_only_touches_key_checksum_and_digest():
    merged = _merged_image()
    patched = _patch(merged)
    key_off = merged.find(PLACEHOLDER, APP_OFFSET)

    changed = {i for i in range(len(merged)) if merged[i] != patched[i]}
    allowed = set(range(key_off, key_off + len(KEY)))
    # Checksum byte and SHA-256 are the last 33 bytes of the app image.
    allowed |= set(range(len(merged) - 33, len(merged)))
    assert changed <= allowed


def test_image_from_a_different_build_is_rejected():
    with pytest.raises(ValueError, match="different builds"):
        _patch(_merged_image(), expected=b"\x02" + b"\x00" * 31)


def test_address_outside_every_segment_is_rejected():
    with pytest.raises(ValueError, match="no app image segment loads address"):
        patch_image(_merged_image(), 0x42F00000, PLACEHOLDER, KEY)


def test_local_override_takes_bin_next_to_elf(tmp_path, monkeypatch):
    (tmp_path / "app.elf").write_bytes(b"elf")
    (tmp_path / "app.bin").write_bytes(b"bin")
    monkeypatch.setenv("HUBBLE_DEMO_ELF_FILE", str(tmp_path / "app.elf"))

    assert fetch_elf("any_board").getvalue() == b"elf"
    assert fetch_bin("any_board").getvalue() == b"bin"


_BUILT_ELF = os.getenv("HUBBLE_DEMO_ELF_FILE")


@pytest.mark.skipif(
    not (_BUILT_ELF and Path(_BUILT_ELF).with_suffix(".bin").exists()),
    reason="set HUBBLE_DEMO_ELF_FILE to a firmware/sat-esp-idf build's ELF, with its .bin alongside",
)
def test_built_image_patches_cleanly():
    elf = fetch_elf("built")
    merged = fetch_bin("built").getvalue()
    chip = os.getenv("HUBBLE_DEMO_ESPTOOL_CHIP", "esp32c6")

    key_addr, expected = locate_key(elf)
    patched = patch_image(merged, key_addr, expected, KEY[: len(expected)])
    app_offset = _app_partitions(patched)[0][0]
    app = LoadFirmwareImage(chip, patched[app_offset:])

    assert app.checksum == app.calculate_checksum()
    assert app.stored_digest == app.calc_digest
    assert KEY[: len(expected)] in b"".join(seg.data for seg in app.segments)
