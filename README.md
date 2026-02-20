# CatLink CLI

Command-line interface for CatLink smart litter boxes. Use it to authenticate, list devices and pets, check device status, and trigger actions like cleaning or consumable resets.

## Features

- Authenticate to CatLink and store tokens in the system keyring.
- List devices and cats associated with your account.
- Inspect device status, logs, and cat health summaries.
- Trigger device actions (clean/start/pause), change modes, and reset consumables.

## Requirements

- Python 3.13+.
- `uv` for running and managing dependencies.
- A CatLink account (phone + password).
- A system keyring backend (macOS Keychain, Windows Credential Manager, or a Linux keyring service).

## Installation

From the repo root:

```bash
uv sync
```

Run the CLI directly:

```bash
uv run catlink --help
```

If you want a local editable install:

```bash
uv pip install -e .
```

Then you can run:

```bash
catlink --help
```

## Quick Start

```bash
# Login and store credentials in your keyring
uv run catlink login --phone 15551234567 --password 'your-password' --region auto

# List devices
uv run catlink devices

# Show status for a device
uv run catlink status <DEVICE_ID> --type SCOOPER

# Start a clean cycle
uv run catlink clean <DEVICE_ID> --type SCOOPER

# List cats and get a daily summary
uv run catlink cats
uv run catlink cat-summary <PET_ID> --date 2025-01-01

# Log out and clear stored credentials
uv run catlink logout
```

## Authentication

- `catlink login` stores your token, phone, region, and SSL verify setting in the system keyring under the service name `catlink-cli`.
- Tokens are stored per region. Use `--region` on most commands to select which stored token to use.
- Commands aggregate results across all stored regions by default. Use `--region` to target a specific region.
- `catlink logout` removes all stored credentials for all regions. Use `--region` to clear one region.
- If you see `Not logged in. Run 'catlink login' first.`, authenticate before running other commands.

### Regions

Use `--region` to force a CatLink API region, or `auto` to log into all regions.

Available regions:

- `auto`
- `global`
- `china`
- `usa`
- `singapore`

## Device Types

Some commands require a `--type` argument. Supported values depend on the command.

- `SCOOPER`
- `LITTER_BOX_599`
- `C08` (status only)
- `FEEDER` (status only)
- `PUREPRO` (water fountain, status/logs)

## Commands

Below are the full help outputs for each command.

### Root

```bash
uv run catlink --help
```

```
Usage: catlink [OPTIONS] COMMAND [ARGS]...

  CatLink CLI - manage your CatLink litter box from the terminal.

Options:
  -v, --verbose  Enable debug logging.
  --help         Show this message and exit.

Commands:
  action           Send an action to the device (clean, pause, start).
  cat-summary      Show a cat's health summary for a given date.
  cats             List all cats on the account.
  change-bag       Trigger garbage bag replacement (LitterBox only).
  clean            Start a cleaning cycle.
  devices          List all devices on the account.
  login            Authenticate with your CatLink account.
  logout           Clear stored credentials.
  logs             Show recent device logs.
  mode             Change the device working mode (auto, manual, time,...
  pause            Pause the current operation.
  reset-deodorant  Reset the deodorant consumable counter.
  reset-litter     Reset the litter consumable counter.
  status           Show detailed status for a device.
```

### `login`

```bash
uv run catlink login --help
```

```
Usage: catlink login [OPTIONS]

  Authenticate with your CatLink account.

Options:
  --iac TEXT                      Country calling code, digits only (e.g. 1
                                  for US, 44 for UK, 86 for China).  [default:
                                  86]
  --phone TEXT                    Phone number (digits only).
  --password TEXT                 Account password.
  --region [auto|global|china|usa|singapore]
                                  API region. Use 'auto' to login to all
                                  regions.  [default: auto]
  --no-verify                     Disable SSL certificate verification.
  --help                          Show this message and exit.
```

### `logout`

```bash
uv run catlink logout --help
```

```
Usage: catlink logout [OPTIONS]

  Clear stored credentials.

Options:
  --region [global|china|usa|singapore]
                                  Clear stored credentials for this region only.
  --help  Show this message and exit.
```

### `devices`

```bash
uv run catlink devices --help
```

```
Usage: catlink devices [OPTIONS]

  List all devices on the account.

Options:
  --help  Show this message and exit.
```

### `status`

```bash
uv run catlink status --help
```

