from tests.test_bookings import future_time


def test_webhook_is_idempotent(client, user_and_token):
    booking = client.post("/bookings", headers=user_and_token, json={"centre_id": 1, "test_id": 1, "appointment_at": future_time()}).json()
    payment = client.post("/payments/", headers=user_and_token, json={"booking_id": booking["id"], "simulate": "SUCCESS"}).json()
    payload = {"event_id": "evt_123", "payment_id": payment["id"], "status": "SUCCESS"}
    for _ in range(3):
        response = client.post("/payments/webhook/", json=payload)
        assert response.status_code == 200
    assert client.get(f"/bookings/{booking['id']}", headers=user_and_token).json()["status"] == "CONFIRMED"


def test_webhook_unknown_payment(client):
    assert client.post("/payments/webhook/", json={"event_id": "evt_unknown", "payment_id": 999, "status": "SUCCESS"}).status_code == 404

