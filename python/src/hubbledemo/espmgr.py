"""Patch and flash Espressif images (the ``esptool-flash`` method).

ESP boards are published as two files from the same build: the app ELF and a
merged flash image -- bootloader, partition table and app -- written at flash
offset 0x0. The ELF alone is not flashable, so the ELF is only used to find
``master_key``: its address is mapped to a file offset through the load address
of each segment in the app image, and the bytes there must match the ELF's copy
of the key before anything is overwritten.

Overwriting the key invalidates the app image's checksum and SHA-256 digest, and
the second-stage bootloader refuses to boot an image that fails either, so both
are recomputed after patching.
"""

from __future__ import annotations

import hashlib
import io
import struct

from elftools.elf.elffile import ELFFile

from .elfmgr import _find_symbol

_KEY_SYMBOL = "master_key"

# CONFIG_PARTITION_TABLE_OFFSET defaults to 0x8000 on every ESP chip, and the
# table occupies at most 0xC00 bytes.
_PARTITION_TABLE_OFFSET = 0x8000
_PARTITION_TABLE_MAX_LEN = 0xC00
_PARTITION_ENTRY_LEN = 32
_PARTITION_MAGIC = b"\xaa\x50"
_PARTITION_TYPE_APP = 0x00

# esp_image_header_t: 8-byte common header, then a 16-byte extended header whose
# last byte says whether a SHA-256 digest follows the checksum.
_IMAGE_MAGIC = 0xE9
_IMAGE_HEADER_LEN = 24
_IMAGE_HASH_APPENDED_OFFSET = 23
_SEGMENT_HEADER_LEN = 8
_CHECKSUM_SEED = 0xEF
_DIGEST_LEN = 32

# If any serial port has one of these USB vendor IDs, only those ports are
# tried; otherwise every port is. Espressif's native USB Serial/JTAG, then the
# USB-UART bridges used on Espressif dev kits (Silicon Labs CP210x, WCH CH34x,
# FTDI).
_ESP_USB_VIDS = (0x303A, 0x10C4, 0x1A86, 0x0403)


def _app_partitions(image: bytes) -> list[tuple[int, int]]:
    """Return (offset, size) of every app partition in the partition table."""
    parts = []
    end = min(len(image), _PARTITION_TABLE_OFFSET + _PARTITION_TABLE_MAX_LEN)
    pos = _PARTITION_TABLE_OFFSET
    while pos + _PARTITION_ENTRY_LEN <= end:
        entry = image[pos : pos + _PARTITION_ENTRY_LEN]
        # The table ends at the first entry without the partition magic: the
        # MD5 entry (0xEBEB) or erased flash (0xFFFF).
        if entry[:2] != _PARTITION_MAGIC:
            break
        offset, size = struct.unpack_from("<II", entry, 4)
        if entry[2] == _PARTITION_TYPE_APP:
            parts.append((offset, size))
        pos += _PARTITION_ENTRY_LEN
    return parts


def _image_layout(
    image: bytes, start: int
) -> tuple[list[tuple[int, int, int]], int, int | None]:
    """
    Parse the app image starting at ``start``.

    Returns the (file offset, length, load address) of each segment's data, the
    offset of the checksum byte, and the offset of the SHA-256 digest (None if
    not appended).
    """
    if start + _IMAGE_HEADER_LEN > len(image):
        raise ValueError("app image is truncated")
    segment_count = image[start + 1]
    hash_appended = image[start + _IMAGE_HASH_APPENDED_OFFSET] == 1

    segments = []
    pos = start + _IMAGE_HEADER_LEN
    for _ in range(segment_count):
        if pos + _SEGMENT_HEADER_LEN > len(image):
            raise ValueError("app image is truncated")
        load_addr, length = struct.unpack_from("<II", image, pos)
        pos += _SEGMENT_HEADER_LEN
        segments.append((pos, length, load_addr))
        pos += length
    if pos > len(image):
        raise ValueError("app image is truncated")

    # Zero padding fills up to the last byte of a 16-byte block, which holds the
    # checksum. Alignment is relative to the start of the image.
    checksum_off = pos + 15 - ((pos - start) % 16)
    digest_off = checksum_off + 1 if hash_appended else None

    end = digest_off + _DIGEST_LEN if digest_off is not None else checksum_off + 1
    if end > len(image):
        raise ValueError("app image is truncated")
    return segments, checksum_off, digest_off


def _checksum(image: bytes | bytearray, segments: list[tuple[int, int, int]]) -> int:
    """XOR of every byte of segment data, seeded with 0xEF."""
    checksum = _CHECKSUM_SEED
    for off, length, _load_addr in segments:
        for byte in image[off : off + length]:
            checksum ^= byte
    return checksum


