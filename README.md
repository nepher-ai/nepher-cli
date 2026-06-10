# nepher-cli

The unified CLI for [Nepher Robotics](https://nepher.ai) — accounts, hackathons, EnvHub, tournaments, and SimStore from a single tool.

**Requires:** Python 3.10+

## Install

```bash
pip install nepher-cli
```

Both `npcli` and `nepher-cli` entry points are registered after install.

```bash
npcli --version
npcli --help
```

## Commands

| Group | Description |
|-------|-------------|
| `npcli account` | Login, API keys, coldkey registration |
| `npcli tournament` | Browse tournaments, submit agents, leaderboards |
| `npcli envhub` | Manage Isaac Lab environment bundles |
| `npcli hackathon` | Browse and submit to hackathons |
| `npcli simstore` | SimStore marketplace *(coming soon)* |

## Quick Start

### Authenticate

```bash
npcli account login --api-key nepher_xxxxxxxx
npcli account whoami
npcli account logout
```

Get your API key at [account.nepher.ai](https://account.nepher.ai) → Account → API Keys.  
For CI/CD, set `NEPHER_API_KEY=nepher_xxxxxxxx` instead of logging in.

### Tournaments

```bash
npcli tournament list
npcli tournament list-active
npcli tournament status <tournament_id>
npcli tournament leaderboard <tournament_id>
```

Check your agent directory structure (no extra dependencies needed):

```bash
npcli tournament check --path ./my-agent
npcli tournament check --path ./my-agent --verbose   # also show recommended-file warnings
```

Submit an agent (requires `bittensor` for wallet signing):

```bash
pip install bittensor
# or: pip install "nepher-cli[bittensor]"
```

```bash
npcli tournament submit --path ./my-agent --wallet-name miner --wallet-hotkey default
```

Full options for `submit`:

```
--path <path>               Agent directory
--wallet-name <str>         Bittensor wallet name (default: miner)
--wallet-hotkey <str>       Bittensor wallet hotkey (default: default)
--api-key <key>             Nepher API key (falls back to stored credentials)
--tournament-id <id>        Target tournament ID (required when multiple are active)
--api-url <url>             Override tournament API URL
-v / --verbose              Verbose output
```

### EnvHub

```bash
npcli envhub list
npcli envhub download <env_id>
npcli envhub upload ./my-bundle --category navigation
npcli envhub cache list
npcli envhub cache info
npcli envhub cache clear
```

### Hackathons

```bash
npcli hackathon list

npcli hackathon submit \
  --title "My entry" \
  --submission ./my-project \
  --assets ./my-assets
```

Full options:

```
--hackathon-id <uuid>       Required when multiple hackathons are open
--title <str>               Entry title
--description <markdown>    Entry description
--thumbnail <file>          Cover image (JPEG, PNG, WebP, GIF)
--submission <path>         Project folder or submission.zip
--assets <path>             Assets folder or assets.zip (images, videos, PDFs)
--public-source             Mark source as public
```

### API Keys

```bash
npcli account api-keys list
npcli account api-keys create --name "CI key" --platform hackertone
npcli account api-keys revoke <key_id>
```

### Coldkey Registration

Bind a Bittensor coldkey to your account (requires `bittensor` + `btcli` on PATH):

```bash
pip install bittensor
npcli account register-coldkey --wallet <wallet_name>
```

## API Key Requirements

- Must start with `nepher_`
- Must be active and not expired
- `hackathon submit` requires **Hackathon** scope (or an unrestricted key)
- `tournament submit` requires **Tournament** scope (or an unrestricted key)

## Troubleshooting

| Error | Fix |
|-------|-----|
| `npcli: command not found` | Ensure `pip install` succeeded and Python scripts dir is on `PATH` |
| `invalid api key format` | Key must start with `nepher_` |
| `api key does not have hackathon access` | Enable Hackathon scope or use an unrestricted key |
| `api key expired` | Run `npcli account api-keys create` |
| `Several hackathons are accepting submissions` | Re-run with `--hackathon-id` |
| `bittensor not installed` | `pip install bittensor` (only needed for `tournament submit`) |
| `Not logged in` | `npcli account login --api-key nepher_...` |

Run any command with `--help` for full flag details:

```bash
npcli --help
npcli hackathon submit --help
npcli tournament submit --help
```

## License

MIT
