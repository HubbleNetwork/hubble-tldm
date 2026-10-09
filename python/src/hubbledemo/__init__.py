# hubbledemo/__init__.py

from .elfmgr import flash_elf, patch_elf, probe_device, convert_elf_to_hex
from .espmgr import find_device as find_esp_device
from .espmgr import flash_image as flash_esp_image
from .espmgr import locate_key as locate_esp_key
from .espmgr import patch_image as patch_esp_image
from .cloud import fetch_artifact, fetch_metadata

__all__ = [
    "flash_elf",
    "fetch_artifact",
    "patch_elf",
    "probe_device",
    "fetch_metadata",
    "convert_elf_to_hex",
    "find_esp_device",
    "flash_esp_image",
    "locate_esp_key",
    "patch_esp_image",
]
