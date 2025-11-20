from __future__ import annotations
from typing import Optional
import click
import os
import petname
import hubbledemo
from hubblenetwork import Organization


def _get_env_or_fail(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise click.ClickException(f"[ERROR] {name} environment variable not set")
    return val


def _get_org_and_token(org_id, token) -> tuple[str, str]:
    """
    Helper function that checks if the given token and/or org
    are None and gets the env var if not
    """
    if not token:
        token = _get_env_or_fail("HUBBLE_API_TOKEN")
    if not org_id:
        org_id = _get_env_or_fail("HUBBLE_ORG_ID")
    return org_id, token


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Hubble SDK CLI."""
    # top-level group; subcommands are added below


@cli.command("probe")
def probe() -> None:
    if hubbledemo.probe_device():
        click.echo("[SUCCESS] Device detected.")
    else:
        click.secho(
            "[ERROR] Failed to connect to device. Check your connection.",
            fg="red",
            err=True,
        )
        return 2


@cli.command("flash")
@click.argument("board", type=str)
@click.option(
    "--org-id",
    "-o",
    type=str,
    default=None,
    show_default=False,
    help="Organization ID (if not using HUBBLE_ORG_ID env var)",
)
@click.option(
    "--token",
    "-t",
    type=str,
    default=None,
    show_default=False,  # show default in --help
    help="Token (if not using HUBBLE_API_TOKEN env var)",
)
def flash(board: str, name: str = None, org_id: str = None, token: str = None) -> None:
    click.secho("[INFO] Getting metadata... ", nl=False)
    metadata = hubbledemo.fetch_metadata()
    click.secho("[SUCCESS]")

    if board not in metadata:
        click.secho("[ERROR] Unsupported board selected!", fg="red",err=True)
        return 2

    # If using jlink, we want to make sure early on that a device is connected
    if metadata[board]["method"] == "jlink-flash" and not hubbledemo.probe_device():
        click.secho(
            "[ERROR] Failed to connect to device. Check your connection.",
            fg="red",
            err=True,
        )
        return 2

    org_id, token = _get_org_and_token(org_id, token)
    org = Organization(org_id=org_id, api_token=token)

    click.secho("[INFO] Organization info acquired:")
    click.secho(f"\tID: {org.credentials.org_id}")
    click.secho(f"\tName: {org.name}")
    click.secho(f"\tEnvironment: {org.env.name}")

    click.secho('[INFO] Registering new device"... ', nl=False)
    device = org.register_device(encryption=metadata[board]["encryption"] if "encryption" in metadata[board] else None)
    click.secho("[SUCCESS]")
    click.secho(f"\tDevice ID:  {device.id}")
    click.secho(f"\tDevice Key: {device.key}")

    if not name:
        name = petname.generate(words=3)
        click.secho(f'[INFO] No name supplied. Naming device "{name}"')
    click.secho("[INFO] Setting device name... ", nl=False)
    org.set_device_name(device_id=device.id, name=name)
    click.secho("[SUCCESS]")

    click.secho(f"[INFO] Retrieving binary for {board}... ", nl=False)
    buf = hubbledemo.fetch_elf(board=board)
    click.secho("[SUCCESS]")

    click.secho("[INFO] Patching key + UTC into binary... ", nl=False)
    hubbledemo.patch_elf(buf, device)
    click.secho("[SUCCESS]")

    # Depending on method, deliver how we will do provisioning.
    if metadata[board]["method"] == "jlink-flash":
        click.secho("[INFO] Flashing binary onto device... ", nl=False)
        hubbledemo.flash_elf(board=board, buf=buf, jlink_device=metadata["jlink_device"])
        click.secho("[SUCCESS]")

        click.secho(f"\n{board} successfully flashed and provisioned!")
    elif metadata[board]["method"] == "generate-hex":
        click.secho("[INFO] Generating hex file... ", nl=False)
        hubbledemo.convert_elf_to_hex(buf=buf, filename=name)
        click.secho("[SUCCESS]")
        click.secho(
            f"\nHex file written to \"{os.getcwd()}/{name}.hex\"",
            bg='blue', fg='white')
    else:
        click.secho(
            "[ERROR] Unknown method for provisioning board.",
            fg="red",
            err=True,
        )
        return 2

def main(argv: Optional[list[str]] = None) -> int:
    """
    Entry point used by console_scripts.

    Returns a process exit code instead of letting Click call sys.exit for easier testing.
    """
    try:
        # standalone_mode=False prevents Click from calling sys.exit itself.
        cli.main(args=argv, prog_name="hubbledemo", standalone_mode=False)
    except SystemExit as e:
        return int(e.code)
    except Exception as e:  # safety net to avoid tracebacks in user CLI
        click.secho(f"Unexpected error: {e}", fg="red", err=True)
        return 2
    return 0

if __name__ == "__main__":
    # Forward command-line args (excluding the program name) to main()
    raise SystemExit(main())
