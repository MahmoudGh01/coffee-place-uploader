from __future__ import annotations


def test_submit_bulk_request_returns_request_id(client):
    response = client.post(
        "/api/v1/bulk-payments",
        headers={"Store-Id": "store-1"},
        json={
            "payments": [
                {
                    "coffeeType": "LATTE",
                    "price": "3.50",
                    "currency": "EUR",
                    "loyaltyCardId": "card-1",
                }
            ]
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["requestId"]
    assert body["status"] == "PENDING"


def test_get_bulk_status_returns_created_request(client):
    create_resp = client.post(
        "/api/v1/bulk-payments",
        headers={"Store-Id": "store-2"},
        json={
            "payments": [
                {
                    "coffeeType": "ESPRESSO",
                    "price": "2.00",
                    "currency": "EUR",
                    "loyaltyCardId": "card-2",
                }
            ]
        },
    )
    request_id = create_resp.json()["requestId"]

    status_resp = client.get(f"/api/v1/bulk-payments/{request_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["requestId"] == request_id
    assert body["storeId"] == "store-2"
    assert body["totalItems"] == 1
    assert body["processedItems"] == 0


def test_get_bulk_status_404_for_unknown_request(client):
    resp = client.get("/api/v1/bulk-payments/missing")
    assert resp.status_code == 404
