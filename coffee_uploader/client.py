from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import httpx

from .models import Payment, UploadResult, UploadStatus


log = logging.getLogger(__name__)


# Status codes that mean "try again later, this might recover".
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 1.0   # seconds, before backoff is applied
    max_delay: float = 30.0   # seconds, cap on a single sleep
    jitter: float = 0.25      # +/- fraction of the computed delay


def _backoff_seconds(attempt: int, policy: RetryPolicy) -> float:
    """Exponential backoff with bounded jitter."""
    base = min(policy.base_delay * (2 ** (attempt - 1)), policy.max_delay)
    jitter = base * policy.jitter
    return max(0.0, base + random.uniform(-jitter, jitter))


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Honor a server-supplied Retry-After header when present."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None  # we don't parse HTTP-date form; backoff handles it


class PaymentApiClient:
    """Posts payments to the StarHarbour Payments API.

    Idempotency-Key is always sent so retries are safe end-to-end. Transient
    failures (network errors, 5xx, 429) get retried with exponential backoff;
    permanent client errors (4xx other than 429) are returned as failures
    immediately — retrying won't fix them.
    """

    def __init__(
        self,
        base_url: str,
        store_id: str,
        *,
        timeout: float = 15.0,
        retry_policy: RetryPolicy | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.store_id = store_id
        self.retry_policy = retry_policy or RetryPolicy()
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> "PaymentApiClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def upload(self, payment: Payment) -> UploadResult:
        url = f"{self.base_url}/api/v1/payments"
        headers = {
            "Store-Id": self.store_id,
            "Idempotency-Key": payment.idempotency_key,
            "Content-Type": "application/json",
        }
        body = payment.to_api_body()

        last_error: str | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                response = self._http.post(url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning(
                    "payment %s attempt %d/%d network error: %s",
                    payment.idempotency_key, attempt,
                    self.retry_policy.max_attempts, last_error,
                )
                if attempt < self.retry_policy.max_attempts:
                    time.sleep(_backoff_seconds(attempt, self.retry_policy))
                continue

            status = response.status_code

            if status in (200, 201):
                payment_id = _safe_payment_id(response)
                result_status = (
                    UploadStatus.CREATED if status == 201
                    else UploadStatus.ALREADY_PROCESSED
                )
                log.info(
                    "payment %s %s (status=%d, attempt=%d)",
                    payment.idempotency_key,
                    "created" if status == 201 else "already processed",
                    status, attempt,
                )
                return UploadResult(
                    payment=payment,
                    status=result_status,
                    http_status=status,
                    payment_id=payment_id,
                    attempts=attempt,
                )

            if status in RETRYABLE_STATUSES:
                last_error = f"HTTP {status}: {_short_body(response)}"
                if attempt < self.retry_policy.max_attempts:
                    delay = (
                        _retry_after_seconds(response)
                        if status == 429
                        else None
                    ) or _backoff_seconds(attempt, self.retry_policy)
                    log.warning(
                        "payment %s attempt %d/%d transient error %s; "
                        "retrying in %.1fs",
                        payment.idempotency_key, attempt,
                        self.retry_policy.max_attempts, last_error, delay,
                    )
                    time.sleep(delay)
                else:
                    log.warning(
                        "payment %s attempt %d/%d transient error %s; "
                        "no retries left",
                        payment.idempotency_key, attempt,
                        self.retry_policy.max_attempts, last_error,
                    )
                continue

            # Permanent client error — retrying won't help.
            error = f"HTTP {status}: {_short_body(response)}"
            log.error(
                "payment %s permanent error %s (no retry)",
                payment.idempotency_key, error,
            )
            return UploadResult(
                payment=payment,
                status=UploadStatus.FAILED,
                http_status=status,
                error=error,
                attempts=attempt,
            )

        return UploadResult(
            payment=payment,
            status=UploadStatus.FAILED,
            error=last_error or "exhausted retries",
            attempts=self.retry_policy.max_attempts,
        )


def _safe_payment_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        return body.get("paymentId") or body.get("id")
    return None


def _short_body(response: httpx.Response, limit: int = 200) -> str:
    text = response.text or ""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "..."
