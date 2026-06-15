from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class RemoteResult:
    success: bool
    payment_id: str | None = None
    retryable: bool = False
    error: str | None = None


class HarbourRemoteClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def create_payment(self, store_id: str, payment: dict, item_id: str) -> RemoteResult:
        url = f"{self._base_url}/api/v1/payments"
        headers = {
            "Store-Id": store_id,
            "Idempotency-Key": f"bulk-{item_id}-{uuid.uuid4()}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers=headers, json=payment)
        except httpx.HTTPError as exc:
            return RemoteResult(success=False, retryable=True, error=f"network error: {exc}")

        if response.status_code in (200, 201):
            payment_id = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    payment_id = body.get("paymentId")
            except ValueError:
                payment_id = None
            return RemoteResult(success=True, payment_id=payment_id)

        retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
        return RemoteResult(
            success=False,
            retryable=retryable,
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )
