from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


VALID_COFFEE_TYPES = frozenset({
    "ESPRESSO",
    "DOUBLE_ESPRESSO",
    "AMERICANO",
    "LATTE",
    "CAPPUCCINO",
    "FLAT_WHITE",
    "MOCHA",
    "CORTADO",
    "MACCHIATO",
    "COLD_BREW",
})


class UploadStatus(str, Enum):
    CREATED = "created"
    ALREADY_PROCESSED = "already_processed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Payment:
    """A payment row read from the CSV — already validated.

    `idempotency_key` is opaque to the server; we just send it back on the
    `Idempotency-Key` header to make retries safe.
    """
    row_number: int
    idempotency_key: str
    coffee_type: str
    price: Decimal
    currency: str
    loyalty_card_id: str

    def to_api_body(self) -> dict:
        return {
            "coffeeType": self.coffee_type,
            "price": str(self.price),
            "currency": self.currency,
            "loyaltyCardId": self.loyalty_card_id,
        }


@dataclass
class UploadResult:
    payment: Payment
    status: UploadStatus
    http_status: int | None = None
    payment_id: str | None = None
    error: str | None = None
    attempts: int = 0


@dataclass
class UploadReport:
    results: list[UploadResult] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for r in self.results if r.status == UploadStatus.CREATED)

    @property
    def already_processed(self) -> int:
        return sum(1 for r in self.results if r.status == UploadStatus.ALREADY_PROCESSED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == UploadStatus.FAILED)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def all_succeeded(self) -> bool:
        return self.failed == 0
