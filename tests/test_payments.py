from tests.test_bookings import future_time


def create_booking(client, headers):
    return client.post("/bookings", headers=headers, json={"centre_id": 1, "test_id": 1, "appointment_at": future_time()}).json()


def test_success_and_failed_simulated_payments(client, user_and_token):
    booking = create_booking(client, user_and_token)
    payment = client.post("/payments/", headers=user_and_token, json={"booking_id": booking["id"], "simulate": "SUCCESS"})
    assert payment.status_code == 201
    assert payment.json()["status"] == "SUCCESS"
    assert client.get(f"/bookings/{booking['id']}", headers=user_and_token).json()["status"] == "CONFIRMED"
    failed_booking = create_booking(client, user_and_token)
    assert client.post("/payments/", headers=user_and_token, json={"booking_id": failed_booking["id"], "simulate": "FAILED"}).status_code == 201
    assert client.get(f"/bookings/{failed_booking['id']}", headers=user_and_token).json()["status"] == "FAILED"


def test_payment_authorization_and_cancelled_booking(client, user_and_token):
    booking = create_booking(client, user_and_token)
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=user_and_token).status_code == 200
    assert client.post("/payments/", headers=user_and_token, json={"booking_id": booking["id"]}).status_code == 409

