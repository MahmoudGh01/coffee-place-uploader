from __future__ import annotations

import logging
from pathlib import Path

from .client import PaymentApiClient
from .models import Payment, UploadReport, UploadResult, UploadStatus
from .parser import RowError, parse_csv


log = logging.getLogger(__name__)


def upload_file(
    csv_path: Path,
    client: PaymentApiClient,
) -> tuple[UploadReport, list[RowError]]:
    """Parse a CSV and upload every valid row.

    Row-level CSV errors are returned separately so the caller can surface
    them — they do *not* abort the run; we want a single bad row not to
    stop a hundred good ones.
    """
    payments, row_errors = parse_csv(csv_path)

    if row_errors:
        log.warning(
            "%d row(s) in %s failed validation and will be skipped",
            len(row_errors), csv_path,
        )

    log.info("uploading %d valid payment(s) from %s", len(payments), csv_path)
    report = UploadReport()
    for idx, payment in enumerate(payments, start=1):
        log.info(
            "[%d/%d] uploading %s", idx, len(payments), payment.idempotency_key,
        )
        result = client.upload(payment)
        report.results.append(result)

    return report, row_errors


def format_summary(report: UploadReport, row_errors: list[RowError]) -> str:
    lines = [
        "=== Upload report ===",
        f"Total uploaded     : {report.total}",
        f"  created          : {report.created}",
        f"  already processed: {report.already_processed}",
        f"  failed           : {report.failed}",
        f"CSV row errors     : {len(row_errors)}",
        "=====================",
    ]

    failures = [r for r in report.results if r.status == UploadStatus.FAILED]
    if failures:
        lines.append("")
        lines.append("Upload failures:")
        for r in failures:
            lines.append(
                f"  row {r.payment.row_number} "
                f"(key={r.payment.idempotency_key}, attempts={r.attempts}): "
                f"{r.error}"
            )

    if row_errors:
        lines.append("")
        lines.append("Skipped rows (invalid):")
        for e in row_errors:
            lines.append(f"  {e}")

    return "\n".join(lines)
