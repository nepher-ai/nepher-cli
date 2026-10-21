<div align="center">

# nepher-cli

**The unified CLI for [Nepher Robotics](https://nepher.ai): accounts, tournaments, hackathons, EnvHub and SimStore.**

[![PyPI](https://img.shields.io/pypi/v/nepher-cli)](https://pypi.org/project/nepher-cli/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)

[Install](#install) •
[Commands](#commands) •
[Tournaments](#tournaments) •
[EnvHub](#envhub) •
[Hackathons](#hackathons) •
[Account](#account) •
[Troubleshooting](#troubleshooting)

</div>

---

## Install

```bash
pip install nepher-cli
pip install "nepher-cli[bittensor]"   # adds wallet signing for tournament submit and coldkey registration
```

This installs two equivalent commands, `npcli` and `nepher-cli`.

## Quick start

```bash
npcli login --api-key nepher_xxxxxxxx
npcli whoami
npcli --help
```

Get your API key at [nepher.ai/account](https://nepher.ai/account) under **API Keys**. In CI/CD, set `NEPHER_API_KEY` instead of logging in.

## Commands

| Command | Description |
|---|---|
| `npcli login` / `whoami` / `logout` | Manage authentication |
| `npcli account` | API keys and coldkey registration |
| `npcli tournament` | Browse tournaments, check and submit agents, view leaderboards |
| `npcli envhub` | Manage Isaac Lab environment bundles |
| `npcli hackathon` | Browse and submit to hackathons |
| `npcli simstore` | SimStore marketplace (coming soon) |

Run any command with `--help` for all options.

## Tournaments

```bash
npcli tournament list                  # or list-active
npcli tournament status <tournament_id>
npcli tournament leaderboard <tournament_id>
npcli tournament check --path ./my-agent
npcli tournament submit --path ./my-agent --wallet-name miner --wallet-hotkey default
```

`check` validates the agent directory (add `--verbose` for recommended-file warnings). `submit` requires `bittensor-wallet`.

<details>
<summary>Full <code>tournament submit</code> options</summary>

| Option | Description |
|---|---|
| `--path <path>` | Agent directory |
| `--wallet-name <str>` | Bittensor wallet name (default: `miner`) |
| `--wallet-hotkey <str>` | Bittensor wallet hotkey (default: `default`) |
| `--api-key <key>` | Nepher API key (falls back to stored credentials) |
| `--tournament-id <id>` | Target tournament, required when several are active |
| `--api-url <url>` | Override the tournament API URL |
| `-v`, `--verbose` | Verbose output |

</details>

## EnvHub

```bash
npcli envhub list
npcli envhub download <env_id>
npcli envhub upload ./my-bundle --category navigation
npcli envhub cache list | info | clear
```

Shares login, API and cache with the standalone [`nepher`](https://github.com/nepher-ai/envhub) package.

## Hackathons

```bash
npcli hackathon list
npcli hackathon submit --title "My entry" --submission ./my-project --assets ./my-assets
```

<details>
<summary>Full <code>hackathon submit</code> options</summary>

| Option | Description |
|---|---|
| `--hackathon-id <uuid>` | Required when several hackathons are open |
| `--title <str>` | Entry title |
| `--description <markdown>` | Entry description |
| `--thumbnail <file>` | Cover image (JPEG, PNG, WebP, GIF) |
| `--submission <path>` | Project folder or `submission.zip` |
| `--assets <path>` | Assets folder or `assets.zip` (images, videos, PDFs) |
| `--public-source` | Mark source as public |

</details>

## Account

API key management needs a session from `npcli account login`. Don't pass `--api-key` to the `api-keys` commands; the account API rejects `X-API-Key` for key management.

```bash
npcli account login --api-key nepher_...
npcli account api-keys list
npcli account api-keys create --name "CI key" --platform hackathon
npcli account api-keys revoke <key_id>
```

Bind a Bittensor coldkey to your account (requires `bittensor-wallet`; `btcli` is not needed):

```bash
npcli account register-coldkey --wallet <wallet_name>
```

Keys must start with `nepher_` and be active. `hackathon submit` needs Hackathon scope and `tournament submit` needs Tournament scope, or use an unrestricted key.

## Troubleshooting

| Error | Fix |
|---|---|
| `npcli: command not found` | Check the install succeeded and Python's scripts directory is on `PATH` |
| `Not logged in` | `npcli login --api-key nepher_...` |
| `invalid api key format` | Key must start with `nepher_` |
| `api key expired` | Create a new key with `npcli account api-keys create` |
| `api key does not have hackathon access` | Enable Hackathon scope or use an unrestricted key |
| `Several hackathons are accepting submissions` | Re-run with `--hackathon-id` |
| `bittensor-wallet not installed` | `pip install bittensor-wallet` |
| `Conflict detected: 'scalecodec' ... 'cyscale'` | Leftover `scalecodec` from a Bittensor upgrade. Install `bittensor-wallet` so npcli doesn't need `btcli`, or repair `btcli` with `pip uninstall scalecodec cyscale -y && pip install -U cyscale --force-reinstall` |

## License

MIT © 2026 Nepher Robotics
