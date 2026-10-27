import hashlib
import io
import json
import struct
import zipfile

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from elftools.elf.elffile import ELFFile

from hubbledemo.mcubootmgr import _signing_key, check_image, locate_key, patch_image, read_dfu_zip

KEY = bytes(range(32))
# What the firmware initialises master_key to.
PLACEHOLDER = b"\x01" + b"\x00" * 31

HDR_SIZE = 0x200
# An image's code follows the MCUboot header. Initialised data is stored in
# flash after the code and copied to RAM.
FLASH_START = 0x10200
TEXT = b"\x11" * 0x100
DATA_ADDR = 0x20000000
KEY_OFFSET_IN_DATA = 8
DATA = b"\x22" * KEY_OFFSET_IN_DATA + PLACEHOLDER + b"\x33" * 24
BODY = TEXT + DATA
KEY_OFFSET = len(TEXT) + KEY_OFFSET_IN_DATA

PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)

# A network core firmware for b0n: fw_info at 0x200 with the firmware's size,
# then validation info with its SHA-256 at the next word.
FW_INFO_OFFSET = 0x200
NET_KEY_OFFSET = 0x300


def _net_body(firmware_end: int = 0x401) -> bytes:
    fw = bytearray(b"\x44" * firmware_end)
    fw[FW_INFO_OFFSET : FW_INFO_OFFSET + 20] = struct.pack(
        "<IIIII", 0x281EE6DE, 0x8FCEBB4C, 0x3502, 60, firmware_end
    )
    fw[NET_KEY_OFFSET : NET_KEY_OFFSET + len(PLACEHOLDER)] = PLACEHOLDER
    validation = struct.pack("<IIII", 0x281EE6DE, 0x86518483, 0x3502, 0x01008800)
    validation += hashlib.sha256(fw).digest() + b"\x55" * 96
    return bytes(fw.ljust((firmware_end + 3) // 4 * 4, b"\xff")) + validation


def _b0_hash_ok(image: bytes) -> bool:
    body = image[HDR_SIZE:]
    size = struct.unpack_from("<I", body, FW_INFO_OFFSET + 16)[0]
    validation = (size + 3) // 4 * 4
    return body[validation + 16 : validation + 48] == hashlib.sha256(body[:size]).digest()


def _signed_image(body: bytes, signing_key=None) -> bytes:
    """An MCUboot image laid out as imgtool signs it for RSA-2048."""
    signing_key = signing_key or _signing_key()
    header = struct.pack("<IIHHII", 0x96F3B83D, 0, HDR_SIZE, 0, len(body), 0).ljust(HDR_SIZE, b"\x00")
    signed = header + body
    public = signing_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.PKCS1
    )
    tlvs = b""
    for tlv_type, value in (
        (0x10, hashlib.sha256(signed).digest()),
        (0x01, hashlib.sha256(public).digest()),
        (0x20, signing_key.sign(signed, PSS, hashes.SHA256())),
    ):
        tlvs += struct.pack("<BxH", tlv_type, len(value)) + value
    return signed + struct.pack("<HH", 0x6907, 4 + len(tlvs)) + tlvs


def _elf() -> io.BytesIO:
    """
    A 32-bit ARM ELF with code at FLASH_START and master_key in initialised
    data, which runs at DATA_ADDR but is stored in flash right after the code.
    """
    shstrtab = b"\x00.text\x00.data\x00.symtab\x00.strtab\x00.shstrtab\x00"
    strtab = b"\x00master_key\x00"
    ehdr_len, phdr_len, shdr_len = 52, 32, 40
    text_off = ehdr_len + 2 * phdr_len
    data_off = text_off + len(TEXT)
    symtab_off = data_off + len(DATA)
    symtab = b"\x00" * 16 + struct.pack(
        "<IIIBBH", 1, DATA_ADDR + KEY_OFFSET_IN_DATA, len(PLACEHOLDER), 0x11, 0, 2
    )
    strtab_off = symtab_off + len(symtab)
    shstrtab_off = strtab_off + len(strtab)
    shoff = shstrtab_off + len(shstrtab)

    ehdr = b"\x7fELF\x01\x01\x01" + b"\x00" * 9 + struct.pack(
        "<HHIIIIIHHHHHH",
        2, 40, 1, FLASH_START, ehdr_len, shoff, 0x5000000, ehdr_len, phdr_len, 2, shdr_len, 6, 5,
    )
    phdrs = struct.pack("<8I", 1, text_off, FLASH_START, FLASH_START, len(TEXT), len(TEXT), 5, 4)
    phdrs += struct.pack(
        "<8I", 1, data_off, DATA_ADDR, FLASH_START + len(TEXT), len(DATA), len(DATA), 6, 4
    )
    shdrs = b"\x00" * shdr_len
    for name, sh_type, flags, addr, off, size, link, info, entsize in (
        (1, 1, 6, FLASH_START, text_off, len(TEXT), 0, 0, 0),
        (7, 1, 3, DATA_ADDR, data_off, len(DATA), 0, 0, 0),
        (13, 2, 0, 0, symtab_off, len(symtab), 4, 1, 16),
        (21, 3, 0, 0, strtab_off, len(strtab), 0, 0, 0),
        (29, 3, 0, 0, shstrtab_off, len(shstrtab), 0, 0, 0),
    ):
        shdrs += struct.pack("<10I", name, sh_type, flags, addr, off, size, link, info, 4, entsize)

    elf = ehdr + phdrs + TEXT + DATA + symtab + strtab + shstrtab + shdrs
    assert ELFFile(io.BytesIO(elf)).num_segments() == 2
    return io.BytesIO(elf)


def _verify(image: bytes) -> None:
    signed_len = HDR_SIZE + struct.unpack_from("<I", image, 12)[0]
    tlvs = image[signed_len + 4 :]
    assert tlvs[4:36] == hashlib.sha256(image[:signed_len]).digest()
    _signing_key().public_key().verify(tlvs[-256:], image[:signed_len], PSS, hashes.SHA256())


def test_locate_key_maps_initialised_data_to_its_place_in_flash():
    assert locate_key(_elf()) == (KEY_OFFSET, PLACEHOLDER)


def test_patched_image_hash_and_signature_verify():
    patched = patch_image(_signed_image(BODY), KEY_OFFSET, PLACEHOLDER, KEY)

    _verify(patched)
    assert patched[HDR_SIZE + KEY_OFFSET : HDR_SIZE + KEY_OFFSET + len(KEY)] == KEY


def test_patch_only_touches_key_hash_and_signature():
    image = _signed_image(BODY)
    patched = patch_image(image, KEY_OFFSET, PLACEHOLDER, KEY)

    changed = {i for i in range(len(image)) if image[i] != patched[i]}
    key_off = HDR_SIZE + KEY_OFFSET
    tlvs = HDR_SIZE + len(BODY) + 4
    allowed = (
        set(range(key_off, key_off + len(KEY)))
        | set(range(tlvs + 4, tlvs + 36))
        | set(range(len(image) - 256, len(image)))
    )
    assert changed and changed <= allowed


def test_rejects_image_from_another_build():
    with pytest.raises(ValueError, match="different builds"):
        patch_image(_signed_image(BODY), KEY_OFFSET, b"\x02" + b"\x00" * 31, KEY)


def test_rejects_image_signed_with_another_key():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValueError, match="development key"):
        patch_image(_signed_image(BODY, other), KEY_OFFSET, PLACEHOLDER, KEY)


