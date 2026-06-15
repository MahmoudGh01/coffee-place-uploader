from __future__ import annotations

from app.models import BulkRequest
from app.models import ItemStatus, RequestStatus
from app.service import create_bulk_request
from app.worker import process_once


class SuccessClient:
    def create_payment(self, store_id: str, payment: dict, item_id: str):
        class Result:
            success = True
            payment_id = f"p-{item_id}"
            retryable = False
            error = None

        return Result()


class FailureClient:
    def create_payment(self, store_id: str, payment: dict, item_id: str):
        class Result:
            success = False
            payment_id = None
            retryable = False
            error = "bad request"

        return Result()


def test_worker_marks_request_done_on_success(db_session, monkeypatch):
    create_bulk_request(
        db_session,
        "store-1",
        [{"coffeeType": "LATTE", "price": "3.50", "currency": "EUR", "loyaltyCardId": "card-1"}],
    )

    monkeypatch.setattr("app.worker.HarbourRemoteClient", lambda _: SuccessClient())

    assert process_once() is True

    req = db_session.query(BulkRequest).first()
    assert req.status == RequestStatus.DONE
    assert req.processed_items == 1
    assert req.succeeded_items == 1
    assert req.failed_items == 0
    assert req.items[0].status == ItemStatus.DONE


def test_worker_marks_request_failed_when_all_items_fail(db_session, monkeypatch):
    create_bulk_request(
        db_session,
        "store-2",
        [{"coffeeType": "ESPRESSO", "price": "2.00", "currency": "EUR", "loyaltyCardId": "card-2"}],
    )

    monkeypatch.setattr("app.worker.HarbourRemoteClient", lambda _: FailureClient())

    assert process_once() is True

    req = db_session.query(BulkRequest).first()
    assert req.status == RequestStatus.FAILED
    assert req.processed_items == 1
    assert req.succeeded_items == 0
    assert req.failed_items == 1
    assert req.items[0].status == ItemStatus.FAILED
