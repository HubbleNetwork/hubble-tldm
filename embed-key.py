#!/usr/bin/env python3

"""
patch_elf_var.py — Patch a global/static variable's initial value in an ELF binary.

Examples:
  # Patch variable by symbol name (auto-size from symbol or specify --type)
  python embed-key.py firmware.elf --key my.key
"""

import argparse
import base64
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


def main():
    ap = argparse.ArgumentParser(
        description="Patch the master key in an ELF binary.")

    ap.add_argument("binary", help="Path to ELF binary to modify (in-place).")
    ap.add_argument(
        "--key", help="Path to file containing base64-encoded key data to embed", required=True)

    args = ap.parse_args()

    data = None

    with open(args.key, "rb") as f:
        data = base64.b64decode(f.read())

    with open(args.binary, "rb") as f:
        try:
            elf = ELFFile(f)
        except Exception as e:
            print(
                f"ERROR: Not a valid ELF binary or could not read ELF: {e}", file=sys.stderr)
            sys.exit(1)

        # Resolve symbol
        sym, sec = find_symbol(elf, "master_key")
        if sym is None:
            print(
                f"ERROR: Symbol master_key not found in .symtab/.dynsym (maybe stripped?).", file=sys.stderr)
            sys.exit(1)

        file_off = compute_file_offset(sym, sec)
        sym_size = int(sym['st_size']) or 0
        size_info = f"(section {sec.name}, sym size {sym_size} bytes, file off 0x{file_off:x})"

        if sym_size not in (0, len(data)):
            print(
                f"WARNING: symbol size is {sym_size} bytes, but --bytes length is {len(data)}.", file=sys.stderr)

    with open(args.binary, "r+b") as wf:
        wf.seek(file_off)
        wf.write(data)

    print(
        f"Patched '{args.binary}' at 0x{file_off:x} with {len(data)} bytes {size_info}.")
    print("Done.")


if __name__ == "__main__":
    main()
