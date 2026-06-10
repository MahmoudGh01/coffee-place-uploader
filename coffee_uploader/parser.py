from __future__ import annotations

import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from .models import Payment, VALID_COFFEE_TYPES


REQUIRED_COLUMNS = ("idempotency_key", "coffee_type", "price", "currency")
OPTIONAL_COLUMNS = ("loyalty_card_id",)
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class CsvParseError(ValueError):
    """Raised when the CSV file is structurally invalid (header issues)."""


class RowError(ValueError):
    """Raised when a single CSV row fails validation."""

    def __init__(self, row_number: int, message: str):
        super().__init__(f"row {row_number}: {message}")
        self.row_number = row_number
        self.message = message


def parse_csv(path: Path) -> tuple[list[Payment], list[RowError]]:
    """Parse a payments CSV file.

    Returns (valid_payments, row_errors). Structural issues (missing required
    columns, unreadable file) raise CsvParseError instead — we can't recover.
    Row-level issues are collected so we can upload the good rows and report
    the bad ones.
    """
    payments: list[Payment] = []
    errors: list[RowError] = []
    seen_keys: set[str] = set()

    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise CsvParseError(f"{path}: file is empty")

        normalized = [f.strip() for f in reader.fieldnames]
        missing = [c for c in REQUIRED_COLUMNS if c not in normalized]
        if missing:
            raise CsvParseError(
                f"{path}: missing required columns: {', '.join(missing)}. "
                f"Found: {', '.join(normalized)}"
            )

        # csv.DictReader yields starting at line 2 (after header)
        for line_idx, raw_row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in raw_row.items() if k}
            if not any(row.values()):
                continue  # skip blank lines
            try:
                payment = _row_to_payment(line_idx, row)
            except RowError as e:
                errors.append(e)
                continue

            if payment.idempotency_key in seen_keys:
                errors.append(RowError(
                    line_idx,
                    f"duplicate idempotency_key '{payment.idempotency_key}' "
                    f"already used earlier in this file",
                ))
                continue
            seen_keys.add(payment.idempotency_key)
            payments.append(payment)

    return payments, errors


def _row_to_payment(row_number: int, row: dict[str, str]) -> Payment:
    idempotency_key = row.get("idempotency_key", "")
    if not idempotency_key:
        raise RowError(row_number, "idempotency_key is required")

    coffee_type = row.get("coffee_type", "").upper()
    if not coffee_type:
        raise RowError(row_number, "coffee_type is required")
    if coffee_type not in VALID_COFFEE_TYPES:
        raise RowError(
            row_number,
            f"invalid coffee_type '{coffee_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_COFFEE_TYPES))}",
        )

    price_raw = row.get("price", "")
    if not price_raw:
        raise RowError(row_number, "price is required")
    try:
        price = Decimal(price_raw)
    except InvalidOperation:
        raise RowError(row_number, f"price '{price_raw}' is not a valid number")
    if price <= 0:
        raise RowError(row_number, f"price must be greater than zero, got {price}")
    if price.as_tuple().exponent < -2:
        raise RowError(
            row_number,
            f"price '{price_raw}' has more than 2 decimal places",
        )

    currency = row.get("currency", "").upper()
    if not currency:
        raise RowError(row_number, "currency is required")
    if not CURRENCY_RE.match(currency):
        raise RowError(
            row_number,
            f"currency '{currency}' must be a 3-letter ISO-4217 code (e.g. EUR)",
        )

    # loyalty_card_id is optional in the CSV; the server requires the field
    # to be present in the JSON body but accepts an empty string.
    loyalty_card_id = row.get("loyalty_card_id", "")

    return Payment(
        row_number=row_number,
        idempotency_key=idempotency_key,
        coffee_type=coffee_type,
        price=price,
        currency=currency,
        loyalty_card_id=loyalty_card_id,
    )
