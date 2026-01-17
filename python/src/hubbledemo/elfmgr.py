from __future__ import annotations

from hubblenetwork import Device

import io
import os
import base64
import time
import tempfile
import pylink
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from intelhex import IntelHex


def _compute_file_offset(sym, sec) -> int:
    return sec["sh_offset"] + (sym["st_value"] - sec["sh_addr"])


def _get_endianness_from_elf(buf: io.BytesIO) -> str:
    buf.seek(0)
    elf = ELFFile(buf)
    """Return 'little' or 'big' by inspecting the ELF header."""
    return "little" if elf.little_endian else "big"


def _find_symbol(elf: ELFFile, name: str):
    """Return (symbol, section) for a named symbol from .symtab or .dynsym."""
    for sec in elf.iter_sections():
        if not isinstance(sec, SymbolTableSection):
            continue
        for sym in sec.iter_symbols():
            if sym.name == name:
                shndx = sym["st_shndx"]
                if shndx == "SHN_UNDEF":
                    raise ValueError(f"Symbol '{name}' is undefined (imported).")
                if isinstance(shndx, str):
                    raise ValueError(
                        f"Symbol '{name}' has special section index {shndx}, cannot patch."
                    )
                target_sec = elf.get_section(shndx)
                if target_sec is None:
                    raise ValueError(f"Could not find section for symbol '{name}'.")
                if target_sec.name == "bss":
                    continue
                return sym, target_sec
    return None, None


def _patch_symbol(buf: io.BytesIO, data: bytes, symbol_name: str):
    buf.seek(0)
    elf = ELFFile(buf)

    # Resolve symbol
    sym, sec = _find_symbol(elf, symbol_name)
    if sym is None:
        raise ValueError(f"{symbol_name} not found in elf file")

    file_off = _compute_file_offset(sym, sec)
    sym_size = int(sym["st_size"]) or 0

    if sym_size not in (0, len(data)):
        raise ValueError(
            f"Symbol size is {sym_size} bytes, but {symbol_name} length is {len(data)}"
        )

    buf.seek(file_off)
    buf.write(data)


def patch_elf(buf: io.BytesIO, device: Device):
    _patch_symbol(buf, device.key, "master_key")

    endian = _get_endianness_from_elf(buf)
    utc_ms = int(time.time() * 1000)
    _patch_symbol(buf, utc_ms.to_bytes(8, endian, signed=False), "utc_time")


def _addr_for_segment(seg) -> int:
    """
    Choose a programming address for a PT_LOAD segment.
    Prefer physical address (p_paddr) if present, else virtual (p_vaddr).
    """
    try:
        paddr = int(seg["p_paddr"])
    except Exception:
        paddr = 0
    vaddr = int(seg["p_vaddr"])
    return paddr if paddr else vaddr


def _always_unsecure(title, msg, flags):
    # proceed with mass erase + unlock
    return pylink.enums.JLinkFlags.DLG_BUTTON_YES


def probe_device() -> bool:
    """Returns if any emulators are connected"""
    jlink = pylink.JLink(unsecure_hook=_always_unsecure)
    return jlink.num_connected_emulators() > 0


def flash_elf(buf: io.BytesIO, board: str, jlink_device) -> None:
    """
    Flash an ELF image (held in a BytesIO) to an nRF52832_xxAA using pylink.
    Creates a temporary .elf on disk (needed by jlink.flash_file) and deletes it afterwards.

    Args:
        buf: io.BytesIO positioned anywhere (we'll rewind it).
        board: board name

    Raises:
        ImportError: pylink not installed.
        RuntimeError: on J-Link connection or flashing failure.
    """
    speed_khz = 4000

    # Write the buffer to a real temp file so flash_file can read it (works on all OSes)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".elf") as tmp:
            tmp_path = tmp.name
            buf.seek(0)
            # Stream copy to avoid duplicating memory with getvalue()
            while True:
                chunk = buf.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
            tmp.flush()

        # jlink will silently fail post-mandated FW update of the jlink
        # for some devices due to a security dialog which pylink ignores.
        # This unsecure_hook just makes it accept the insecurity.
        jlink = pylink.JLink(unsecure_hook=_always_unsecure)

        try:
            jlink.open()
            jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
            jlink.connect(jlink_device, speed=speed_khz)

            jlink.halt()
            jlink.flash_file(tmp_path, addr=None)  # ELF contains its own load addresses
            jlink.reset()
        except Exception as e:
            raise RuntimeError(f"Flashing failed: {e}") from e
        finally:
            try:
                if jlink.opened():
                    jlink.close()
            except Exception:
                pass
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

def convert_elf_to_hex(buf: io.BytesIO, output_path: str):
    """
    Convert an ELF file to Intel HEX format.
    
    Args:
        buf: io.BytesIO containing the ELF file data
        output_path: Path where the .hex file will be written (include .hex extension)
    """
    ih = IntelHex()

    buf.seek(0)
    elf = ELFFile(buf)

    for segment in elf.iter_segments():
        if segment["p_type"] != "PT_LOAD":
            continue

        data = segment.data()
        # Prefer physical address if present, otherwise virtual
        addr = segment['p_paddr'] if segment['p_paddr'] != 0 else segment['p_vaddr']

        # Store bytes into IntelHex at the proper address
        for offset, b in enumerate(data):
            ih[addr + offset] = b

    # Ensure .hex extension if not provided
    if not output_path.endswith('.hex'):
        output_path = output_path + '.hex'
    
    ih.write_hex_file(output_path)