def locate_key(elf: io.BytesIO) -> tuple[int, bytes]:
    """Return the load address of ``master_key`` and its contents in the ELF."""
    elf.seek(0)
    elffile = ELFFile(elf)
    sym, sec = _find_symbol(elffile, _KEY_SYMBOL)
    if sym is None:
        raise ValueError(f"{_KEY_SYMBOL} not found in elf file")
    addr = int(sym["st_value"])
    size = int(sym["st_size"])
    if size == 0:
        raise ValueError(f"{_KEY_SYMBOL} has zero size in elf file")
    start = addr - int(sec["sh_addr"])
    return addr, sec.data()[start : start + size]


def _find_key(image: bytes, key_addr: int, key_len: int):
    """
    Find the app image whose segment loads ``key_addr``.

    Returns (app image offset, its segments, checksum offset, digest offset,
    file offset of the key).
    """
    for part_off, _part_size in _app_partitions(image):
        if part_off >= len(image) or image[part_off] != _IMAGE_MAGIC:
            continue  # partition left empty in the merged image (e.g. ota_1)
        segments, checksum_off, digest_off = _image_layout(image, part_off)
        for seg_off, seg_len, seg_addr in segments:
            if seg_addr <= key_addr and key_addr + key_len <= seg_addr + seg_len:
                key_off = seg_off + (key_addr - seg_addr)
                return part_off, segments, checksum_off, digest_off, key_off
    raise ValueError(f"no app image segment loads address 0x{key_addr:08x}")


def patch_image(image: bytes, key_addr: int, expected: bytes, key: bytes) -> bytes:
    """
    Return a copy of a merged ESP flash image with ``key`` written at load
    address ``key_addr``, and the containing app image's checksum and digest
    updated.

    ``expected`` is what the ELF says is at ``key_addr``; the image must hold
    the same bytes there, which catches an ELF and image from different builds.

    Raises ValueError if the key cannot be located in an app image, the image
    disagrees with ``expected``, or the image's existing checksum or digest do
    not verify -- the latter means the image layout is not what this parser
    expects, and re-sealing it would produce an image the bootloader rejects.
    """
    if len(key) != len(expected):
        raise ValueError(f"key is {len(key)} bytes, but the firmware holds a {len(expected)}-byte key")

    part_off, segments, checksum_off, digest_off, key_off = _find_key(image, key_addr, len(key))
    key_end = key_off + len(key)
    if image[key_off:key_end] != expected:
        raise ValueError(
            f"image bytes at 0x{key_addr:08x} do not match the ELF; "
            "the image and ELF are probably from different builds"
        )

    if _checksum(image, segments) != image[checksum_off]:
        raise ValueError("app image checksum does not verify before patching")
    if digest_off is not None:
        digest = hashlib.sha256(image[part_off : checksum_off + 1]).digest()
        if digest != image[digest_off : digest_off + _DIGEST_LEN]:
            raise ValueError("app image SHA-256 does not verify before patching")

    out = bytearray(image)
    out[key_off:key_end] = key
    out[checksum_off] = _checksum(out, segments)
    if digest_off is not None:
        out[digest_off : digest_off + _DIGEST_LEN] = hashlib.sha256(
            out[part_off : checksum_off + 1]
        ).digest()
    return bytes(out)


def _candidate_ports() -> list[str]:
    from serial.tools import list_ports

    ports = list(list_ports.comports())
    preferred = [p.device for p in ports if p.vid in _ESP_USB_VIDS]
    return preferred or [p.device for p in ports]


def find_device(chip: str) -> str:
    """
    Return the serial port of a connected ``chip`` (an esptool chip name such as
    ``esp32c6``), trying every likely port.

    Raises RuntimeError if no matching device answers.
    """
    from esptool.cmds import detect_chip
    from esptool.targets import CHIP_DEFS

    expected = CHIP_DEFS[chip].CHIP_NAME
    candidates = _candidate_ports()
    if not candidates:
        raise RuntimeError("No serial ports found. Check the USB cable (it must carry data).")

    problems = []
    for candidate in candidates:
        try:
            with detect_chip(candidate) as esp:
                found = esp.CHIP_NAME
        except Exception as e:  # esptool raises FatalError, pyserial OSError/SerialException
            problems.append(f"{candidate}: {e}")
            continue
        if found == expected:
            return candidate
        problems.append(f"{candidate}: found {found}, expected {expected}")

    raise RuntimeError(f"No {expected} found.\n  " + "\n  ".join(problems))


def flash_image(image: bytes, port: str) -> None:
    """Write a merged flash image at offset 0x0 and reset the device."""
    from esptool.cmds import attach_flash, detect_chip, reset_chip, run_stub, write_flash

    with detect_chip(port) as esp:
        esp = run_stub(esp)
        attach_flash(esp)
        write_flash(esp, [(0x0, image)])
        reset_chip(esp, "hard-reset")
