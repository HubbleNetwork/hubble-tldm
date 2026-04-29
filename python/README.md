# Hubble Demo Script

This will enable you to flash a pre-determined set of boards and provision them with your credentials.

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