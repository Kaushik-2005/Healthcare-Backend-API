"""Run the required automated and end-to-end evaluation checks."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def run_tests() -> None:
    print("[1/2] Running pytest...")
    result = subprocess.run([sys.executable, "-m", "pytest"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def run_end_to_end() -> None:
    database_path = Path(tempfile.gettempdir()) / "eve_healthcare_evaluation.db"
    database_path.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    os.environ["JWT_SECRET_KEY"] = "evaluation-secret-key-32-bytes-long"

    from datetime import datetime, timedelta, timezone

    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from app.database import SessionLocal, engine
    from app.main import app
    from app.models import Payment, WebhookEvent

    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    print("[2/2] Running end-to-end API checks...")
    with TestClient(app) as client:
        def signup(email: str) -> dict[str, str]:
            response = client.post("/auth/signup", json={"email": email, "password": "password123"})
            assert response.status_code == 201, response.text
            token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["access_token"]
            return {"Authorization": f"Bearer {token}"}

        owner = signup("evaluation-owner@example.com")
        other_user = signup("evaluation-other@example.com")

        assert client.get("/health").status_code == 200
        assert client.get("/centres").status_code == 200
        assert client.get("/tests").status_code == 200
        assert client.get("/centres/1/tests").json()[0]["price"] == "500.00"
        assert client.get("/bookings").status_code == 401
        assert client.post("/auth/signup", json={"email": "EVALUATION-OWNER@example.com", "password": "password123"}).status_code == 409

        booking = client.post(
            "/bookings",
            headers=owner,
            json={"centre_id": 1, "test_id": 1, "appointment_at": future},
        )
        assert booking.status_code == 201, booking.text
        booking_data = booking.json()
        assert booking_data["status"] == "PENDING"
        assert booking_data["amount"] == "500.00"

        booking_id = booking_data["id"]
        assert client.get(f"/bookings/{booking_id}", headers=other_user).status_code == 404
        assert client.post(f"/bookings/{booking_id}/cancel", headers=other_user).status_code == 404
        assert client.post("/payments/", headers=other_user, json={"booking_id": booking_id}).status_code == 404

        payment = client.post("/payments/", headers=owner, json={"booking_id": booking_id, "simulate": "SUCCESS"})
        assert payment.status_code == 201, payment.text
        payment_id = payment.json()["id"]
        assert client.get(f"/bookings/{booking_id}", headers=owner).json()["status"] == "CONFIRMED"

        event = {"event_id": "evaluation-success-event", "payment_id": payment_id, "status": "SUCCESS"}
        assert client.post("/payments/webhook/", json=event).status_code == 200
        assert client.post("/payments/webhook/", json=event).status_code == 200

        failed_booking = client.post(
            "/bookings",
            headers=owner,
            json={"centre_id": 1, "test_id": 1, "appointment_at": future},
        ).json()
        failed_payment = client.post(
            "/payments/",
            headers=owner,
            json={"booking_id": failed_booking["id"], "simulate": "FAILED"},
        )
        assert failed_payment.status_code == 201
        assert client.get(f"/bookings/{failed_booking['id']}", headers=owner).json()["status"] == "FAILED"

        cancelled_booking = client.post(
            "/bookings",
            headers=owner,
            json={"centre_id": 1, "test_id": 1, "appointment_at": future},
        ).json()
        assert client.post(f"/bookings/{cancelled_booking['id']}/cancel", headers=owner).status_code == 200
        assert client.post("/payments/", headers=owner, json={"booking_id": cancelled_booking["id"]}).status_code == 409

        assert client.post(
            "/bookings",
            headers=owner,
            json={"centre_id": 1, "test_id": 1, "appointment_at": "2020-01-01T00:00:00Z"},
        ).status_code == 400
        assert client.post("/payments/webhook/", json={"event_id": "unknown", "payment_id": 99999, "status": "SUCCESS"}).status_code == 404

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 2
        assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1

    engine.dispose()
    database_path.unlink(missing_ok=True)
    print("Evaluation passed: required API flows and invariants are working.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Run only the end-to-end API checks")
    args = parser.parse_args()
    if not args.skip_tests:
        run_tests()
    run_end_to_end()


if __name__ == "__main__":
    main()
