from typing import Optional, Any
import io
import os
import requests
import json
import time
from pathlib import Path

_ARTIFACT_BASE_URL = (
    "https://raw.githubusercontent.com/HubbleNetwork/hubble-tldm/master/merge"
)

_METADATA_FILENAME = "md.json"

def fetch_elf(board: str, timeout: float = 20.0) -> io.BytesIO:
    """
    Download the board-specific ELF from HubbleNetwork/hubble-tldm/merge and
    return it as an io.BytesIO.

    Parameters
    ----------
    board : str
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
    return _fetch_artifact(board, "elf")


def fetch_bin(board: str, timeout: float = 20.0) -> io.BytesIO:
    """
    Download the board-specific binary from HubbleNetwork/hubble-tldm/merge and
    return it as an io.BytesIO.

    Parameters
    ----------
    board : str
        Board identifier (e.g. 'nrf21540dk', 'xg24_ek2703a', 'xg22_ek4108a').
    timeout : float
        Requests timeout in seconds (connect + read).

    Returns
    -------
    io.BytesIO
        Raw bytes of the .bin file

    Raises
    ------
    ValueError
        If the board is not supported or name is malformed.
    FileNotFoundError
        If the expected .bin file does not exist in the merge directory.
    ConnectionError
        On network, HTTP, or parsing failures.
    """
    return _fetch_artifact(board, "bin")


def _fetch_artifact(board: str, ext: str) -> io.BytesIO:
    """
    Tool to fetch a board-specific artifact from the merge directory.

    Parameters
    ----------
    board : str
        Board identifier (e.g. 'nrf21540dk', 'xg24_ek2703a', 'xg22_ek4108a').
    ext : str
        Artifact extension (e.g. 'elf', 'bin').

    Returns
    -------
    io.BytesIO
        Raw bytes of the artifact

    Raises
    ------
    ValueError
        If the board is not supported or name is malformed.
    FileNotFoundError
        If the expected artifact does not exist in the merge directory.
    ConnectionError
        On network, HTTP, or parsing failures.
    """
    if not isinstance(board, str) or not board.strip():
        raise ValueError("board must be a non-empty string")

    # If we have a local override, just use that. It names the ELF; other
    # artifacts sit next to it with the same stem, as they do in merge/.
    local_file = os.getenv("HUBBLE_DEMO_ELF_FILE")
    if local_file:
        path = Path(local_file)
        if ext != "elf":
            path = path.with_suffix(f".{ext}")
        return io.BytesIO(path.read_bytes())

    # Give option (for development) to pull binary from elsewhere
    val = os.getenv("HUBBLE_DEMO_URL_OVERRIDE")
    if val:
        base_url = val
    else:
        base_url = _ARTIFACT_BASE_URL

    url = f"{base_url}/{board}.{ext}"
    kind = ext.upper()

    _RETRY_STATUS = {429, 500, 502, 503, 504}
    retries = 5

    last_err: Optional[Exception] = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            resp = requests.get(url, timeout=5)

            if resp.status_code == 404:
                # Not found is definitive; don't bother retrying
                raise FileNotFoundError(f"No {kind} for board '{board}' at {url}")

            # Retry transient status codes (unless it's the final attempt)
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                sleep_s = (2 ** (attempt - 1))
                time.sleep(sleep_s)
                continue

            # Raise for other non-OK codes
            resp.raise_for_status()

            # Basic sanity checks: content-type and size
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "html" in ctype:
                raise ValueError(f"Expected {kind} bytes, got {ctype} from {url}")

            return io.BytesIO(resp.content)

        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt < retries:
                sleep_s = (2 ** (attempt - 1))
                time.sleep(sleep_s)
                continue
            raise ConnectionError(f"Failed to download {kind} from {url}: {e}") from e

        except Exception:
            raise

    # Should not reach here; defensive:
    raise ConnectionError(f"Failed to download {kind} from {url}: {last_err}")

def fetch_metadata() -> Any:
    """
    Downloads the metadata about devices and returns it
    """
    # If we have a local override, just use that
    local_file = os.getenv("HUBBLE_DEMO_METADATA_FILE")
    if local_file:
        with open(local_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # Give option (for development) to pull binary from elsewhere
    val = os.getenv("HUBBLE_DEMO_URL_OVERRIDE")
    if val:
        base_url = val
    else:
        base_url = _ARTIFACT_BASE_URL

    url = f"{base_url}/{_METADATA_FILENAME}"

    _RETRY_STATUS = {429, 500, 502, 503, 504}
    retries = 5

    last_err: Optional[Exception] = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            resp = requests.get(url, timeout=5)

            if resp.status_code == 404:
                # Not found is definitive; don't bother retrying
                raise FileNotFoundError("No metadata file found for devices")

            # Retry transient status codes (unless it's the final attempt)
            if resp.status_code in _RETRY_STATUS and attempt < retries:
                sleep_s = 2 ** (attempt - 1)
                time.sleep(sleep_s)
                continue

            # Raise for other non-OK codes
            resp.raise_for_status()

            return json.loads(resp.text)

        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            if attempt < retries:
                sleep_s = (2 ** (attempt - 1))
                time.sleep(sleep_s)
                continue
            raise ConnectionError(f"Failed to download metadata file from {url}: {e}") from e

        except Exception:
            raise

    # Should not reach here; defensive:
    raise ConnectionError(f"Failed to download metadata from {url}: {last_err}")
