# Async Payments Service

Standalone async bulk-payment service implemented as a subproject inside
`coffee-place-uploader`.

## What it does

- Accepts bulk payment requests.
- Stores request and items in a relational database (PostgreSQL).
- Returns a `requestId` immediately (`202 Accepted`).
- Lets clients query request status by `requestId`.
- Background worker sends each payment to `harbour-cloud-26` and updates status.

## API

### Submit bulk request

`POST /api/v1/bulk-payments`

Required header:

- `Store-Id: <store-id>`

Body:

```json
{
  "payments": [
    {
      "coffeeType": "LATTE",
      "price": "3.50",
      "currency": "EUR",
      "loyaltyCardId": "card-1"
    }
  ]
}
```

Response (`202`):

```json
{
  "requestId": "...",
  "status": "PENDING"
}
```

### Get status

`GET /api/v1/bulk-payments/{requestId}`

Response example:

```json
{
  "requestId": "...",
  "storeId": "coffee-place-01",
  "status": "DONE",
  "totalItems": 2,
  "processedItems": 2,
  "succeededItems": 2,
  "failedItems": 0,
  "createdAt": "...",
  "updatedAt": "..."
}
```

## Run with Docker Compose

From `async-payments-service/`:

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8100`
- Postgres: `localhost:5433`
- Worker: `bulk-worker` container

By default worker targets `HARBOUR_BASE_URL=http://host.docker.internal:8090`.
Make sure your `harbour-cloud-26` service is running and reachable there.

## Tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```
