from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .schemas import BulkCreateRequest, BulkCreateResponse, BulkStatusResponse
from .service import create_bulk_request, get_bulk_request


app = FastAPI(title="Async Payments Service", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.post("/api/v1/bulk-payments", response_model=BulkCreateResponse, status_code=202)
def submit_bulk_request(
    payload: BulkCreateRequest,
    store_id: str = Header(alias="Store-Id"),
    db: Session = Depends(get_db),
) -> BulkCreateResponse:
    request = create_bulk_request(
        db,
        store_id=store_id,
        payments=[payment.model_dump() for payment in payload.payments],
    )
    return BulkCreateResponse(requestId=request.id, status=request.status.value)


@app.get("/api/v1/bulk-payments/{request_id}", response_model=BulkStatusResponse)
def get_bulk_request_status(request_id: str, db: Session = Depends(get_db)) -> BulkStatusResponse:
    request = get_bulk_request(db, request_id)
    if not request:
        raise HTTPException(status_code=404, detail=f"request {request_id} not found")

    return BulkStatusResponse(
        requestId=request.id,
        storeId=request.store_id,
        status=request.status.value,
        totalItems=request.total_items,
        processedItems=request.processed_items,
        succeededItems=request.succeeded_items,
        failedItems=request.failed_items,
        createdAt=request.created_at,
        updatedAt=request.updated_at,
    )
