"""CatLink CLI - Command-line interface for CatLink litter boxes."""

import datetime
import logging
import sys
from collections.abc import Callable

import click

from .api import (
    CatLinkAPI,
    CatLinkAPIError,
    clear_credentials,
    clear_credentials_for_region,
    get_authenticated_clients,
    get_system_timezone,
    save_credentials,
)
from .const import API_SERVERS, DEVICE_ACTIONS, DEVICE_MODES, WORK_STATUSES

_URL_TO_REGION = {url: name for name, url in API_SERVERS.items()}
_REGION_CHOICES = list(API_SERVERS.keys())


def _region_name_from_url(api_base: str) -> str:
    return _URL_TO_REGION.get(api_base, "unknown")


def _region_option(func: Callable[..., object]) -> Callable[..., object]:
    """
    Attach a region option to a Click command.

    Args:
        func: Click command function.

    Returns:
        Wrapped Click command.
    """
    return click.option(
        "--region",
        type=click.Choice(_REGION_CHOICES),
        default=None,
        help="Use stored token for this region.",
    )(func)


def _load_clients(region: str | None) -> tuple[list[tuple[str, CatLinkAPI]], bool]:
    """
    Load clients for one or more regions.

    Args:
        region: Optional region identifier.

    Returns:
        Tuple of clients and a flag indicating multiple regions.
    """
    clients = get_authenticated_clients(region=region)
    return clients, len(clients) > 1


def _echo_region_header(region: str, api_base: str, multi: bool) -> None:
    """
    Print a region header when multiple regions are active.

    Args:
        region: Region name.
        api_base: API base URL.
        multi: Whether multiple regions are active.

    Returns:
        None.
    """
    if multi:
        click.echo(f"Region: {region} ({api_base})")


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
    help="API region. Use 'auto' to login to all regions.",
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
            successes, errors = client.login_all_regions(iac, phone, password)
            if not successes:
                msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
                click.echo(f"Error: Login failed on all regions: {msg}", err=True)
                sys.exit(1)
            for region_name, api_base, token in successes:
                save_credentials(token, phone, iac, api_base, verify=verify)
            if len(successes) == 1:
                region_name, api_base, _ = successes[0]
                click.echo(f"Login successful. Connected to {region_name} ({api_base}).")
            else:
                click.echo(f"Login successful for {len(successes)} region(s).")
                for region_name, api_base, _ in successes:
                    click.echo(f"  {region_name}: {api_base}")
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
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
@click.option(
    "--region",
    type=click.Choice(_REGION_CHOICES),
    default=None,
    help="Clear stored credentials for this region only.",
)
def logout(region: str | None) -> None:
    """Clear stored credentials."""
    if region:
        clear_credentials_for_region(region)
        click.echo(f"Credentials cleared for region {region}.")
    else:
        clear_credentials()
        click.echo("Credentials cleared.")


