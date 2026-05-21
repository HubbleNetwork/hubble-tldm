# Hubble Demo Script

This will enable you to flash a pre-determined set of boards and provision them with your credentials.

## Testing

Run all commands from `python/`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                 # smoke tests only; the e2e test is skipped
```

### End-to-end test (hardware required)

`tests/test_e2e.py` flashes a connected board, BLE-scans + ingests
packets via `pyhubblenetwork`, then queries the backend by device ID. It
is gated behind the `integration` and `ble` markers so it never runs by
accident.

Set `HUBBLE_ORG_ID` and `HUBBLE_API_TOKEN` (in your shell, or copy
`.env.example` to `.env` in `python/` or the repo root — loaded via
`python-dotenv`), pick a board ID from `merge/md.json`, plug it in,
then:

```bash
export HUBBLE_TEST_BOARD=nrf52dk
pytest -s -m integration tests/test_e2e.py -v
```

`-s` is required because TI `generate-hex` boards (`lp_em_cc2340r5`,
`lp_em_cc2340r53`, `lp_em_cc2755p10`) emit a `.hex` and the test pauses to ask you to flash
it manually before continuing.

#### Testing a locally-built ELF

To exercise an ELF you just built (instead of the prebuilt one in
`merge/`), point `HUBBLE_TEST_ELF_FILE` at it. The test forwards this
through to `hubbledemo flash` via the `HUBBLE_DEMO_ELF_FILE` override:

```bash
export HUBBLE_TEST_BOARD=nrf52dk
export HUBBLE_TEST_ELF_FILE=../firmware/zephyr/hubble-demo-app/build/zephyr/zephyr.elf
pytest -s -m integration tests/test_e2e.py -v
```

#### Tunables

| Env var | Default | Purpose |
|---|---|---|
| `HUBBLE_TEST_BOARD` | — | Board ID; test is skipped if unset |
| `HUBBLE_TEST_ELF_FILE` | — | Local ELF path; uses remote `merge/<board>.elf` if unset |
| `HUBBLE_TEST_SCAN_TIMEOUT` | `90` | Seconds to scan for BLE packets |
| `HUBBLE_TEST_SCAN_COUNT` | `3` | Stop scanning after N packets |
| `HUBBLE_TEST_INGEST_WAIT` | `45` | Seconds to wait for backend propagation before querying |
| `HUBBLE_TEST_DEVICE_NAME` | auto | `--name` for the registered device |

## Releasing

Releases are triggered by pushing a `vX.Y.Z` tag. The
`.github/workflows/release.yml` workflow then runs lint + tests, builds
sdist + wheel, creates a GitHub Release using `release-notes.md` as the
body, and publishes to PyPI via OIDC trusted publishing.

### One-time setup

1. **PyPI Trusted Publisher** — at
   <https://pypi.org/manage/project/pyhubbledemo/settings/publishing/>,
   add a publisher with:
   - Owner: `HubbleNetwork`
   - Repository: `hubble-tldm`
   - Workflow filename: `release.yml`
   - Environment name: `pypi`
2. **GitHub Environment** — in repo Settings → Environments, create an
   environment named `pypi`. Optionally add a required-reviewer rule so
   each publish needs manual approval.

### Cutting a release

Run all commands from the repo root.

1. **Bump the version** in `python/pyproject.toml` (`project.version`).
   The git tag must exactly match this string with a `v` prefix.
2. **Update `python/release-notes.md`** — prepend a new section under
   `# Release Notes`:
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD

   ### Added
   - feat(...): ...

   ### Fixed
   - fix(...): ...
   ```
   The full file is dumped as the GitHub Release body, so keep it
   readable.
3. **Commit and tag**:
   ```bash
   git add python/pyproject.toml python/release-notes.md
   git commit -m "chore: release X.Y.Z"
   git tag vX.Y.Z
   git push origin master
   git push origin vX.Y.Z
   ```
4. **Approve the publish step** — if you enabled the reviewer gate on
   the `pypi` environment, the workflow will pause before pushing to
   PyPI until you approve it in the Actions UI.

Watch progress at
<https://github.com/HubbleNetwork/hubble-tldm/actions>.