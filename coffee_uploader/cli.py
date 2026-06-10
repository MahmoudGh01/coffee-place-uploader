from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .client import PaymentApiClient, RetryPolicy
from .parser import CsvParseError, parse_csv
from .uploader import format_summary, upload_file


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="coffee-uploader",
        description=(
            "Upload daily coffee-shop payments from a CSV file to the "
            "StarHarbour Payments API. Safe to re-run — idempotency keys "
            "from the CSV prevent duplicates."
        ),
    )
    p.add_argument("csv_file", type=Path, help="Path to the payments CSV file")
    p.add_argument(
        "--api-url", required=True,
        help="Base URL of the Payments API, e.g. http://localhost:8080",
    )
    p.add_argument(
        "--store-id", required=True,
        help="Your store identifier, sent as the Store-Id header",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Parse and validate the CSV without sending anything",
    )
    p.add_argument(
        "--max-attempts", type=int, default=5,
        help="Max attempts per payment, including the first try (default: 5)",
    )
    p.add_argument(
        "--base-delay", type=float, default=1.0,
        help="Base delay (seconds) between retries; doubles each attempt (default: 1.0)",
    )
    p.add_argument(
        "--timeout", type=float, default=15.0,
        help="Per-request timeout in seconds (default: 15)",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG-level logging",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("coffee_uploader")

    if not args.csv_file.exists():
        log.error("CSV file not found: %s", args.csv_file)
        return 2

    if args.dry_run:
        try:
            payments, row_errors = parse_csv(args.csv_file)
        except CsvParseError as e:
            log.error("CSV is invalid: %s", e)
            return 2
        print(f"Parsed {len(payments)} valid row(s), {len(row_errors)} bad row(s).")
        for e in row_errors:
            print(f"  {e}")
        return 0 if not row_errors else 1

    policy = RetryPolicy(
        max_attempts=max(1, args.max_attempts),
        base_delay=max(0.0, args.base_delay),
    )

    try:
        with PaymentApiClient(
            base_url=args.api_url,
            store_id=args.store_id,
            timeout=args.timeout,
            retry_policy=policy,
        ) as client:
            report, row_errors = upload_file(args.csv_file, client)
    except CsvParseError as e:
        log.error("CSV is invalid: %s", e)
        return 2

    print(format_summary(report, row_errors))

    if not report.all_succeeded or row_errors:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