@cli.command("devices")
@_region_option
def list_devices(region: str | None) -> None:
    """List all devices on the account."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    total_devices = 0
    try:
        for region_name, client in clients:
            try:
                devices = client.get_devices()
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            if not devices:
                continue
            _echo_region_header(region_name, client.api_base, multi)
            for dev in devices:
                dtype = dev.get("deviceType", "unknown")
                name = dev.get("deviceName", "unnamed")
                did = dev.get("id", "?")
                model = dev.get("model", "?")
                click.echo(f"  [{dtype}] {name}  (id={did}, model={model})")
                total_devices += 1
        if total_devices == 0:
            if errors and len(errors) == len(clients):
                msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
                click.echo(f"Error: {msg}", err=True)
                sys.exit(1)
            click.echo("No devices found.")
        if errors and total_devices > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


def _show_litter_box_status(detail: dict, device_type: str) -> None:
    work_status = detail.get("workStatus", "")
    state = WORK_STATUSES.get(str(work_status).strip(), work_status)
    mode_code = detail.get("workModel", "")
    modes = DEVICE_MODES.get(device_type, {})
    mode = modes.get(mode_code, mode_code)

    click.echo(f"State:             {state}")
    click.echo(f"Mode:              {mode}")

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


def _show_feeder_status(detail: dict) -> None:
    food_out = detail.get("foodOutStatus", "")
    if food_out:
        click.echo(f"Food out status:   {food_out}")

    weight = detail.get("weight")
    if weight is not None:
        click.echo(f"Food weight:       {weight} g")

    auto_fill = detail.get("autoFillStatus", "")
    if auto_fill:
        click.echo(f"Auto-fill:         {auto_fill}")

    power = detail.get("powerSupplyStatus", "")
    if power:
        click.echo(f"Power supply:      {power}")

    key_lock = detail.get("keyLockStatus", "")
    if key_lock:
        click.echo(f"Key lock:          {key_lock}")

    indicator = detail.get("indicatorLightStatus", "")
    if indicator:
        click.echo(f"Indicator light:   {indicator}")

    breath = detail.get("breathLightStatus", "")
    if breath:
        click.echo(f"Breath light:      {breath}")

    firmware = detail.get("firmwareVersion", "")
    if firmware:
        click.echo(f"Firmware:          {firmware}")

    error = detail.get("currentErrorMessage") or detail.get("error") or detail.get("currentMessage")
    if error:
        click.echo(f"Error:             {error}")


@cli.command()
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599", "C08", "FEEDER", "PUREPRO"]),
    help="Device type.",
)
@_region_option
def status(device_id: str, device_type: str, region: str | None) -> None:
    """Show detailed status for a device."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    shown = 0
    try:
        for region_name, client in clients:
            try:
                detail = client.get_device_detail(device_id, device_type)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            if not detail:
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo(f"Online:            {detail.get('online', '?')}")

            if device_type == "FEEDER":
                _show_feeder_status(detail)
            else:
                _show_litter_box_status(detail, device_type)
            shown += 1
        if shown == 0:
            if errors and len(errors) == len(clients):
                msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
                click.echo(f"Error: {msg}", err=True)
                sys.exit(1)
            click.echo("No detail returned for this device.")
        if errors and shown > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
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
@_region_option
def mode(device_id: str, mode: str, device_type: str, region: str | None) -> None:
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

    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    updated = 0
    try:
        for region_name, client in clients:
            try:
                client.change_mode(device_id, code, device_type)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo(f"Mode set to '{mode}'.")
            updated += 1
        if updated == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and updated > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
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
@_region_option
def action(device_id: str, action: str, device_type: str, region: str | None) -> None:
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

    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    sent = 0
    try:
        for region_name, client in clients:
            try:
                client.send_action(device_id, code, device_type)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo(f"Action '{action}' sent.")
            sent += 1
        if sent == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and sent > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


@cli.command()
@click.argument("device_id")
@click.option(
    "--type",
    "device_type",
    default="SCOOPER",
    show_default=True,
    type=click.Choice(["SCOOPER", "LITTER_BOX_599", "FEEDER", "PUREPRO"]),
    help="Device type.",
)
@_region_option
def logs(device_id: str, device_type: str, region: str | None) -> None:
    """Show recent device logs."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    shown = 0
    try:
        for region_name, client in clients:
            try:
                entries = client.get_device_logs(device_id, device_type)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            if not entries:
                continue
            _echo_region_header(region_name, client.api_base, multi)
            for entry in entries:
                ts = entry.get("time") or entry.get("createTime") or ""
                event = entry.get("event") or entry.get("msg") or str(entry)
                parts = [event]
                for extra in ("firstSection", "secondSection"):
                    val = entry.get(extra)
                    if val:
                        parts.append(str(val))
                click.echo(f"  [{ts}] {' '.join(parts)}")
                shown += 1
        if shown == 0:
            if errors and len(errors) == len(clients):
                msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
                click.echo(f"Error: {msg}", err=True)
                sys.exit(1)
            click.echo("No logs found.")
        if errors and shown > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
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
@_region_option
def clean(device_id: str, device_type: str, region: str | None) -> None:
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

    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    sent = 0
    try:
        for region_name, client in clients:
            try:
                client.send_action(device_id, code, device_type)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo("Cleaning started.")
            sent += 1
        if sent == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and sent > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
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
@_region_option
def pause(device_id: str, device_type: str, region: str | None) -> None:
    """Pause the current operation."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    sent = 0
    try:
        for region_name, client in clients:
            try:
                client.send_action(device_id, "00", device_type)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo("Device paused.")
            sent += 1
        if sent == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and sent > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


