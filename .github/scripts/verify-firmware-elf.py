"""Pre-publish check that an ELF satisfies the hubbledemo patching contract.

Mirrors the symbol lookup in python/src/hubbledemo/elfmgr.py::_find_symbol —
if a built ELF passes here, hubbledemo flash will be able to patch it.
"""

from __future__ import annotations

import sys

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

REQUIRED_SYMBOLS = ("master_key",)


def find_symbol(elf: ELFFile, name: str):
    for sec in elf.iter_sections():
        if not isinstance(sec, SymbolTableSection):
            continue
        for sym in sec.iter_symbols():
            if sym.name != name:
                continue
            shndx = sym["st_shndx"]
            if shndx == "SHN_UNDEF":
                raise SystemExit(f"{name}: undefined (imported)")
            if isinstance(shndx, str):
                raise SystemExit(f"{name}: special section index {shndx}")
            target = elf.get_section(shndx)
            if target is None:
                raise SystemExit(f"{name}: section index {shndx} not resolvable")
            if target.name == "bss":
                continue
            return sym, target
    raise SystemExit(f"{name}: not found in .symtab or .dynsym")


def main(path: str) -> None:
    with open(path, "rb") as f:
        elf = ELFFile(f)
        for name in REQUIRED_SYMBOLS:
            sym, sec = find_symbol(elf, name)
            size = int(sym["st_size"])
            if size == 0:
                raise SystemExit(f"{name}: zero size")
            print(f"  {name}: {size} bytes in {sec.name} @ 0x{sym['st_value']:08x}")
    print(f"{path}: OK")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify-firmware-elf.py <elf>")
    main(sys.argv[1])
