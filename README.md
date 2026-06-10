# npcli — Unified Nepher CLI

The unified command-line interface for [Nepher](https://nepher.ai)'s ecosystem — accounts, hackathons, EnvHub, Bittensor Subnet 49, tournaments, and SimStore, all from a single tool.

**Requirements:** Python 3.10+

| Command group | What it does | Extra tooling |
|---------------|--------------|---------------|
| `npcli account` | Login, API keys, coldkey registration | [`btcli`](https://github.com/opentensor/bittensor) for coldkey |
| `npcli hackathon` | Browse hackathons and upload submissions | — |
| `npcli envhub` | Manage Isaac Lab environment bundles | Isaac Lab for `view` |
| `npcli subnet` | Validate and submit agents to Subnet 49 | `nepher-subnet` + `bittensor` |
| `npcli tournament` | Browse tournaments and leaderboards | — |
| `npcli simstore` | SimStore marketplace *(coming soon)* | — |

## Install

```bash
pip install nepher-cli
```

Verify the install:

```bash
npcli --version
npcli --help
```

Both `npcli` and `nepher-cli` point to the same tool after install.

## Quick start

### 1. Log in

Store credentials locally so you don't need to pass `--api-key` on every command:

```bash
npcli account login
# Prompts for your API key (created at account.nepher.ai)
```

Or pass the key inline:

```bash
npcli account login --api-key nepher_xxxxxxxx
```

Check who you're logged in as:

```bash
npcli account whoami
```

Log out and clear stored credentials:

```bash
npcli account logout
```

### 2. Browse hackathons

```bash
npcli hackathon list
```

### 3. Submit to a hackathon

Upload your project and assets (folders are zipped automatically):

```bash
npcli hackathon submit \
  --title "My entry" \
  --submission ./my-project \
  --assets ./my-assets
```

With all optional flags:

```bash
npcli hackathon submit \
  --hackathon-id <uuid> \
  --title "My entry" \
  --description "Markdown summary for your entry page." \
  --thumbnail ./cover.png \
  --submission ./my-project \
  --assets ./my-assets \
  --public-source
```

- **`--hackathon-id`** — required when multiple hackathons are open simultaneously; the available UUIDs are printed if you omit it and ambiguity is detected.
- **`--thumbnail`** — optional listing image (JPEG, PNG, WebP, or GIF).

### 4. Register a Bittensor coldkey

Bind or replace the coldkey on your Nepher account (requires `btcli` on PATH):

```bash
npcli account register-coldkey --wallet <wallet_name>
```

### 5. EnvHub — Isaac Lab environments

```bash
npcli envhub list                           # browse available bundles
npcli envhub download <env_id>             # cache locally
npcli envhub upload ./my-bundle --category navigation
npcli envhub cache list                    # show cached environments
npcli envhub cache info                    # disk usage
npcli envhub cache clear                   # remove all cached bundles
```

### 6. Subnet 49 — agent submission

Requires `nepher-subnet` (and `bittensor`) to be installed:

```bash
npcli subnet validate --path ./my-agent          # check structure
npcli subnet list-active                          # active tournaments
npcli subnet submit --path ./my-agent \
  --wallet-name miner --wallet-hotkey default
```

### 7. Tournaments

```bash
npcli tournament list                            # all tournaments
npcli tournament status <tournament_id>          # details
npcli tournament leaderboard <tournament_id>     # score table
```

## API keys

Create a key at [account.nepher.ai](https://account.nepher.ai) (Account > API Keys):

- Must start with `nepher_`
- Must be **active** (not revoked) and **not expired**
- For `hackathon submit`, enable **Hackathon** access (or use an unrestricted key)

After `npcli account login`, the key is stored securely and reused automatically. For CI/CD, set the environment variable instead:

```bash
export NEPHER_API_KEY=nepher_xxxxxxxx
npcli hackathon submit --title "CI build" --submission ./dist --assets ./assets
```

## Manage API keys from the CLI

```bash
npcli account api-keys list
npcli account api-keys create --name "CI key" --platform hackertone
npcli account api-keys revoke <key_id>
```

## Services

| Platform | Base URL | Commands |
|----------|----------|----------|
| Account | `account-api.nepher.ai` | `account` |
| Hackathon | `api.hackathon.nepher.ai` | `hackathon` |
| EnvHub | `envhub-api.nepher.ai` | `envhub` |
| Tournament | `tournament-api.nepher.ai` | `tournament`, `subnet` |
| SimStore | `api.simstore.nepher.ai` | `simstore` *(coming soon)* |

## Notes

- You do **not** need a registered coldkey to submit a hackathon entry. A coldkey is used for stake-weighted community voting when an event requires it.
- `--submission` accepts a project folder (recommended) or an existing `submission.zip`.
- `--assets` accepts a folder or `assets.zip` with images, videos, and PDFs only.
- The `nepher` command (standalone EnvHub CLI) is unaffected — it continues to work as before. `npcli envhub` provides the same operations in the unified interface.

## Common problems

| Problem | What to do |
|---------|------------|
| `npcli: command not found` | Ensure `pip install` succeeded and your Python scripts directory is on `PATH` |
| `invalid api key format` | Key must start with `nepher_` |
| `api key does not have hackathon access` | Enable **Hackathon** on the key or use an unrestricted key |
| `api key expired` | Create a new key with a later expiry or run `npcli account api-keys create` |
| `btcli` / wallet not found | Run `btcli wallet list`; check `--wallet` name |
| `Several hackathons are accepting submissions` | Re-run with `--hackathon-id` from the listed UUIDs |
| `Unable to reach the Nepher backend` | Check your network connection |
| `nepher_core / miner not available` | Install `nepher-subnet`: `pip install -e path/to/nepher-subnet` |
| `Not logged in` | Run `npcli account login --api-key nepher_...` |

For full flag reference, run any command with `--help`:

```bash
npcli --help
npcli hackathon submit --help
npcli envhub --help
npcli subnet submit --help
```

## License

MIT
