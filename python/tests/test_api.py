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


def test_list_bookings_by_customer_and_ui_is_served():
    client = TestClient(create_app())
    maid_id = client.post("/api/maids", json=MAID).json()["id"]
    start = (datetime.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)

    def book(customer, hour):
        body = {"customerId": customer, "maidId": maid_id, "serviceType": "CLEANING", "bookingType": "SCHEDULED",
                "durationMinutes": 60, "startDateTime": start.replace(hour=hour).isoformat()}
        return client.post("/api/bookings", json=body).json()["id"]

    a1, a2, b1 = book("alice", 10), book("alice", 12), book("bob", 14)
    listed = client.get("/api/bookings", params={"customerId": "alice"}).json()
    assert {b["id"] for b in listed} == {a1, a2}
    assert [b["id"] for b in listed] == [a2, a1]  # latest first
    assert [b["id"] for b in client.get("/api/bookings", params={"customerId": "bob"}).json()] == [b1]
    assert client.get("/api/bookings", params={"customerId": "nobody"}).json() == []
    assert client.get("/api/bookings").status_code == 400

    page = client.get("/")
    assert page.status_code == 200 and "Maid Booking" in page.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/health").json()["status"] == "ok"  # API routes still win over the static mount


def test_meta_and_slot_availability():
    now = datetime(2030, 1, 7, 10, 0)
    client = TestClient(create_app(clock=lambda: now))
    assert client.get("/api/meta").json()["now"] == "2030-01-07T10:00:00"

    maid_id = client.post("/api/maids", json=MAID).json()["id"]  # works 08:00-20:00 every day
    params = {"date": "2030-01-08", "durationMinutes": 60, "locality": "Koramangala", "serviceType": "CLEANING"}

    def counts():
        return {s["time"]: s["available"] for s in client.get("/api/availability/slots", params=params).json()}

    first = counts()
    assert first["07:45"] == 0 and first["08:00"] == 1 and first["19:00"] == 1 and first["19:15"] == 0
    assert first["06:00"] == 0 and first["22:00"] == 0

    client.post("/api/bookings", json={"customerId": "c", "maidId": maid_id, "serviceType": "CLEANING",
                                       "bookingType": "SCHEDULED", "durationMinutes": 60,
                                       "startDateTime": "2030-01-08T10:00"})
    booked = counts()
    assert booked["09:15"] == 0 and booked["09:45"] == 0 and booked["10:45"] == 0  # overlap with 10:00-11:00
    assert booked["09:00"] == 1 and booked["11:00"] == 1                           # back-to-back is fine

    assert counts() == booked
    today = {s["time"]: s["available"] for s in client.get(
        "/api/availability/slots", params={**params, "date": "2030-01-07"}).json()}
    assert today["10:00"] == 0 and today["10:15"] == 1  # a start that is not after now is not offered
    assert client.get("/api/availability/slots", params={"durationMinutes": 60}).status_code == 400


def test_pagination_localities_and_service_summary():
    client = TestClient(create_app())
    for i in range(5):
        client.post("/api/maids", json={**MAID, "name": f"Maid {i}", "rating": 4.0 + i / 10,
                                         "locality": "Koramangala" if i < 4 else "Indiranagar"})

    first = client.get("/api/maids/search", params={"limit": 2})
    assert [m["name"] for m in first.json()] == ["Maid 4", "Maid 3"]
    assert first.headers["X-Total-Count"] == "5"
    second = client.get("/api/maids/search", params={"limit": 2, "offset": 2})
    assert [m["name"] for m in second.json()] == ["Maid 2", "Maid 1"]
    assert client.get("/api/maids/search", params={"locality": "koramangala"}).headers["X-Total-Count"] == "4"
    assert client.get("/api/maids/search", params={"limit": 0}).status_code == 400
    assert client.get("/api/maids/search", params={"limit": 101}).status_code == 400

    assert client.get("/api/localities").json() == ["Indiranagar", "Koramangala"]
    assert client.get("/api/services/summary").json() == {"CLEANING": {"maids": 5, "minHourlyRate": 200.0}}
    assert client.get("/api/services/summary", params={"locality": "indiranagar"}).json()["CLEANING"]["maids"] == 1
    assert client.get("/api/services/summary", params={"locality": "nowhere"}).json() == {}
