# hubbledemo/__init__.py

from .elfmgr import flash_elf, patch_elf, probe_device, convert_elf_to_hex
from .espmgr import find_device as find_esp_device
from .espmgr import flash_image as flash_esp_image
from .espmgr import locate_key as locate_esp_key
from .espmgr import patch_image as patch_esp_image
from .mcubootmgr import check_image as check_mcuboot_image
from .mcubootmgr import find_device as find_mcuboot_device
from .mcubootmgr import flash_images as flash_mcuboot_images
from .mcubootmgr import locate_key as locate_mcuboot_key
from .mcubootmgr import patch_image as patch_mcuboot_image
from .mcubootmgr import read_dfu_zip
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
    "check_mcuboot_image",
    "find_mcuboot_device",
    "flash_mcuboot_images",
    "locate_mcuboot_key",
    "patch_mcuboot_image",
    "read_dfu_zip",
]
