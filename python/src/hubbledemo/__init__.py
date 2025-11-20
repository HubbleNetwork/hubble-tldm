# hubbledemo/__init__.py

from .elfmgr import flash_elf, patch_elf, probe_device, convert_elf_to_hex
from .cloud import fetch_elf, fetch_metadata

__all__ = [
    "flash_elf",
    "fetch_elf",
    "patch_elf",
    "probe_device",
    "fetch_metadata",
    "convert_elf_to_hex",
]
