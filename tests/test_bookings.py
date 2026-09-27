from datetime import datetime, timedelta, timezone


def future_time():
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


def test_booking_snapshots_price_and_starts_pending(client, user_and_token):
    response = client.post("/bookings", headers=user_and_token, json={"centre_id": 1, "test_id": 1, "appointment_at": future_time()})
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING"
    assert response.json()["amount"] == "500.00"


def test_booking_accepts_timezone_less_iso_datetime(client, user_and_token):
    response = client.post("/bookings", headers=user_and_token, json={"centre_id": 1, "test_id": 1, "appointment_at": "2099-10-02T10:30:00"})
    assert response.status_code == 201


def test_booking_validation_and_ownership(client, user_and_token):
    assert client.post("/bookings", headers=user_and_token, json={"centre_id": 999, "test_id": 1, "appointment_at": future_time()}).status_code == 404
    assert client.post("/bookings", headers=user_and_token, json={"centre_id": 1, "test_id": 1, "appointment_at": "2020-01-01T00:00:00Z"}).status_code == 400
    booking = client.post("/bookings", headers=user_and_token, json={"centre_id": 1, "test_id": 1, "appointment_at": future_time()}).json()
    client.post("/auth/signup", json={"email": "b@example.com", "password": "password123"})
    token = client.post("/auth/login", json={"email": "b@example.com", "password": "password123"}).json()["access_token"]
    assert client.get(f"/bookings/{booking['id']}", headers={"Authorization": f"Bearer {token}"}).status_code == 404
