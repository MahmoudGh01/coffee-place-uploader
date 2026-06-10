from __future__ import annotations

from decimal import Decimal
from typing import Callable

import httpx
import pytest

from coffee_uploader.client import PaymentApiClient, RetryPolicy
from coffee_uploader.models import Payment, UploadStatus


def make_payment(key: str = "order-1") -> Payment:
    return Payment(
        row_number=2,
        idempotency_key=key,
        coffee_type="LATTE",
        price=Decimal("3.50"),
        currency="EUR",
        loyalty_card_id="card-1",
    )


def client_with(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_attempts: int = 3,
) -> PaymentApiClient:
    transport = httpx.MockTransport(handler)
    return PaymentApiClient(
        base_url="http://test",
        store_id="store-test",
        retry_policy=RetryPolicy(max_attempts=max_attempts, base_delay=0.0, jitter=0.0),
        http_client=httpx.Client(transport=transport),
    )


def test_created_on_first_try():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Store-Id"] == "store-test"
        assert request.headers["Idempotency-Key"] == "order-1"
        assert request.url.path == "/api/v1/payments"
        return httpx.Response(201, json={"paymentId": "p-123"})

    with client_with(handler) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.CREATED
    assert result.http_status == 201
    assert result.payment_id == "p-123"
    assert result.attempts == 1


def test_already_processed_returns_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"paymentId": "p-existing"})

    with client_with(handler) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.ALREADY_PROCESSED
    assert result.http_status == 200
    assert result.attempts == 1


def test_retries_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(201, json={"paymentId": "p-ok"})

    with client_with(handler, max_attempts=5) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.CREATED
    assert result.attempts == 3


def test_4xx_does_not_retry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="bad coffee")

    with client_with(handler, max_attempts=5) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.FAILED
    assert result.http_status == 400
    assert "bad coffee" in result.error
    assert calls["n"] == 1


def test_429_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, text="slow down")
        return httpx.Response(201, json={"paymentId": "p-ok"})

    with client_with(handler, max_attempts=3) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.CREATED
    assert result.attempts == 2


def test_exhausted_retries_returns_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="still busy")

    with client_with(handler, max_attempts=3) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.FAILED
    assert result.http_status is None
    # last_error is captured during the last attempt
    assert "503" in result.error
    assert result.attempts == 3


def test_network_error_retried_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(201, json={"paymentId": "p-ok"})

    with client_with(handler, max_attempts=3) as c:
        result = c.upload(make_payment())

    assert result.status == UploadStatus.CREATED
    assert result.attempts == 2


def test_request_body_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"paymentId": "p-1"})

    with client_with(handler) as c:
        c.upload(make_payment())

    assert captured["body"] == {
        "coffeeType": "LATTE",
        "price": "3.50",
        "currency": "EUR",
        "loyaltyCardId": "card-1",
    }
