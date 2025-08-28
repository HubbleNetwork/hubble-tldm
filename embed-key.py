#!/usr/bin/env python3

"""
patch_elf_var.py — Patch a global/static variable's initial value in an ELF binary.

Examples:
  # Patch variable by symbol name (auto-size from symbol or specify --type)
  python embed-key.py firmware.elf --key my.key
"""

import argparse
import base64
import time
import os
import sys

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection


def find_symbol(elf: ELFFile, name: str):
    """Return (symbol, section) for a named symbol from .symtab or .dynsym."""
    for sec in elf.iter_sections():
        if not isinstance(sec, SymbolTableSection):
            continue
        for sym in sec.iter_symbols():
            if sym.name == name:
                shndx = sym['st_shndx']
                if shndx == 'SHN_UNDEF':
                    raise ValueError(
                        f"Symbol '{name}' is undefined (imported).")
                if isinstance(shndx, str):
                    raise ValueError(
                        f"Symbol '{name}' has special section index {shndx}, cannot patch.")
                target_sec = elf.get_section(shndx)
                if target_sec is None:
                    raise ValueError(
                        f"Could not find section for symbol '{name}'.")
                if target_sec.name == 'bss':
                    continue
                return sym, target_sec
    return None, None


def compute_file_offset(sym, sec) -> int:
    return sec['sh_offset'] + (sym['st_value'] - sec['sh_addr'])

def get_endianness_from_elf(elf_path: str) -> str:
    """Return 'little' or 'big' by inspecting the ELF header."""
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        return 'little' if elf.little_endian else 'big'

def patch_data(elf_file_path: str, data: bytes, symbol_name: str = "master_key") -> int:
    with open(elf_file_path, "rb") as f:
        try:
            elf = ELFFile(f)
        except Exception as e:
            print(
                f"[ERROR] Not a valid ELF binary or could not read ELF: {e}", file=sys.stderr)
            return 1

        # Resolve symbol
        sym, sec = find_symbol(elf, symbol_name)
        if sym is None:
            print(
                f"[ERROR] Symbol {symbol_name} not found in .symtab/.dynsym (maybe stripped?).", file=sys.stderr)
            return 1

        file_off = compute_file_offset(sym, sec)
        sym_size = int(sym['st_size']) or 0
        size_info = f"(section {sec.name}, sym size {sym_size} bytes, file off 0x{file_off:x})"

        if sym_size not in (0, len(data)):
            print(
                f"[ERROR] symbol size is {sym_size} bytes, but {symbol_name} length is {len(data)}.", file=sys.stderr)
            return 1

    with open(elf_file_path, "r+b") as wf:
        wf.seek(file_off)
        wf.write(data)

    print(
        f"[SUCCESS] Patched '{elf_file_path}' at 0x{file_off:x} with {len(data)} bytes {size_info}.")

    return 0

def main():
    ap = argparse.ArgumentParser(
        description="Patch the master key and utc time (ms) in an ELF binary.")

    ap.add_argument("binary", help="Path to ELF binary to modify (in-place).")
    ap.add_argument(
        "--key", help="The base64-encoded key", required=True)

    args = ap.parse_args()

    data = None

    # Process key data
    try:
        data = base64.b64decode(args.key)
        print(f"[INFO] Key size: {len(data)} bytes")
        
    except base64.binascii.Error as e:
        print(f"[ERROR] Error decoding base64 key: {e}", file=sys.stderr)
        sys.exit(1)

    # patch the key
    err = patch_data(args.binary, data, symbol_name="master_key")
    if err != 0:
        sys.exit(err)

    # patch the time
    endian = get_endianness_from_elf(args.binary)
    utc_ms = int(time.time() * 1000)
    err = patch_data(args.binary, utc_ms.to_bytes(8, endian, signed=False), symbol_name="utc_time")
    if err != 0:
        sys.exit(err)

if __name__ == "__main__":
    main()
