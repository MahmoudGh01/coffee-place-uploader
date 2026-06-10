from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from coffee_uploader.parser import CsvParseError, parse_csv


def write_csv(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "payments.csv"
    p.write_text(content, encoding="utf-8")
    return p


def test_parses_valid_rows(tmp_path: Path):
    csv = write_csv(tmp_path, """\
idempotency_key,coffee_type,price,currency,loyalty_card_id
order-1,LATTE,3.50,EUR,card-1
order-2,ESPRESSO,2.00,EUR,
""")
    payments, errors = parse_csv(csv)
    assert errors == []
    assert len(payments) == 2
    assert payments[0].idempotency_key == "order-1"
    assert payments[0].coffee_type == "LATTE"
    assert payments[0].price == Decimal("3.50")
    assert payments[0].currency == "EUR"
    assert payments[0].loyalty_card_id == "card-1"
    assert payments[1].loyalty_card_id == ""


def test_missing_required_column_raises(tmp_path: Path):
    csv = write_csv(tmp_path, "idempotency_key,coffee_type,price\norder-1,LATTE,3.50\n")
    with pytest.raises(CsvParseError, match="missing required columns"):
        parse_csv(csv)


def test_invalid_rows_collected_not_raised(tmp_path: Path):
    csv = write_csv(tmp_path, """\
idempotency_key,coffee_type,price,currency,loyalty_card_id
order-1,LATTE,3.50,EUR,
,LATTE,3.50,EUR,
order-2,LATTE,not-a-number,EUR,
order-3,EXPRESSO,3.50,EUR,
order-4,LATTE,-1.00,EUR,
order-5,LATTE,3.001,EUR,
order-6,LATTE,3.50,EU,
order-7,,3.50,EUR,
order-8,LATTE,,EUR,
""")
    payments, errors = parse_csv(csv)
    assert len(payments) == 1
    assert payments[0].idempotency_key == "order-1"

    messages = [str(e) for e in errors]
    assert any("idempotency_key is required" in m for m in messages)
    assert any("not a valid number" in m for m in messages)
    assert any("invalid coffee_type" in m for m in messages)
    assert any("must be greater than zero" in m for m in messages)
    assert any("decimal places" in m for m in messages)
    assert any("ISO-4217" in m for m in messages)
    assert any("coffee_type is required" in m for m in messages)
    assert any("price is required" in m for m in messages)


def test_duplicate_idempotency_key_flagged(tmp_path: Path):
    csv = write_csv(tmp_path, """\
idempotency_key,coffee_type,price,currency,loyalty_card_id
order-1,LATTE,3.50,EUR,
order-1,ESPRESSO,2.00,EUR,
""")
    payments, errors = parse_csv(csv)
    assert len(payments) == 1
    assert len(errors) == 1
    assert "duplicate idempotency_key" in str(errors[0])


def test_blank_lines_skipped(tmp_path: Path):
    csv = write_csv(tmp_path, """\
idempotency_key,coffee_type,price,currency,loyalty_card_id
order-1,LATTE,3.50,EUR,

order-2,ESPRESSO,2.00,EUR,
""")
    payments, errors = parse_csv(csv)
    assert errors == []
    assert len(payments) == 2


def test_coffee_type_case_normalized(tmp_path: Path):
    csv = write_csv(tmp_path, """\
idempotency_key,coffee_type,price,currency,loyalty_card_id
order-1,latte,3.50,eur,
""")
    payments, errors = parse_csv(csv)
    assert errors == []
    assert payments[0].coffee_type == "LATTE"
    assert payments[0].currency == "EUR"