def test_rejects_image_whose_hash_does_not_verify():
    image = bytearray(_signed_image(BODY))
    image[HDR_SIZE] ^= 0xFF
    with pytest.raises(ValueError, match="SHA-256"):
        patch_image(bytes(image), KEY_OFFSET, PLACEHOLDER, KEY)


def test_check_image_accepts_what_patch_image_accepts():
    check_image(_signed_image(BODY), KEY_OFFSET, PLACEHOLDER)
    check_image(_signed_image(_net_body()), NET_KEY_OFFSET, PLACEHOLDER)


def test_check_image_rejects_image_from_another_build():
    with pytest.raises(ValueError, match="different builds"):
        check_image(_signed_image(BODY), KEY_OFFSET, b"\x02" + b"\x00" * 31)


def test_rejects_key_of_wrong_length():
    with pytest.raises(ValueError, match="16 bytes"):
        patch_image(_signed_image(BODY), KEY_OFFSET, PLACEHOLDER, KEY[:16])


def test_signature_check_is_real():
    image = bytearray(patch_image(_signed_image(BODY), KEY_OFFSET, PLACEHOLDER, KEY))
    image[-1] ^= 0xFF
    with pytest.raises(InvalidSignature):
        _verify(bytes(image))


def test_read_dfu_zip_returns_images_by_index():
    manifest = {
        "files": [
            {"image_index": "1", "slot_index_primary": "3", "file": "cpunet.bin"},
            {"image_index": "0", "slot_index_primary": "1", "file": "app.signed.bin"},
        ]
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("cpunet.bin", b"net")
        z.writestr("app.signed.bin", b"app")

    images = read_dfu_zip(buf.getvalue())
    assert images == {0: (1, "app.signed.bin", b"app"), 1: (3, "cpunet.bin", b"net")}
    assert list(images) == [0, 1]


def test_network_core_image_b0_hash_is_updated():
    image = _signed_image(_net_body())
    assert _b0_hash_ok(image)

    patched = patch_image(image, NET_KEY_OFFSET, PLACEHOLDER, KEY)

    _verify(patched)
    assert _b0_hash_ok(patched)
    assert patched[HDR_SIZE + NET_KEY_OFFSET : HDR_SIZE + NET_KEY_OFFSET + len(KEY)] == KEY


def test_rejects_network_core_image_whose_b0_hash_does_not_verify():
    body = bytearray(_net_body())
    body[0] ^= 0xFF
    with pytest.raises(ValueError, match="network core firmware SHA-256"):
        patch_image(_signed_image(bytes(body)), NET_KEY_OFFSET, PLACEHOLDER, KEY)


def test_rejects_key_outside_network_core_firmware():
    body = _net_body() + PLACEHOLDER
    with pytest.raises(ValueError, match="outside the network core firmware"):
        patch_image(_signed_image(body), len(body) - len(PLACEHOLDER), PLACEHOLDER, KEY)