```
Usage: catlink status [OPTIONS] DEVICE_ID

  Show detailed status for a device.

Options:
  --type [SCOOPER|LITTER_BOX_599|C08|FEEDER]
                                  Device type.  [default: SCOOPER]
  --help                          Show this message and exit.
```

### `mode`

```bash
uv run catlink mode --help
```

```
Usage: catlink mode [OPTIONS] DEVICE_ID MODE

  Change the device working mode (auto, manual, time, empty).

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: SCOOPER]
  --help                          Show this message and exit.
```

### `action`

```bash
uv run catlink action --help
```

```
Usage: catlink action [OPTIONS] DEVICE_ID ACTION

  Send an action to the device (clean, pause, start).

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: SCOOPER]
  --help                          Show this message and exit.
```

### `clean`

```bash
uv run catlink clean --help
```

```
Usage: catlink clean [OPTIONS] DEVICE_ID

  Start a cleaning cycle.

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: SCOOPER]
  --help                          Show this message and exit.
```

### `pause`

```bash
uv run catlink pause --help
```

```
Usage: catlink pause [OPTIONS] DEVICE_ID

  Pause the current operation.

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: SCOOPER]
  --help                          Show this message and exit.
```

### `logs`

```bash
uv run catlink logs --help
```

```
Usage: catlink logs [OPTIONS] DEVICE_ID

  Show recent device logs.

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: SCOOPER]
  --help                          Show this message and exit.
```

### `change-bag`

```bash
uv run catlink change-bag --help
```

```
Usage: catlink change-bag [OPTIONS] DEVICE_ID

  Trigger garbage bag replacement (LitterBox only).

Options:
  --help  Show this message and exit.
```

### `reset-litter`

```bash
uv run catlink reset-litter --help
```

```
Usage: catlink reset-litter [OPTIONS] DEVICE_ID

  Reset the litter consumable counter.

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: LITTER_BOX_599]
  --help                          Show this message and exit.
```

### `reset-deodorant`

```bash
uv run catlink reset-deodorant --help
```

```
Usage: catlink reset-deodorant [OPTIONS] DEVICE_ID

  Reset the deodorant consumable counter.

Options:
  --type [SCOOPER|LITTER_BOX_599]
                                  Device type.  [default: LITTER_BOX_599]
  --help                          Show this message and exit.
```

### `cats`

```bash
uv run catlink cats --help
```

```
Usage: catlink cats [OPTIONS]

  List all cats on the account.

Options:
  --help  Show this message and exit.
```

### `cat-summary`

```bash
uv run catlink cat-summary --help
```

```
Usage: catlink cat-summary [OPTIONS] PET_ID

  Show a cat's health summary for a given date.

Options:
  --date TEXT  Date in YYYY-MM-DD format. Defaults to today.
  --help       Show this message and exit.
```

## Modes and Actions

The CLI validates modes and actions per device type.

Available modes:

- `SCOOPER`: `auto`, `manual`, `time`, `empty`
- `LITTER_BOX_599`: `auto`, `manual`, `time`

Available actions:

- `SCOOPER`: `start`, `pause`
- `LITTER_BOX_599`: `clean`, `pause`

## Examples

```bash
# Switch to manual mode
uv run catlink mode <DEVICE_ID> manual --type SCOOPER

# Trigger a clean action for a Litter Box
uv run catlink action <DEVICE_ID> clean --type LITTER_BOX_599

# Fetch logs for the last few events
uv run catlink logs <DEVICE_ID> --type SCOOPER

# Reset consumables
uv run catlink reset-litter <DEVICE_ID> --type LITTER_BOX_599
uv run catlink reset-deodorant <DEVICE_ID> --type LITTER_BOX_599

# Replace a garbage bag
uv run catlink change-bag <DEVICE_ID>
```

## Time Zones

Cat health summaries use the system IANA timezone derived from `/etc/localtime`. If the timezone cannot be resolved, the CLI falls back to `UTC`.

## Troubleshooting

- `Not logged in. Run 'catlink login' first.`
  Run `catlink login` and ensure a keyring backend is available.
- `Token expired`
  Re-run `catlink login`. The CLI will retry once using stored credentials when possible.
- SSL errors
  If you're behind a proxy or have TLS inspection, retry with `--no-verify` (not recommended for regular use).

## Development

Run tests:

```bash
uv run pytest
```

Format code:

```bash
uv run black .
```

Lint:

```bash
uv run ruff check .
```
```