@cli.command("feed")
@click.argument("device_id")
@click.option(
    "--portions",
    default=5,
    show_default=True,
    type=click.IntRange(1, 10),
    help="Number of portions to dispense (1-10).",
)
@_region_option
def feed(device_id: str, portions: int, region: str | None) -> None:
    """Dispense food from a feeder."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    sent = 0
    try:
        for region_name, client in clients:
            try:
                client.food_out(device_id, portions)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo(f"Dispensing {portions} portion(s).")
            sent += 1
        if sent == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and sent > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
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
@_region_option
def reset_litter(device_id: str, device_type: str, region: str | None) -> None:
    """Reset the litter consumable counter."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    reset = 0
    try:
        for region_name, client in clients:
            try:
                client.reset_consumable(device_id, device_type, "CAT_LITTER")
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo("Litter counter reset.")
            reset += 1
        if reset == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and reset > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
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
@_region_option
def reset_deodorant(device_id: str, device_type: str, region: str | None) -> None:
    """Reset the deodorant consumable counter."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    reset = 0
    try:
        for region_name, client in clients:
            try:
                client.reset_consumable(device_id, device_type, "DEODORIZER_02")
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo("Deodorant counter reset.")
            reset += 1
        if reset == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and reset > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


@cli.command("change-bag")
@click.argument("device_id")
@_region_option
def change_bag(device_id: str, region: str | None) -> None:
    """Trigger garbage bag replacement (LitterBox only)."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    sent = 0
    try:
        for region_name, client in clients:
            try:
                client.replace_garbage_bag(device_id, enable=True)
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            _echo_region_header(region_name, client.api_base, multi)
            click.echo("Garbage bag change triggered.")
            sent += 1
        if sent == 0:
            msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
            click.echo(f"Error: {msg}", err=True)
            sys.exit(1)
        if errors and sent > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


@cli.command("cats")
@_region_option
def list_cats(region: str | None) -> None:
    """List all cats on the account."""
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    total_cats = 0
    try:
        for region_name, client in clients:
            try:
                cats = client.get_cats(timezone_id=get_system_timezone())
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            if not cats:
                continue
            _echo_region_header(region_name, client.api_base, multi)
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
                total_cats += 1
        if total_cats == 0:
            if errors and len(errors) == len(clients):
                msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
                click.echo(f"Error: {msg}", err=True)
                sys.exit(1)
            click.echo("No cats found.")
        if errors and total_cats > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


@cli.command("cat-summary")
@click.argument("pet_id")
@click.option(
    "--date",
    default=None,
    help="Date in YYYY-MM-DD format. Defaults to today.",
)
@_region_option
def cat_summary(pet_id: str, date: str | None, region: str | None) -> None:
    """Show a cat's health summary for a given date."""
    if date is None:
        date = datetime.date.today().isoformat()
    clients, multi = _load_clients(region)
    errors: list[tuple[str, str]] = []
    shown = 0
    try:
        for region_name, client in clients:
            try:
                data = client.get_cat_summary(pet_id, date, timezone_id=get_system_timezone())
            except CatLinkAPIError as exc:
                errors.append((region_name, str(exc)))
                continue
            if not data:
                continue
            _echo_region_header(region_name, client.api_base, multi)
            for key, val in data.items():
                click.echo(f"  {key}: {val}")
            shown += 1
        if shown == 0:
            if errors and len(errors) == len(clients):
                msg = "; ".join(f"{region_name}: {err}" for region_name, err in errors)
                click.echo(f"Error: {msg}", err=True)
                sys.exit(1)
            click.echo("No summary data returned.")
        if errors and shown > 0:
            for region_name, err in errors:
                click.echo(f"Warning ({region_name}): {err}", err=True)
    finally:
        for _, client in clients:
            client.close()


def main() -> None:
    """Entry point."""
    cli()
