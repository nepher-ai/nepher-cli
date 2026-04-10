# nepher-cli

Command-line interface for Nepher — **`--service account`** (coldkey registration) and **`--service hackathon`** (zip submission). Behavior matches the internal product spec (`internal-docs/Hackathon/2. Python CLI SDK.md`).

## Install

```bash
pip install nepher-cli
```

Development install from this repo:

```bash
pip install -e ".[dev]"
```

## Usage

### Register coldkey (account backend)

Requires [Bittensor](https://github.com/opentensor/bittensor) `btcli` on your `PATH`.

```bash
nepher-cli --service account register-coldkey --wallet <walletname> --apikey <nepher_api_key>
```

### Submit to active hackathon

```bash
nepher-cli --service hackathon submit --apikey <nepher_api_key> --file submission.zip --assets assets.zip
```

Optional: `--public-source` maps to `submitter_public_source` when the backend supports it.

### Backend URL (dev / staging only)

Not shown in `--help`. Resolution order: `--backend` → `NEPHER_CLI_BACKEND` → per-service default.

```bash
export NEPHER_CLI_BACKEND=https://localhost:8000
nepher-cli --service account register-coldkey --wallet mywallet --apikey nepher_xxx
```

## Defaults

| Service   | Production default (override with `--backend` / env) |
|-----------|------------------------------------------------------|
| `account` | `https://api.accounts.nepher.ai`                     |
| `hackathon` | `https://api.hackathon.nepher.ai`                  |

## API paths (v1)

Illustrative — align with **account-backend** / **hackathon-backend** deployments:

- Account: `POST /api/v1/account/coldkey/challenge`, `POST /api/v1/account/coldkey/verify`
- Hackathon: `POST /api/v1/hackathon/submit/preflight`, `POST /api/v1/hackathon/submit/upload`

## License

MIT
