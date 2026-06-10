# Coffee Place Payment Uploader

A small, reliable Python CLI that reads a CSV of coffee-shop payments and
posts them to the **StarHarbour Payments API**
(`harbour-cloud-26`). Safe to re-run — every row carries an idempotency
key so retries never create duplicate payments.

## Why it exists

You own the Coffee Place. You collect payments in your notebook during the
day, and at end of day you need to ship them to Central System. This tool
is the automation that does it:

- Reads a CSV file of payments.
- Validates each row before sending anything.
- POSTs each row to `POST /api/v1/payments`.
- Retries transient failures (network errors, 5xx, 429) with exponential
  backoff + jitter; **does not** retry 4xx because retrying won't fix bad
  data.
- Uses `Idempotency-Key` on every request — if a network blip causes you
  to re-send a payment that the server already accepted, you get back
  `200 OK` with the original payment ID, not a duplicate.

## Requirements

- Python 3.10+ (tested on 3.14)
- The Payments API reachable somewhere — see
  [`../harbour-cloud-26`](../harbour-cloud-26)

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

(The `[dev]` extra pulls in `pytest`; drop it for a pure runtime install.)

## Usage

```bash
python -m coffee_uploader examples/daily-payments.csv \
  --api-url http://localhost:8080 \
  --store-id coffee-place-01
```

Or, after install, the entry-point script:

```bash
coffee-uploader examples/daily-payments.csv \
  --api-url http://localhost:8080 \
  --store-id coffee-place-01
```

### All flags

| Flag | Default | What it does |
|---|---|---|
| `csv_file` | — | Path to the CSV (positional) |
| `--api-url` | — | Base URL of the Payments API |
| `--store-id` | — | Sent as the `Store-Id` header |
| `--dry-run` | off | Parse + validate the CSV without sending anything |
| `--max-attempts` | `5` | Attempts per payment, *including* the first try |
| `--base-delay` | `1.0` | Seconds; doubles each attempt (capped at 30s) |
| `--timeout` | `15.0` | Per-request timeout, seconds |
| `--verbose` | off | DEBUG-level logs |

### CSV format

```csv
idempotency_key,coffee_type,price,currency,loyalty_card_id
order-2026-06-09-001,LATTE,3.50,EUR,card-loyal-123
order-2026-06-09-002,ESPRESSO,2.00,EUR,
```

- `idempotency_key` — any unique string per row. Re-uploads with the same
  key + `store-id` are idempotent on the server.
- `coffee_type` — one of: `ESPRESSO`, `DOUBLE_ESPRESSO`, `AMERICANO`,
  `LATTE`, `CAPPUCCINO`, `FLAT_WHITE`, `MOCHA`, `CORTADO`, `MACCHIATO`,
  `COLD_BREW`.
- `price` — positive, max 2 decimal places.
- `currency` — 3-letter ISO-4217 code (`EUR`, `USD`, ...).
- `loyalty_card_id` — optional; leave blank if no card.

See [`examples/daily-payments.csv`](examples/daily-payments.csv).

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Every row uploaded successfully |
| `1` | At least one row failed to upload, or the CSV had invalid rows |
| `2` | Could not start: file missing or structurally bad CSV |

## How reliability is built in

| Concern | How we handle it |
|---|---|
| **Network blip mid-upload** | Up to `--max-attempts` retries with exponential backoff + jitter |
| **Server overloaded (5xx, 429)** | Retried; `Retry-After` header honored on 429 |
| **Bad data (400)** | Not retried — reported in the failure summary |
| **Phantom writes** (server processed the request but client never saw the response) | Same `Idempotency-Key` on the next attempt → server replies `200` with the original payment, no duplicate |
| **Re-running the whole CSV** | Same — every key replays as `200 already_processed` |
| **One bad row** | Doesn't abort the run — skipped, reported at the end |
| **Hanging server** | Per-request `--timeout` |

## Demo against `harbour-cloud-26` with fault injection

```bash
# Inject 3s of latency via Toxiproxy
curl -X POST http://localhost:8474/proxies/spring-boot-app/toxics \
  -H "Content-Type: application/json" \
  -d '{"name":"slow","type":"latency","attributes":{"latency":3000}}'

# Run against the Toxiproxy port with a tight timeout — retries will fire
python -m coffee_uploader examples/daily-payments.csv \
  --api-url http://localhost:9091 \
  --store-id coffee-place-01 \
  --timeout 1 --max-attempts 3 --base-delay 0.3

# Remove the toxic; re-run — idempotency makes it safe even if some of
# the timed-out requests actually reached the server.
curl -X DELETE http://localhost:8474/proxies/spring-boot-app/toxics/slow
python -m coffee_uploader examples/daily-payments.csv \
  --api-url http://localhost:9091 \
  --store-id coffee-place-01
```

## Tests

```bash
pytest
```

14 tests cover CSV parsing edge cases and HTTP client behavior (retry on
5xx/429/connection errors, no retry on 4xx, idempotent 200 vs 201
handling, exact request body shape).

## Layout

```
coffee_uploader/
├── __main__.py    # python -m coffee_uploader
├── cli.py         # argparse entry point
├── models.py      # Payment, UploadResult, UploadReport
├── parser.py      # CSV → Payment with validation
├── client.py      # httpx client with retry + idempotency
└── uploader.py    # orchestrates parse → upload → summary
tests/
├── test_parser.py
└── test_client.py
examples/
└── daily-payments.csv
```
