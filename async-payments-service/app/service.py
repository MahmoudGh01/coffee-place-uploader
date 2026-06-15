from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import BulkRequest, BulkRequestItem, ItemStatus, RequestStatus


def create_bulk_request(db: Session, store_id: str, payments: list[dict]) -> BulkRequest:
    request = BulkRequest(
        store_id=store_id,
        status=RequestStatus.PENDING,
        total_items=len(payments),
        processed_items=0,
        succeeded_items=0,
        failed_items=0,
    )
    db.add(request)
    db.flush()

    for payment in payments:
        db.add(
            BulkRequestItem(
                request_id=request.id,
                coffee_type=payment["coffeeType"],
                price=Decimal(str(payment["price"])),
                currency=payment["currency"],
                loyalty_card_id=payment["loyaltyCardId"],
                status=ItemStatus.PENDING,
                attempts=0,
            )
        )

    db.commit()
    db.refresh(request)
    return request


def get_bulk_request(db: Session, request_id: str) -> BulkRequest | None:
    stmt = select(BulkRequest).options(selectinload(BulkRequest.items)).where(BulkRequest.id == request_id)
    return db.execute(stmt).scalars().first()


def next_pending_request(db: Session) -> BulkRequest | None:
    stmt = (
        select(BulkRequest)
        .options(selectinload(BulkRequest.items))
        .where(BulkRequest.status == RequestStatus.PENDING)
        .order_by(BulkRequest.created_at.asc())
    )
    req = db.execute(stmt).scalars().first()
    if not req:
        return None
    req.status = RequestStatus.PROCESSING
    db.commit()
    db.refresh(req)
    return req


def finalize_request(request: BulkRequest) -> None:
    if request.failed_items == 0:
        request.status = RequestStatus.DONE
    elif request.succeeded_items == 0:
        request.status = RequestStatus.FAILED
    else:
        request.status = RequestStatus.DONE_WITH_ERRORS
