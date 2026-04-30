"""End-to-end test: flash a board, scan + ingest BLE packets, query backend.

Drives the user's full pipeline as black-box subprocesses against the
installed `hubbledemo` and `hubblenetwork` console scripts. Skips unless
`HUBBLE_TEST_BOARD`, `HUBBLE_ORG_ID`, and `HUBBLE_API_TOKEN` are set
(env or .env via conftest).

Run:
    cd python
    export HUBBLE_TEST_BOARD=nrf52dk     # or any board id from merge/md.json
    pytest -s -m integration tests/test_e2e.py -v

To test a locally-built ELF instead of the prebuilt one in merge/:
    export HUBBLE_TEST_ELF_FILE=/path/to/local.elf
    pytest -s -m integration tests/test_e2e.py -v

`-s` is required so the manual-flash prompt for TI generate-hex boards
can read from stdin.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple

import pytest


DEVICE_ID_RE = re.compile(r"Device ID:\s*(\S+)")
DEVICE_KEY_RE = re.compile(r"Device Key:\s*(\S+)")


def _run(cmd: list[str], extra_env: dict | None = None, **kwargs) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    env = None
    if extra_env:
        env = {**os.environ, **extra_env}
        for k, v in extra_env.items():
            print(f"  (with {k}={v})", flush=True)
    proc = subprocess.run(
        cmd,
        check=False,
        text=True,
        capture_output=True,
        env=env,
        **kwargs,
    )
    if proc.stdout:
        print(proc.stdout, flush=True)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, flush=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''} exited "
            f"{proc.returncode}"
        )
    return proc


def _parse_flash_output(stdout: str) -> Tuple[str, str]:
    id_match = DEVICE_ID_RE.search(stdout)
    key_match = DEVICE_KEY_RE.search(stdout)
    if not id_match or not key_match:
        raise AssertionError(
            "Could not parse Device ID / Device Key from hubbledemo flash "
            "stdout. Did the output format change? See cli.py:120-121."
        )
    return id_match.group(1), key_match.group(1)


def _board_method(board: str) -> str:
    import hubbledemo

    metadata = hubbledemo.fetch_metadata()
    if board not in metadata:
        raise AssertionError(
            f"Board {board!r} not in metadata. Valid: {sorted(metadata)}"
        )
    return metadata[board]["method"]


@pytest.mark.integration
@pytest.mark.ble
def test_flash_scan_ingest_get_packets(tmp_path):
    board = os.getenv("HUBBLE_TEST_BOARD")
    org_id = os.getenv("HUBBLE_ORG_ID")
    token = os.getenv("HUBBLE_API_TOKEN")
    if not board:
        pytest.skip("HUBBLE_TEST_BOARD not set")
    if not org_id or not token:
        pytest.skip("HUBBLE_ORG_ID / HUBBLE_API_TOKEN not set")

    if not shutil.which("hubbledemo"):
        pytest.skip("hubbledemo console script not on PATH (pip install -e .)")
    if not shutil.which("hubblenetwork"):
        pytest.skip("hubblenetwork console script not on PATH")

    scan_timeout = int(os.getenv("HUBBLE_TEST_SCAN_TIMEOUT", "90"))
    scan_count = int(os.getenv("HUBBLE_TEST_SCAN_COUNT", "3"))
    ingest_wait = int(os.getenv("HUBBLE_TEST_INGEST_WAIT", "45"))
    device_name = os.getenv("HUBBLE_TEST_DEVICE_NAME", f"e2e-{int(time.time())}")

    elf_env = os.getenv("HUBBLE_TEST_ELF_FILE")
    elf_path = Path(elf_env).expanduser().resolve() if elf_env else None
    if elf_path:
        if not elf_path.is_file():
            pytest.fail(f"HUBBLE_TEST_ELF_FILE does not exist: {elf_path}")
        print(f"[TEST] Using local ELF: {elf_path}")
    else:
        print(f"[TEST] Using remote ELF for board {board} (merge/{board}.elf)")

    is_ti_hex = _board_method(board) == "generate-hex"

    _run(["hubblenetwork", "validate-credentials"])

    flash_cmd = [
        "hubbledemo", "flash", board,
        "-o", org_id,
        "-t", token,
        "-n", device_name,
    ]
    if is_ti_hex:
        hex_path = tmp_path / f"{device_name}.hex"
        flash_cmd += ["-f", str(hex_path)]

    flash_env = {"HUBBLE_DEMO_ELF_FILE": str(elf_path)} if elf_path else None
    flash_proc = _run(flash_cmd, extra_env=flash_env)
    device_id, device_key = _parse_flash_output(flash_proc.stdout)

    assert device_id, "empty Device ID"
    key_bytes = base64.b64decode(device_key)
    assert len(key_bytes) in (16, 32), (
        f"Device Key decoded to {len(key_bytes)} bytes; expected 16 or 32"
    )
    print(f"\n[TEST] Device ID:  {device_id}")
    print(f"[TEST] Device Key: {device_key} ({len(key_bytes)} bytes)")

    if is_ti_hex:
        print(
            f"\n[ACTION REQUIRED] Flash {hex_path} to your TI board, "
            "then press Enter to continue..."
        )
        input()

    print("[TEST] Waiting 10s for device to start transmitting...")
    time.sleep(10)

    scan_proc = _run([
        "hubblenetwork", "ble", "scan",
        "--key", device_key,
        "--counter-mode", "DEVICE_UPTIME",
        "--ingest",
        "--count", str(scan_count),
        "--timeout", str(scan_timeout),
        "--format", "json",
    ])
    scanned = json.loads(scan_proc.stdout)
    assert isinstance(scanned, list), f"expected JSON array, got {type(scanned)}"
    assert len(scanned) >= 1, (
        f"BLE scan captured 0 packets in {scan_timeout}s. "
        "Check the board is powered, advertising, and within range."
    )
    print(f"[TEST] Scanned + ingested {len(scanned)} packet(s)")

    print(f"[TEST] Waiting {ingest_wait}s for backend to surface packets...")
    time.sleep(ingest_wait)

    packets_proc = _run([
        "hubblenetwork", "org", "get-packets", device_id,
        "-o", "json",
        "--days", "1",
    ])
    queried = json.loads(packets_proc.stdout)
    assert isinstance(queried, list), f"expected JSON array, got {type(queried)}"
    assert len(queried) >= 1, (
        f"get-packets returned 0 packets for device {device_id} after "
        f"ingesting {len(scanned)}. Backend latency may exceed "
        f"HUBBLE_TEST_INGEST_WAIT={ingest_wait}s; try raising it."
    )
    print(f"[TEST] Backend returned {len(queried)} packet(s) for {device_id}")
