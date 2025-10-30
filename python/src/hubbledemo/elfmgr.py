from __future__ import annotations

from hubblenetwork import Device

import io
import os
import base64
import requests
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Optional
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection


_ELF_BASE_URL = (
    "https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/master/merge"
)

# Map boards to OpenOCD config files
# These boards work with both J-Link and CMSIS-DAP probes
_BOARD_TO_OPENOCD_CFG: Dict[str, list[str]] = {
    "nrf52dk": ["target/nrf52.cfg"],
    "nrf52840dk": ["target/nrf52.cfg"],
    "nrf21540dk": ["target/nrf52.cfg"],
    "xg24_ek2703a": ["target/efm32.cfg"],
    "xg22_ek4108a": ["target/efm32.cfg"],
}

# Supported debug interface configs (in order of preference)
_DEBUG_INTERFACES = [
    "interface/jlink.cfg",
    "interface/cmsis-dap.cfg",
]


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
    _patch_symbol(buf, base64.b64decode(device.key), "master_key")

    endian = _get_endianness_from_elf(buf)
    utc_ms = int(time.time() * 1000)
    _patch_symbol(buf, utc_ms.to_bytes(8, endian, signed=False), "utc_time")


def probe_device() -> bool:
    """
    Check if a debug probe (J-Link or CMSIS-DAP) is connected using OpenOCD.
    
    Returns:
        bool: True if a debug probe is detected, False otherwise.
    """
    # Try each supported interface
    for interface in _DEBUG_INTERFACES:
        try:
            result = subprocess.run(
                [
                    "openocd",
                    "-f", interface,
                    "-c", "transport select swd",
                    "-c", "adapter speed 4000",
                    "-c", "init",
                    "-c", "exit"
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        except Exception:
            continue
    
    return False


def flash_elf(buf: io.BytesIO, board: str) -> None:
    """
    Flash an ELF image (held in a BytesIO) to a target board using OpenOCD.
    Creates a temporary .elf on disk and deletes it afterwards.
    Automatically detects J-Link or CMSIS-DAP debug probes.

    Args:
        buf: io.BytesIO positioned anywhere (we'll rewind it).
        board: board name (e.g., 'nrf52dk', 'nrf52840dk', 'xg24_ek2703a')

    Raises:
        ValueError: if board is not supported.
        RuntimeError: on OpenOCD connection or flashing failure.
    """
    board_key = board.strip().lower()
    target_configs = _BOARD_TO_OPENOCD_CFG.get(board_key)
    
    if not target_configs:
        raise ValueError(
            f"Unsupported board: {board}. "
            f"Supported boards: {', '.join(_BOARD_TO_OPENOCD_CFG.keys())}"
        )

    # Write the buffer to a temporary file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".elf") as tmp:
            tmp_path = tmp.name
            buf.seek(0)
            tmp.write(buf.read())
            tmp.flush()

        # Try each debug interface until one works
        errors = []
        for interface in _DEBUG_INTERFACES:
            # Build OpenOCD command with correct order:
            # 1. Load interface
            # 2. Configure transport and speed BEFORE target
            # 3. Load target
            # 4. Init and flash
            cmd = [
                "openocd",
                "-f", interface,
                "-c", "transport select swd",
                "-c", "adapter speed 4000"
            ]
            for cfg in target_configs:
                cmd.extend(["-f", cfg])
            cmd.extend([
                "-c", "init",
                "-c", "targets",
                "-c", "reset halt",
                "-c", f"flash write_image erase {tmp_path}",
                "-c", "reset run",
                "-c", "exit"
            ])

            # Execute OpenOCD
            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                # Success! Return without trying other interfaces
                return
            except subprocess.CalledProcessError as e:
                # Save error and try next interface
                interface_name = interface.split('/')[-1].replace('.cfg', '')
                errors.append({
                    'interface': interface_name,
                    'cmd': ' '.join(cmd),
                    'returncode': e.returncode,
                    'stderr': e.stderr
                })
                continue
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(f"OpenOCD flashing timed out after 30 seconds") from e
            except FileNotFoundError as e:
                raise RuntimeError(
                    "OpenOCD not found. Please install OpenOCD:\n"
                    "  macOS: brew install openocd\n"
                    "  Linux: sudo apt-get install openocd\n"
                    "  Windows: https://openocd.org/pages/getting-openocd.html"
                ) from e

        # If we get here, all interfaces failed
        if errors:
            error_details = "\n\n".join([
                f"Interface: {err['interface']}\n"
                f"Return code: {err['returncode']}\n"
                f"Error: {err['stderr'].strip()}"
                for err in errors
            ])
            raise RuntimeError(
                f"OpenOCD flashing failed with all interfaces:\n\n{error_details}"
            )
        else:
            raise RuntimeError("No compatible debug probe found")

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def fetch_elf(board: str, timeout: float = 20.0) -> io.BytesIO:
    """
    Download the board-specific ELF from HubbleNetwork/hubble-tldm/merge and
    return it as an io.BytesIO.

    Parameters
    ----------
    board_name : str
        Board identifier (e.g. 'nrf21540dk', 'xg24_ek2703a', 'xg22_ek4108a').
    timeout : float
        Requests timeout in seconds (connect + read).

    Returns
    -------
    io.BytesIO
        Raw bytes of the .elf file

    Raises
    ------
    ValueError
        If the board is not supported or name is malformed.
    FileNotFoundError
        If the expected ELF file does not exist in the merge directory.
    ConnectionError
        On network, HTTP, or parsing failures.
    """
    if not isinstance(board, str) or not board.strip():
        raise ValueError("board must be a non-empty string")

    # If we have a local override, just use that
    local_file = os.getenv("HUBBLE_DEMO_ELF_FILE")
    if local_file:
        return io.BytesIO(Path(local_file).read_bytes())

    # Give option (for development) to pull binary from elsewhere
    val = os.getenv("HUBBLE_DEMO_ELF_URL_OVERRIDE")
    if val:
        base_url = val
    else:
        base_url = _ELF_BASE_URL

    url = f"{base_url}/{board}.elf"

    _RETRY_STATUS = {429, 500, 502, 503, 504}
    retries = 5
    backoff = 1.0  # Initial backoff time in seconds

    last_err: Optional[Exception] = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            resp = requests.get(url, timeout=timeout)

            if resp.status_code == 404:
                # Not found is definitive; don't bother retrying
                raise FileNotFoundError(f"No ELF for board '{board}' at {url}")

            # Retry transient status codes (unless it's the final attempt)
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                sleep_s = backoff * (2 ** (attempt - 1))
                time.sleep(sleep_s)
                continue

            # Raise for other non-OK codes
            resp.raise_for_status()

            # Basic sanity checks: content-type and size
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "html" in ctype:
                raise ValueError(f"Expected ELF bytes, got {ctype} from {url}")

            return io.BytesIO(resp.content)

        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt < retries:
                sleep_s = backoff * (2 ** (attempt - 1))
                time.sleep(sleep_s)
                continue
            raise ConnectionError(f"Failed to download ELF from {url}: {e}") from e

        except Exception as e:
            raise

    # Should not reach here; defensive:
    raise ConnectionError(f"Failed to download ELF from {url}: {last_err}")
