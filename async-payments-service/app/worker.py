from __future__ import annotations

import logging
import time

from .config import HARBOUR_BASE_URL, WORKER_MAX_ATTEMPTS, WORKER_POLL_SECONDS
from . import db
from .models import ItemStatus
from .remote_client import HarbourRemoteClient
from .service import finalize_request, next_pending_request


log = logging.getLogger(__name__)


def process_once() -> bool:
    client = HarbourRemoteClient(HARBOUR_BASE_URL)
    with db.SessionLocal() as session:
        req = next_pending_request(session)
        if not req:
            return False

        for item in req.items:
            if item.status == ItemStatus.DONE:
                continue

            payload = {
                "coffeeType": item.coffee_type,
                "price": str(item.price),
                "currency": item.currency,
                "loyaltyCardId": item.loyalty_card_id,
            }

            item.status = ItemStatus.PROCESSING
            session.commit()

            for attempt in range(1, WORKER_MAX_ATTEMPTS + 1):
                result = client.create_payment(req.store_id, payload, item.id)
                item.attempts = attempt
                if result.success:
                    item.status = ItemStatus.DONE
                    item.remote_payment_id = result.payment_id
                    item.last_error = None
                    req.processed_items += 1
                    req.succeeded_items += 1
                    session.commit()
                    break

                item.last_error = result.error
                if not result.retryable or attempt == WORKER_MAX_ATTEMPTS:
                    item.status = ItemStatus.FAILED
                    req.processed_items += 1
                    req.failed_items += 1
                    session.commit()
                    break

        finalize_request(req)
        session.commit()
        log.info("processed request %s with status %s", req.id, req.status.value)
        return True


def run_forever() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    log.info("worker started, polling every %.1fs", WORKER_POLL_SECONDS)
    while True:
        handled = process_once()
        if not handled:
            time.sleep(WORKER_POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
