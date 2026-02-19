"""CatLink CLI - Command-line interface for CatLink litter boxes."""

import datetime
import logging
import sys

import click

from .api import (
    CatLinkAPI,
    CatLinkAPIError,
    clear_credentials,
    get_authenticated_client,
    save_credentials,
)
from .const import API_SERVERS, DEVICE_ACTIONS, DEVICE_MODES, WORK_STATUSES

_URL_TO_REGION = {url: name for name, url in API_SERVERS.items()}


def _region_name_from_url(api_base: str) -> str:
    return _URL_TO_REGION.get(api_base, "unknown")


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """CatLink CLI - manage your CatLink litter box from the terminal."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


@cli.command()
@click.option(
    "--iac",
    prompt="Country code (e.g. 1=US, 44=UK, 86=China)",
    default="86",
    show_default=True,
    help="Country calling code, digits only (e.g. 1 for US, 44 for UK, 86 for China).",
)
@click.option("--phone", prompt=True, help="Phone number (digits only).")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    help="Account password.",
)
@click.option(
    "--region",
    type=click.Choice(["auto", "global", "china", "usa", "singapore"]),
    default="auto",
    show_default=True,
    help="API region.",
)
@click.option(
    "--no-verify",
    is_flag=True,
    default=False,
    help="Disable SSL certificate verification.",
)
def login(phone: str, iac: str, password: str, region: str, no_verify: bool) -> None:
    """Authenticate with your CatLink account."""
    verify = not no_verify
    client = CatLinkAPI(verify=verify)
    try:
        if region == "auto":
            token, api_base = client.login_auto_region(iac, phone, password)
        else:
            api_base = API_SERVERS[region]
            client.api_base = api_base
            token = client.login(iac, phone, password)
        save_credentials(token, phone, iac, api_base, verify=verify)
        region_name = _region_name_from_url(api_base)
        click.echo(f"Login successful. Connected to {region_name} ({api_base}).")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command()
def logout() -> None:
    """Clear stored credentials."""
    clear_credentials()
    click.echo("Credentials cleared.")


@cli.command("devices")
def list_devices() -> None:
    """List all devices on the account."""
    client = get_authenticated_client()
    try:
        devices = client.get_devices()
        if not devices:
            click.echo("No devices found.")
            return
        for dev in devices:
            dtype = dev.get("deviceType", "unknown")
            name = dev.get("deviceName", "unnamed")
            did = dev.get("id", "?")
            model = dev.get("model", "?")
            click.echo(f"  [{dtype}] {name}  (id={did}, model={model})")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599", "C08", "FEEDER"]),
    help="Device type.",
)
def status(device_id: str, device_type: str) -> None:
    """Show detailed status for a device."""
    client = get_authenticated_client()
    try:
        detail = client.get_device_detail(device_id, device_type)
        if not detail:
            click.echo("No detail returned for this device.")
            return

        work_status = detail.get("workStatus", "")
        state = WORK_STATUSES.get(str(work_status).strip(), work_status)
        mode_code = detail.get("workModel", "")
        modes = DEVICE_MODES.get(device_type, {})
        mode = modes.get(mode_code, mode_code)

        click.echo(f"State:             {state}")
        click.echo(f"Mode:              {mode}")
        click.echo(f"Online:            {detail.get('online', '?')}")

        litter_weight = detail.get("catLitterWeight")
        if litter_weight is not None:
            click.echo(f"Litter weight:     {litter_weight} kg")

        countdown = detail.get("litterCountdown")
        if countdown is not None:
            click.echo(f"Litter remaining:  {countdown} days")

        induction = int(detail.get("inductionTimes", 0))
        manual = int(detail.get("manualTimes", 0))
        click.echo(f"Total cleans:      {induction + manual}")
        click.echo(f"Manual cleans:     {manual}")

        deodorant = detail.get("deodorantCountdown")
        if deodorant is not None:
            click.echo(f"Deodorant days:    {deodorant}")

        temp = detail.get("temperature")
        if temp is not None and temp != "-":
            click.echo(f"Temperature:       {temp} C")
        humidity = detail.get("humidity")
        if humidity is not None and humidity != "-":
            click.echo(f"Humidity:          {humidity}%")

        error = detail.get("currentMessage") or detail.get("currentError")
        if error:
            click.echo(f"Error:             {error}")

    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.argument("device_id")
@click.argument("mode")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def mode(device_id: str, mode: str, device_type: str) -> None:
    """Change the device working mode (auto, manual, time, empty)."""
    modes = DEVICE_MODES.get(device_type, {})
    code = None
    for k, v in modes.items():
        if v == mode:
            code = k
            break
    if code is None:
        valid = ", ".join(modes.values())
        click.echo(f"Invalid mode '{mode}'. Valid modes: {valid}", err=True)
        sys.exit(1)

    client = get_authenticated_client()
    try:
        client.change_mode(device_id, code, device_type)
        click.echo(f"Mode set to '{mode}'.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.argument("device_id")
@click.argument("action")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def action(device_id: str, action: str, device_type: str) -> None:
    """Send an action to the device (clean, pause, start)."""
    actions = DEVICE_ACTIONS.get(device_type, {})
    code = None
    for k, v in actions.items():
        if v == action:
            code = k
            break
    if code is None:
        valid = ", ".join(actions.values())
        click.echo(f"Invalid action '{action}'. Valid actions: {valid}", err=True)
        sys.exit(1)

    client = get_authenticated_client()
    try:
        client.send_action(device_id, code, device_type)
        click.echo(f"Action '{action}' sent.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command()
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def logs(device_id: str, device_type: str) -> None:
    """Show recent device logs."""
    client = get_authenticated_client()
    try:
        entries = client.get_device_logs(device_id, device_type)
        if not entries:
            click.echo("No logs found.")
            return
        for entry in entries:
            ts = entry.get("time") or entry.get("createTime") or ""
            event = entry.get("event") or entry.get("msg") or str(entry)
            click.echo(f"  [{ts}] {event}")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("clean")
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def clean(device_id: str, device_type: str) -> None:
    """Start a cleaning cycle."""
    actions = DEVICE_ACTIONS.get(device_type, {})
    code = None
    for k, v in actions.items():
        if v in ("start", "clean"):
            code = k
            break
    if code is None:
        click.echo("Clean action not available for this device type.", err=True)
        sys.exit(1)

    client = get_authenticated_client()
    try:
        client.send_action(device_id, code, device_type)
        click.echo("Cleaning started.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("pause")
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def pause(device_id: str, device_type: str) -> None:
    """Pause the current operation."""
    client = get_authenticated_client()
    try:
        client.send_action(device_id, "00", device_type)
        click.echo("Device paused.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("reset-litter")
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="LITTER_BOX_599",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def reset_litter(device_id: str, device_type: str) -> None:
    """Reset the litter consumable counter."""
    client = get_authenticated_client()
    try:
        client.reset_consumable(device_id, device_type, "CAT_LITTER")
        click.echo("Litter counter reset.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("reset-deodorant")
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="LITTER_BOX_599",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599"]),
    help="Device type.",
)
def reset_deodorant(device_id: str, device_type: str) -> None:
    """Reset the deodorant consumable counter."""
    client = get_authenticated_client()
    try:
        client.reset_consumable(device_id, device_type, "DEODORIZER_02")
        click.echo("Deodorant counter reset.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("change-bag")
@click.argument("device_id")
def change_bag(device_id: str) -> None:
    """Trigger garbage bag replacement (LitterBox only)."""
    client = get_authenticated_client()
    try:
        client.replace_garbage_bag(device_id, enable=True)
        click.echo("Garbage bag change triggered.")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("cats")
def list_cats() -> None:
    """List all cats on the account."""
    client = get_authenticated_client()
    try:
        cats = client.get_cats()
        if not cats:
            click.echo("No cats found.")
            return
        for cat in cats:
            name = cat.get("name") or cat.get("petName") or "unnamed"
            pid = cat.get("id") or cat.get("petId") or "?"
            weight = cat.get("weight", "?")
            breed = cat.get("breedName") or cat.get("breed") or ""
            line = f"  {name} (id={pid}, weight={weight}kg"
            if breed:
                line += f", breed={breed}"
            line += ")"
            click.echo(line)
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@cli.command("cat-summary")
@click.argument("pet_id")
@click.option(
    "--date",
    default=None,
    help="Date in YYYY-MM-DD format. Defaults to today.",
)
def cat_summary(pet_id: str, date: str | None) -> None:
    """Show a cat's health summary for a given date."""
    if date is None:
        date = datetime.date.today().isoformat()
    client = get_authenticated_client()
    try:
        data = client.get_cat_summary(pet_id, date)
        if not data:
            click.echo("No summary data returned.")
            return
        for key, val in data.items():
            click.echo(f"  {key}: {val}")
    except CatLinkAPIError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


def main() -> None:
    """Entry point."""
    cli()
