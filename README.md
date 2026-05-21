# nepher-cli

Command-line interface for Nepher — **`--service account`** (coldkey registration) and **`--service hackathon`** (zip submission; no coldkey required). Behavior matches the internal product spec (`internal-docs/Hackathon/2. Python CLI SDK.md`).

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

To **replace** a coldkey already on your account, run the same command with the **new** wallet and complete signing; the account stores the new address after verification.

### API key (Nepher)

Use a key from **Account → API Keys** that is:

- **Not expired** — past `expires_at`, keys are rejected.
- **Active** — disabled / revoked keys are rejected.
- **Allowed for Hackathon when scoped** — if you limited the key to specific products, enable **Hackathon** on the API key. Keys with access to **all** platforms need no extra toggle.

### Submit to a hackathon

When **one** published event is in its submission window, the backend picks it automatically. If **several** are open, preflight fails until you pass **`--hackathon-id <UUID>`** (copy from the dashboard or hackathon URL).

```bash
nepher-cli --service hackathon submit --apikey <nepher_api_key> --submission submission.zip --assets assets.zip
nepher-cli --service hackathon submit --apikey <nepher_api_key> --hackathon-id <uuid> --submission submission.zip --assets assets.zip
```

You do **not** need a registered Bittensor coldkey to submit. A coldkey is only used for stake-weighted voting when an event uses open community scoring.

After preflight and again after a successful upload, the CLI prints how many submission attempts you have left for this hackathon.

Optional: `--public-source` maps to `submitter_public_source` when the backend supports it.

### Backend URL (development / staging / production)

Not shown in `--help`. **Pip installs default to production** — no env vars needed for end users.

**Precedence (highest first):** `--backend` → per-service URLs → single `NEPHER_CLI_BACKEND` → `NEPHER_CLI_ENV` preset → production defaults.

| Variable | Purpose |
|----------|---------|
| `NEPHER_CLI_ENV` | `production` (default), `staging`, or `development` — picks a **preset** pair of API bases. Aliases: `prod`, `stage`, `dev`, `local`. |
| `NEPHER_CLI_ACCOUNT_BACKEND` | Override **account** API base only (e.g. `http://127.0.0.1:8001`). |
| `NEPHER_CLI_HACKATHON_BACKEND` | Override **hackathon** API base only (e.g. `http://127.0.0.1:8002`). |
| `NEPHER_CLI_BACKEND` | One URL for **both** services (legacy / quick override when both APIs share the same origin). |

**Presets** (when only `NEPHER_CLI_ENV` is set, no overrides):

| `NEPHER_CLI_ENV` | Account API | Hackathon API |
|------------------|-------------|----------------|
| `production` (default) | `https://api.accounts.nepher.ai` | `https://api.hackathon.nepher.ai` |
| `staging` | `https://api.account-staging.nepher.ai` | `https://api.hackathon-staging.nepher.ai` |
| `development` | `http://127.0.0.1:8001` | `http://127.0.0.1:8002` |

Canonical URLs for all apps and APIs: `internal-docs/Hackathon/ENVIRONMENTS.md`.

**Examples**

```bash
# Local backends (account :8001, hackathon :8002)
export NEPHER_CLI_ENV=development
nepher-cli --service account register-coldkey --wallet mywallet --apikey nepher_xxx
```

```bash
# Staging preset
export NEPHER_CLI_ENV=staging
nepher-cli --service hackathon submit --apikey nepher_xxx --submission submission.zip --assets assets.zip
```

```bash
# Fine-grained overrides (e.g. account local, hackathon still staging)
export NEPHER_CLI_ENV=staging
export NEPHER_CLI_ACCOUNT_BACKEND=http://127.0.0.1:8001
nepher-cli --service account register-coldkey --wallet mywallet --apikey nepher_xxx
```

```bash
# Same origin for both (older style)
export NEPHER_CLI_BACKEND=https://localhost:8000
nepher-cli --service account register-coldkey --wallet mywallet --apikey nepher_xxx
```

## Defaults (production, no env)

| Service   | Default |
|-----------|---------|
| `account` | `https://api.accounts.nepher.ai` |
| `hackathon` | `https://api.hackathon.nepher.ai` |

## API paths (v1)

Illustrative — align with **account-backend** / **hackathon-backend** deployments:

- Account: `POST /api/v1/account/coldkey/challenge`, `POST /api/v1/account/coldkey/verify`
- Hackathon: `POST /api/v1/hackathon/submit/preflight`, `POST /api/v1/hackathon/submit/upload`

## License

MIT
