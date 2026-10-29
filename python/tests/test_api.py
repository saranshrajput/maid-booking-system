from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from maidbooking.api import create_app

MAID = {"name": "Asha", "locality": "Koramangala", "gender": "FEMALE", "rating": 4.5,
        "hourlyRates": {"CLEANING": 200}, "skills": ["deep-cleaning"],
        "availability": [{"day": d, "start": "08:00", "end": "20:00"} for d in range(7)]}


def test_discover_book_pay_cancel_end_to_end():
    client = TestClient(create_app())
    maid_id = client.post("/api/maids", json=MAID).json()["id"]
    start = (datetime.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
    search = {"locality": "koramangala", "date": start.date().isoformat(), "startTime": "10:00"}

    assert [m["id"] for m in client.get("/api/maids/search", params=search).json()] == [maid_id]

    body = {"customerId": "c1", "maidId": maid_id, "serviceType": "CLEANING", "bookingType": "SCHEDULED",
            "durationMinutes": 60, "startDateTime": start.isoformat()}
    booking = client.post("/api/bookings", json=body)
    assert booking.status_code == 201
    assert client.post("/api/bookings", json=body).status_code == 409
    assert client.get("/api/maids/search", params=search).json() == []

    pay = client.post(f"/api/bookings/{booking.json()['id']}/payments", headers={"Idempotency-Key": "k1"},
                      json={"method": "UPI", "instrument": "asha@upi"})
    assert pay.status_code == 201

    cancel = client.post(f"/api/bookings/{booking.json()['id']}/cancel").json()
    assert cancel["totalRefund"] == 200.0
    assert cancel["booking"]["status"] == "CANCELLED"
    assert [m["id"] for m in client.get("/api/maids/search", params=search).json()] == [maid_id]


def test_invalid_requests_return_400_and_404():
    client = TestClient(create_app())
    assert client.post("/api/maids", json={}).status_code == 400
    assert client.get("/api/bookings/nope").status_code == 404
    assert client.get("/api/maids/search", params={"date": "2030-01-01"}).status_code == 400


def test_postgres_backed_app_survives_restart():
    import os
    import pytest
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from tests.conftest import reset_database
    reset_database(url)

    first = TestClient(create_app(database_url=url))
    maid_id = first.post("/api/maids", json=MAID).json()["id"]
    assert first.get("/health").json() == {"status": "ok", "storage": "postgres"}

    restarted = TestClient(create_app(database_url=url))  # Fresh app, same database.
    assert restarted.get(f"/api/maids/{maid_id}").status_code == 200
