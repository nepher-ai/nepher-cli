# nepher-cli

Command-line tools for Nepher — **`--service account`** (Bittensor coldkey binding) and **`--service hackathon`** (project + assets upload). Production defaults are baked in; no env vars needed for normal use.

**Requirements:** Python 3.10+

| Command | Extra tooling |
|---------|-------------|
| `register-coldkey` | [Bittensor](https://github.com/opentensor/bittensor) **`btcli`** on your `PATH` |
| `submit` | None (folders or zips only) |

## Install

```bash
pip install nepher-cli
```

From this repository:

```bash
pip install -e ".[dev]"
```

Check the install:

```bash
nepher-cli --version
nepher-cli --help
```

## Commands

| Service | Command | Purpose |
|---------|---------|---------|
| `account` | `register-coldkey` | Bind or replace the Bittensor coldkey on your Nepher account (wallet signing via `btcli`) |
| `hackathon` | `submit` | Upload `submission.zip` + `assets.zip` (CLI can zip folders for you) |

Global flags:

| Flag | Required | Description |
|------|----------|-------------|
| `-s` / `--service` | Yes | `account` or `hackathon` — selects which API base URL to use |
| `--version` | No | Print package version |

`--backend` exists for development overrides but is hidden from `--help`.

### Register coldkey

```bash
nepher-cli --service account register-coldkey --wallet <wallet_name> --apikey <nepher_api_key>
```

**Replace an existing coldkey:** run the same command with a **different** wallet, complete signing when `btcli` prompts for your password; the account stores the new address after verification.

**API key rules** (Account → API Keys):

- Must start with `nepher_`
- Must be **active** (not revoked)
- Must **not be expired**
- If the key is scoped to specific platforms, enable **Hackathon** (or use a key with access to all platforms)

### Submit to a hackathon

#### Choosing a hackathon (`--hackathon-id`)

Several published hackathons can be in the **submission** phase at the same time. The CLI must know **which event** you are entering.

| Situation | What to do |
|-----------|------------|
| **One** event in submission | Omit `--hackathon-id`. Preflight picks it automatically. |
| **Several** events in submission | Pass **`--hackathon-id <UUID>`** on every `submit` run. |

**Where to get the UUID**

- Hackathon dashboard URL: `/dashboard/hackathons/<UUID>` (use the UUID segment, not the public slug).
- Hackathon list on [hackathon.nepher.ai](https://hackathon.nepher.ai) — open the event and copy the id from the URL or admin detail page.

**If you omit `--hackathon-id` and more than one window is open**, preflight fails with `multiple_hackathons` and prints each open event, for example:

```
Several hackathons are accepting submissions. Pass --hackathon-id with one of:
Open submission windows:
  • 550e8400-e29b-41d4-a716-446655440010 — Robotic Movement Sprint
  • 6ba7b810-9dad-11d1-80b4-00c04fd430c8 — Dexterous Grasp Challenge
Re-run with --hackathon-id <UUID> to choose one.
```

Then submit again with the id you want:

```bash
nepher-cli --service hackathon submit \
  --apikey <nepher_api_key> \
  --hackathon-id 550e8400-e29b-41d4-a716-446655440010 \
  --title "My entry" \
  --submission ./my-project \
  --assets ./my-assets
```

When only one event qualifies, this works without `--hackathon-id`:

```bash
nepher-cli --service hackathon submit \
  --apikey <nepher_api_key> \
  --title "My entry" \
  --submission ./my-project \
  --assets ./my-assets
```

Full example with optional metadata:

```bash
nepher-cli --service hackathon submit \
  --apikey <nepher_api_key> \
  --hackathon-id <uuid> \
  --title "My entry" \
  --description "Markdown summary shown on your entry page." \
  --submission ./my-project \
  --assets ./my-assets \
  --public-source
```

| Flag | Required | Description |
|------|----------|-------------|
| `--apikey` | Yes | Nepher API key (same rules as above) |
| `--hackathon-id` | **When multiple events are in submission** | Target hackathon UUID (see table above). Optional when exactly one event is open. |
| `--title` | Yes | Entry title, max **200** characters |
| `--description` | No | Markdown description for the entry page |
| `--submission` | Yes | Project **folder** (recommended) or existing **`submission.zip`** |
| `--assets` | Yes | **Folder** (recommended) or **`assets.zip`** — images, videos, and PDFs only |
| `--public-source` | No | Opt in to public source download when the event allows it (`submitter_public_source`) |

**Coldkey and submit:** you do **not** need a registered coldkey to **submit**. A coldkey is used for **stake-weighted community voting** when an event uses open community scoring; register with `register-coldkey` before voting if required by the event.

**Inputs:**

| Input | Rules |
|-------|--------|
| `--submission` folder | Any layout; CLI blocks unsafe paths, executables (`.exe`, …), and common secret patterns in source files, then zips to `submission.zip` |
| `--submission` zip | Same checks applied inside the archive |
| `--assets` folder / zip | Images (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`), videos (`.mp4`, `.webm`, `.mov`), PDFs (`.pdf`) only; counts and per-file size caps come from preflight |

After preflight and after a successful upload, the CLI prints how many submission attempts you have left for that hackathon (`submissions_remaining` / `max_submissions_per_user`).

**Typical terminal flow:**

```
Checking submission...
Checking assets...
Verifying your API key and submission eligibility...
Hackathon: <uuid> — <title>
Eligible now: N of M upload attempt(s) remaining …
Validating assets against hackathon limits...
Zipping my-project → nepher-submission-….zip
Zipping my-assets → nepher-assets-….zip
Uploading submission.zip (…) and assets.zip (…)…
Submission uploaded successfully.
  Submission ID: …
  Status: pending (pending review)
```

## Backend URLs

**Precedence (highest first):** `--backend` → `NEPHER_CLI_ACCOUNT_BACKEND` / `NEPHER_CLI_HACKATHON_BACKEND` → `NEPHER_CLI_BACKEND` (both services) → `NEPHER_CLI_ENV` preset → production defaults.

| Variable | Purpose |
|----------|---------|
| `NEPHER_CLI_ENV` | `production` (default), `staging`, or `development` — aliases: `prod`, `stage`, `dev`, `local` |
| `NEPHER_CLI_ACCOUNT_BACKEND` | Override account API only (e.g. `http://127.0.0.1:8001`) |
| `NEPHER_CLI_HACKATHON_BACKEND` | Override hackathon API only (e.g. `http://127.0.0.1:8002`) |
| `NEPHER_CLI_BACKEND` | Single URL for **both** services (legacy / shared origin) |

| `NEPHER_CLI_ENV` | Account API | Hackathon API |
|------------------|-------------|----------------|
| `production` (default) | `https://api.accounts.nepher.ai` | `https://api.hackathon.nepher.ai` |
| `staging` | `https://api.account-staging.nepher.ai` | `https://api.hackathon-staging.nepher.ai` |
| `development` | `http://127.0.0.1:8001` | `http://127.0.0.1:8002` |

Canonical URLs for all environments: `internal-docs/Hackathon/ENVIRONMENTS.md` (in the Nepher monorepo).

**Examples**

```bash
# Local backends (account :8001, hackathon :8002)
export NEPHER_CLI_ENV=development
nepher-cli --service account register-coldkey --wallet mywallet --apikey nepher_xxx
nepher-cli --service hackathon submit --apikey nepher_xxx --hackathon-id <uuid> --title "Test" --submission ./proj --assets ./assets
```

```bash
# Staging preset (always pass --hackathon-id when several events overlap)
export NEPHER_CLI_ENV=staging
nepher-cli --service hackathon submit --apikey nepher_xxx --hackathon-id <uuid> --title "My entry" --submission ./my-project --assets ./my-assets
```

```bash
# Account local, hackathon still staging
export NEPHER_CLI_ENV=staging
export NEPHER_CLI_ACCOUNT_BACKEND=http://127.0.0.1:8001
nepher-cli --service account register-coldkey --wallet mywallet --apikey nepher_xxx
```

## API paths (v1)

The CLI calls these routes on the resolved hackathon / account base URL:

| Service | Method | Path |
|---------|--------|------|
| Account | `POST` | `/api/v1/account/coldkey/challenge` |
| Account | `POST` | `/api/v1/account/coldkey/verify` |
| Hackathon | `POST` | `/api/v1/hackathon/submit/preflight` |
| Hackathon | `POST` | `/api/v1/hackathon/submit/upload` |

Preflight and upload accept JSON / multipart `api_key` and optional `hackathon_id` when multiple events are in the submission window. The website may use scoped paths under `/api/v1/hackathons/<uuid>/submit/…`; the CLI uses the global `/api/v1/hackathon/submit/…` routes with the same body fields.

## Common problems

### Register coldkey

| Problem | What to do |
|---------|------------|
| `nepher-cli: command not found` | Ensure `pip install` succeeded and your Python scripts directory is on `PATH` |
| `error: --service is required` | Use `--service account` for `register-coldkey` |
| `invalid api key format` | Key must start with `nepher_` |
| `api key does not have hackathon access` | Enable **Hackathon** on the key or use an unrestricted key |
| `api key expired` | Create a new key with a later expiry |
| `btcli` / wallet not found | Run `btcli wallet list`; check `--wallet` name |
| `Unable to reach the Nepher backend` | Check network and `NEPHER_CLI_*` URL overrides |

### Submit

| Problem | What to do |
|---------|------------|
| `Path not found` | Check `--submission` and `--assets` paths |
| `must be a directory or zip file` | Pass a folder or `.zip`, not a single loose file |
| `submission folder is empty` / requirement errors | Add files; fix blocked types or paths listed in the output |
| `assets exceed … limit` | Reduce image/video/PDF count or size per preflight limits |
| `Unsupported asset type` | Only images, videos, and PDFs in `--assets` |
| `title is required` / `title is too long` | Pass non-empty `--title`, max 200 characters |
| `Several hackathons are accepting submissions` | Re-run with `--hackathon-id` from the listed UUIDs |
| `No hackathon is accepting submissions` | No published event in submission phase |
| `used all allowed submission attempts` | Quota exhausted for that event; check the dashboard |
| `submission.zip is too large` | Shrink project or check `max_submission_zip_mb` from the event |
| `Unable to reach the Nepher backend` | Check network and backend URL configuration |

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

## License

MIT
