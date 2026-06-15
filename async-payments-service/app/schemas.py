from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentIn(BaseModel):
    coffeeType: str
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    loyaltyCardId: str


class BulkCreateRequest(BaseModel):
    payments: list[PaymentIn] = Field(min_length=1)


class BulkCreateResponse(BaseModel):
    requestId: str
    status: str


class BulkStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requestId: str
    storeId: str
    status: str
    totalItems: int
    processedItems: int
    succeededItems: int
    failedItems: int
    createdAt: datetime
    updatedAt: datetime
