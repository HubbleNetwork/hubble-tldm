"""Patch and flash images through MCUboot serial recovery (the ``mcuboot-serial`` method).

MCUboot boards are published as two files from the same build: the ELF of the
image that holds ``master_key``, and the DFU zip with every signed image and a
manifest of the slots they go in. The ELF is only used to find ``master_key``:
its load address in flash, relative to the start of the ELF's flash contents,
is its offset in the body of the signed image, and the bytes there must match
the ELF's copy of the key before anything is overwritten.

MCUboot only accepts an image whose SHA-256 and signature verify, so both are
recomputed after patching. The factory MCUboot on these boards accepts images
signed with MCUboot's RSA-2048 development key (root-rsa-2048.pem in the
MCUboot repository, Apache-2.0), which is public and bundled in keys/; it gives
no protection, and is only what that bootloader expects.

An nRF5340 network core image is checked again by the network core bootloader
(b0n), against a SHA-256 of the firmware in validation info appended to it, so
that hash is recomputed as well.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import logging
import struct
import time
import zipfile
from importlib import resources
from typing import NamedTuple

from elftools.elf.elffile import ELFFile

from .elfmgr import _addr_for_segment, _compute_file_offset, _find_symbol

_KEY_SYMBOL = "master_key"
_SIGNING_KEY = "mcuboot-root-rsa-2048.pem"

# struct image_header and struct image_tlv_info in MCUboot's image.h.
_IMAGE_MAGIC = 0x96F3B83D
_IMAGE_HEADER_LEN = 32
_TLV_INFO_MAGIC = 0x6907
_TLV_PROT_INFO_MAGIC = 0x6908
_TLV_SHA256 = 0x10
_TLV_RSA2048_PSS = 0x20
_RSA_PSS_SALT_LEN = 32

# struct fw_info and the validation info after the firmware, in the nRF Connect
# SDK's fw_info_bare.h and validation_data.py. fw_info is at one of these
# offsets in the firmware; the validation info starts at the next word after
# the firmware's size, and holds the SHA-256 after its magic and address.
_FW_INFO_MAGIC = struct.pack("<II", 0x281EE6DE, 0x8FCEBB4C)
_FW_INFO_OFFSETS = (0x0, 0x200, 0x400, 0x800, 0x1000)
_FW_INFO_SIZE_OFFSET = 16
_FW_VALIDATION_MAGIC = struct.pack("<II", 0x281EE6DE, 0x86518483)
_FW_VALIDATION_HASH_OFFSET = 16

# CONFIG_BOOT_SERIAL_MAX_RECEIVE_SIZE in the Thingy:53 MCUboot.
_MCUBOOT_RX_BUF = 512
# MCUboot erases before acknowledging the first chunk of an image; on Thingy:53
# that took 0.5 s.
_FIRST_CHUNK_TIMEOUT_S = 10.0
# After a network core image, MCUboot answers reset with EBUSY until it has
# handed the image to the network core; on Thingy:53 the reset took 3 s with a
# 40 KB image, and the time grows with the image.
_RESET_TIMEOUT_S = 15.0


def locate_key(elf: io.BytesIO) -> tuple[int, bytes]:
    """
    Return the offset of ``master_key`` in the body of the signed image, and
    its contents in the ELF.
    """
    elf.seek(0)
    elffile = ELFFile(elf)
    sym, sec = _find_symbol(elffile, _KEY_SYMBOL)
    if sym is None:
        raise ValueError(f"{_KEY_SYMBOL} not found in elf file")
    size = int(sym["st_size"])
    if size == 0:
        raise ValueError(f"{_KEY_SYMBOL} has zero size in elf file")

    # The key may be initialised data, which runs from RAM but is stored in
    # flash: map its file offset to a flash address through the segments.
    file_off = _compute_file_offset(sym, sec)
    segments = [s for s in elffile.iter_segments() if s["p_type"] == "PT_LOAD" and s["p_filesz"]]
    flash_start = min(_addr_for_segment(s) for s in segments)
    for seg in segments:
        if seg["p_offset"] <= file_off and file_off + size <= seg["p_offset"] + seg["p_filesz"]:
            addr = _addr_for_segment(seg) + file_off - int(seg["p_offset"])
            elf.seek(file_off)
            return addr - flash_start, elf.read(size)
    raise ValueError(f"{_KEY_SYMBOL} is not stored in any loadable segment")


def _image_layout(image: bytes) -> tuple[int, int, int, dict[int, tuple[int, int]]]:
    """
    Parse a signed MCUboot image.

    Returns the header size, the body size, the length of the signed part
    (header, body and protected TLVs) and the (offset, length) of each
    unprotected TLV's value, by type.
    """
    if len(image) < _IMAGE_HEADER_LEN:
        raise ValueError("image is truncated")
    magic, _load_addr, hdr_size, prot_size, body_size = struct.unpack_from("<IIHHI", image)
    if magic != _IMAGE_MAGIC:
        raise ValueError("not an MCUboot image")

    signed_len = hdr_size + body_size + prot_size
    pos = signed_len
    if pos + 4 > len(image):
        raise ValueError("image is truncated")
    info_magic, info_len = struct.unpack_from("<HH", image, pos)
    if info_magic != _TLV_INFO_MAGIC or pos + info_len > len(image):
        raise ValueError("image TLV area is malformed")

    tlvs = {}
    end = pos + info_len
    pos += 4
    while pos + 4 <= end:
        tlv_type, tlv_len = struct.unpack_from("<BxH", image, pos)
        pos += 4
        tlvs[tlv_type] = (pos, tlv_len)
        pos += tlv_len
    return hdr_size, body_size, signed_len, tlvs


def _b0_hash(body: bytes) -> tuple[int, int] | None:
    """
    For a network core image body, return the firmware size and the offset of
    the SHA-256 that b0n checks it against; None for any other image.
    """
    for off in _FW_INFO_OFFSETS:
        if body[off : off + len(_FW_INFO_MAGIC)] == _FW_INFO_MAGIC:
            size = struct.unpack_from("<I", body, off + _FW_INFO_SIZE_OFFSET)[0]
            validation = (size + 3) // 4 * 4
            if body[validation : validation + len(_FW_VALIDATION_MAGIC)] != _FW_VALIDATION_MAGIC:
                raise ValueError("network core image has no validation info after its firmware")
            return size, validation + _FW_VALIDATION_HASH_OFFSET
    return None


def _signing_key():
    from cryptography.hazmat.primitives import serialization

    pem = resources.files(__package__).joinpath("keys", _SIGNING_KEY).read_bytes()
    return serialization.load_pem_private_key(pem, password=None)


def _pss():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=_RSA_PSS_SALT_LEN), hashes.SHA256()


class _Checked(NamedTuple):
    """Where patch_image writes, in an image check_image accepted."""

    key_off: int
    signed_len: int
    sha: tuple[int, int]
    sig: tuple[int, int]
    # (firmware start, firmware end, offset of its SHA-256) of a network core
    # image; None for any other image.
    b0: tuple[int, int, int] | None


def _check(image: bytes, key_offset: int, expected: bytes) -> _Checked:
    from cryptography.exceptions import InvalidSignature

    hdr_size, body_size, signed_len, tlvs = _image_layout(image)
    if _TLV_SHA256 not in tlvs or _TLV_RSA2048_PSS not in tlvs:
        raise ValueError("image is not signed with an RSA-2048 key")
    sha_off, sha_len = tlvs[_TLV_SHA256]
    sig_off, sig_len = tlvs[_TLV_RSA2048_PSS]

    key_off = hdr_size + key_offset
    if image[key_off : key_off + len(expected)] != expected:
        raise ValueError(
            "image bytes at the key do not match the ELF; "
            "the image and ELF are probably from different builds"
        )

    pss, sha256 = _pss()
    if hashlib.sha256(image[:signed_len]).digest() != image[sha_off : sha_off + sha_len]:
        raise ValueError("image SHA-256 does not verify before patching")
    try:
        _signing_key().public_key().verify(image[sig_off : sig_off + sig_len], image[:signed_len], pss, sha256)
    except InvalidSignature:
        raise ValueError("image is not signed with the MCUboot development key") from None

    b0 = None
    fw = _b0_hash(image[hdr_size : hdr_size + body_size])
    if fw is not None:
        fw_size, b0_hash_off = fw
        fw_end = hdr_size + fw_size
        b0_hash_off += hdr_size
        if key_off + len(expected) > fw_end:
            raise ValueError("key is outside the network core firmware")
        if hashlib.sha256(image[hdr_size:fw_end]).digest() != image[b0_hash_off : b0_hash_off + 32]:
            raise ValueError("network core firmware SHA-256 does not verify before patching")
        b0 = (hdr_size, fw_end, b0_hash_off)

    return _Checked(key_off, signed_len, (sha_off, sha_len), (sig_off, sig_len), b0)


def check_image(image: bytes, key_offset: int, expected: bytes) -> None:
    """
    Check that ``patch_image`` can patch a key into a signed MCUboot image.

    ``expected`` is what the ELF says is at ``key_offset``; the image must hold
    the same bytes there, which catches an ELF and image from different builds.

    Raises ValueError if the image disagrees with ``expected``, or its existing
    hashes or signature do not verify -- for the signature, that means it was
    not signed with the development key, and re-signing it would not change
    what its bootloader expects.
    """
    _check(image, key_offset, expected)


def patch_image(image: bytes, key_offset: int, expected: bytes, key: bytes) -> bytes:
    """
    Return a copy of a signed MCUboot image with ``key`` written at
    ``key_offset`` in its body, and its SHA-256 and signature updated (and the
    b0n SHA-256 of a network core image).

    Checks the image as ``check_image`` does first, and raises ValueError in
    the same cases.
    """
    if len(key) != len(expected):
        raise ValueError(f"key is {len(key)} bytes, but the firmware holds a {len(expected)}-byte key")
    checked = _check(image, key_offset, expected)
    (sha_off, sha_len), (sig_off, sig_len) = checked.sha, checked.sig

    out = bytearray(image)
    out[checked.key_off : checked.key_off + len(key)] = key
    if checked.b0 is not None:
        fw_start, fw_end, b0_hash_off = checked.b0
        out[b0_hash_off : b0_hash_off + 32] = hashlib.sha256(out[fw_start:fw_end]).digest()
    out[sha_off : sha_off + sha_len] = hashlib.sha256(out[: checked.signed_len]).digest()
    pss, sha256 = _pss()
    out[sig_off : sig_off + sig_len] = _signing_key().sign(bytes(out[: checked.signed_len]), pss, sha256)
    return bytes(out)


def read_dfu_zip(dfu_zip: bytes) -> dict[int, tuple[int, str, bytes]]:
    """
    Return (slot, file name, image) for each image in a DFU zip, by image
    index, in image index order.
    """
    with zipfile.ZipFile(io.BytesIO(dfu_zip)) as z:
        files = json.loads(z.read("manifest.json"))["files"]
        files.sort(key=lambda f: int(f["image_index"]))
        return {
            int(f["image_index"]): (int(f["slot_index_primary"]), f["file"], z.read(f["file"]))
            for f in files
        }


def find_device(usb_id: str) -> str | None:
    """Return the serial port of the USB device ``usb_id`` ("vid:pid", hex), if connected."""
    from serial.tools import list_ports

    vid, pid = (int(part, 16) for part in usb_id.split(":"))
    for port in list_ports.comports():
        if port.vid == vid and port.pid == pid:
            return port.device
    return None


async def _flash(images: list[tuple[int, str, bytes]], port: str, progress) -> None:
    from smp.error import MGMT_ERR
    from smpclient import SMPClient
    from smpclient.generics import error, error_v1
    from smpclient.requests.os_management import ResetWrite
    from smpclient.transport import SMPTransportDisconnected
    from smpclient.transport.serial import BufferSize, SMPSerialTransport

    transport = SMPSerialTransport(fragmentation_strategy=BufferSize(buf_size=_MCUBOOT_RX_BUF))
    async with SMPClient(transport, port) as client:
        for slot, name, data in images:
            async for offset in client.upload(
                data, slot=slot, first_timeout_s=_FIRST_CHUNK_TIMEOUT_S
            ):
                progress(name, offset, len(data))

        deadline = time.monotonic() + _RESET_TIMEOUT_S
        while True:
            try:
                response = await client.request(ResetWrite())
            except SMPTransportDisconnected:
                return  # rebooted before answering
            # MCUboot answers with only an rc, which smpclient parses as an
            # error response even when it is EOK.
            rc = response.rc if error_v1(response) else None
            if not error(response) or rc == MGMT_ERR.EOK:
                return
            if rc != MGMT_ERR.EBUSY:
                raise RuntimeError(f"MCUboot refused to reset: {response}")
            if time.monotonic() > deadline:
                raise RuntimeError(f"MCUboot still refused to reset after {_RESET_TIMEOUT_S:.0f}s: {response}")
            await asyncio.sleep(1.0)


@contextlib.contextmanager
def _quiet_smpclient():
    """
    Hide smpclient's log output. It logs two expected events as problems: MCUboot
    not answering the buffer size query (the upload uses a fixed buffer size
    instead), and the serial port going away when the board resets. Real
    failures are raised as exceptions.
    """
    logger = logging.getLogger("smpclient")
    level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(level)


def flash_images(images: list[tuple[int, str, bytes]], port: str, progress=lambda name, done, total: None) -> None:
    """
    Upload each (slot, file name, image) through MCUboot serial recovery on
    ``port``, then reset into the new firmware.

    ``progress(name, done, total)`` is called as each image uploads.
    """
    with _quiet_smpclient():
        asyncio.run(_flash(images, port, progress))
