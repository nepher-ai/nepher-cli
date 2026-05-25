# nepher-cli

The command-line interface for [Nepher](https://nepher.ai)'s platforms—currently supporting account coldkey registration and hackathon submissions, with more integrations added over time.

**Requirements:** Python 3.10+

| Command | Extra tooling |
|---------|---------------|
| `register-coldkey` | [Bittensor](https://github.com/opentensor/bittensor) **`btcli`** on your `PATH` |
| `submit` | None (folders or zips only) |

## Install

```bash
pip install nepher-cli
```

Verify the install:

```bash
nepher-cli --version
nepher-cli --help
```

Run `nepher-cli --help`, `nepher-cli --service account register-coldkey --help`, or `nepher-cli --service hackathon submit --help` for full usage, flags, and examples.

## Quick start

### Register coldkey

Bind or replace the Bittensor coldkey on your Nepher account:

```bash
nepher-cli --service account register-coldkey \
  --wallet <wallet_name> \
  --apikey <nepher_api_key>
```

To replace an existing coldkey, run the same command with a different `--wallet` and complete signing when `btcli` prompts for your password.

### Submit to a hackathon

Upload your project and assets (the CLI zips folders for you):

```bash
nepher-cli --service hackathon submit \
  --apikey <nepher_api_key> \
  --title "My entry" \
  --submission ./my-project \
  --assets ./my-assets
```

When several hackathons are accepting submissions, add `--hackathon-id <UUID>` (from your dashboard URL `/dashboard/hackathons/<UUID>` or the list printed if preflight finds multiple open events).

Optional metadata:

```bash
nepher-cli --service hackathon submit \
  --apikey <nepher_api_key> \
  --hackathon-id <uuid> \
  --title "My entry" \
  --description "Markdown summary for your entry page." \
  --thumbnail ./cover.png \
  --submission ./my-project \
  --assets ./my-assets \
  --public-source
```

- **`--thumbnail`** — optional listing image (JPEG, PNG, WebP, or GIF). If omitted, one image from `--assets` is used as the submission thumbnail.

## API keys

Create a key at [account.nepher.ai](https://account.nepher.ai) (Account → API Keys):

- Must start with `nepher_`
- Must be **active** (not revoked) and **not expired**
- For `submit`, enable **Hackathon** access (or use a key with access to all platforms)

## Services

The CLI talks to Nepher production APIs automatically:

| Service | Command |
|---------|---------|
| Account | `register-coldkey` |
| Hackathon | `submit` |

Select the service with `-s` / `--service account` or `--service hackathon`.

## Notes

- You do **not** need a registered coldkey to **submit**. A coldkey is used for stake-weighted community voting when an event requires it.
- `--submission` accepts a project folder (recommended) or an existing `submission.zip`.
- `--assets` accepts a folder or `assets.zip` with images, videos, and PDFs only.
- After preflight and a successful upload, the CLI prints how many submission attempts you have left for that hackathon.

## Common problems

| Problem | What to do |
|---------|------------|
| `nepher-cli: command not found` | Ensure `pip install` succeeded and your Python scripts directory is on `PATH` |
| `error: --service is required` | Add `--service account` or `--service hackathon` |
| `invalid api key format` | Key must start with `nepher_` |
| `api key does not have hackathon access` | Enable **Hackathon** on the key or use an unrestricted key |
| `api key expired` | Create a new key with a later expiry |
| `btcli` / wallet not found | Run `btcli wallet list`; check `--wallet` name |
| `Several hackathons are accepting submissions` | Re-run with `--hackathon-id` from the listed UUIDs |
| `Unable to reach the Nepher backend` | Check your network connection |

For more detail on flags and examples, run `nepher-cli --help`.

## License

MIT
