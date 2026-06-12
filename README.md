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
  --api-url http://localhost:8090 \
  --store-id coffee-place-01
```

Or, after install, the entry-point script:

```bash
coffee-uploader examples/daily-payments.csv \
  --api-url http://localhost:8090 \
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

18 tests cover CSV parsing edge cases, HTTP client behavior (retry on
5xx/429/connection errors, no retry on 4xx, idempotent 200 vs 201
handling, exact request body shape), and load balancer selection/health logic.

## Redirect load balancer (Homework 1)

This repository now also includes a tiny **HTTP 302 redirect load balancer**
that can distribute traffic across several app instances from homework 1.

### Start it

```bash
coffee-redirect-lb \
  --instances http://localhost:8080,http://localhost:8081,http://localhost:8082 \
  --listen-port 8090
```

You can also provide instances from a file:

```bash
coffee-redirect-lb --instances-file ./instances.txt
```

Where `instances.txt` contains one URL per line (empty lines and `# comments`
are ignored).

If your backend addresses are internal (for example Docker service DNS names),
you can provide client-facing redirect addresses separately:

```bash
coffee-redirect-lb \
  --instances http://harbour-1:8090,http://harbour-2:8090,http://harbour-3:8090 \
  --public-instances http://localhost:8081,http://localhost:8082,http://localhost:8083
```

`--instances` is used for health checks; `--public-instances` is used in the
`Location` header for `302` redirects. Both lists must have the same size and
matching order.

### How it works

- `GET /_lb/services` — returns the list of configured services with current
  health status (`healthy: true/false`) and both internal/public URLs.
- `GET /_lb/health` — returns the load balancer health (`UP` when at least
  one backend is healthy, otherwise `DOWN` with `503`).
- Any other path is redirected with `302 Found` to a selected healthy backend
  preserving the original path/query string.

### Health checks

- Default check endpoint is `/actuator/health` on each backend.
- A backend is considered healthy when:
  - HTTP status is `2xx`, and
  - if the response is JSON with a `status` field, its value is `UP`.
- Configure with:
  - `--health-path` (default: `/actuator/health`)
  - `--health-timeout` (default: `2.0` seconds)
  - `--check-interval` (default: `5.0` seconds)

### Load balancing algorithm

The balancer uses **Round Robin** across healthy instances:

- Request 1 -> instance A
- Request 2 -> instance B
- Request 3 -> instance C
- then repeats from A

If no instance is healthy, the balancer returns `503 Service Unavailable`
instead of redirecting.

### Run with Docker Compose (LB + 3 harbour instances)

From `coffee-place-uploader/`:

```bash
docker compose up --build
```

Services exposed on host:

- Load balancer: `http://localhost:8090`
- Harbour instance 1: `http://localhost:8081`
- Harbour instance 2: `http://localhost:8082`
- Harbour instance 3: `http://localhost:8083`

The load balancer uses:

- backend list: `http://harbour-1:8090,http://harbour-2:8090,http://harbour-3:8090`
- public redirect list: `http://localhost:8081,http://localhost:8082,http://localhost:8083`
- `--health-path /` (important: current `harbour-cloud-26` image does not expose
  `/actuator/health` by default)

Quick checks:

```bash
# LB sees service health
curl -s http://localhost:8090/_lb/services

# LB health
curl -i http://localhost:8090/_lb/health

# Any regular route returns a redirect (302) to one healthy backend
curl -i http://localhost:8090/api/v1/payments?storeId=store-1
```

Run uploader through the LB:

```bash
coffee-uploader examples/daily-payments.csv \
  --api-url http://localhost:8090 \
  --store-id coffee-place-01
```

## Layout

```
coffee_uploader/
├── __main__.py    # python -m coffee_uploader
├── cli.py         # argparse entry point
├── load_balancer.py # 302 redirect load balancer service
├── models.py      # Payment, UploadResult, UploadReport
├── parser.py      # CSV → Payment with validation
├── client.py      # httpx client with retry + idempotency
└── uploader.py    # orchestrates parse → upload → summary
tests/
├── test_parser.py
├── test_client.py
└── test_load_balancer.py
examples/
└── daily-payments.csv
```
