"""Run a narrated end-to-end evaluation of the Healthcare Backend API."""

from __future__ import annotations

import os
import logging
import sys
import tempfile
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def show(step: str, message: str) -> None:
    print(f"\n[{step}] {message}")


def result(message: str) -> None:
    print(f"      -> {message}")


def flow(*nodes: str) -> None:
    print("      " + "  ->  ".join(f"[{node}]" for node in nodes))


def run_evaluation() -> None:
    database_path = Path(tempfile.gettempdir()) / "eve_healthcare_evaluation.db"
    database_path.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    os.environ["JWT_SECRET_KEY"] = "evaluation-secret-key-32-bytes-long"

    from datetime import datetime, timedelta, timezone

    warnings.filterwarnings("ignore")
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from app.database import SessionLocal, engine
    from app.main import app
    from app.models import Payment, User, WebhookEvent

    # The evaluator prints its own readable workflow; application JSON logs
    # remain available when running Uvicorn or Docker Compose directly.
    logging.getLogger("healthcare").setLevel(logging.CRITICAL)

    password = "password123"
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    try:
        with TestClient(app) as client:
            show("1/12", "Create user account")
            flow("CLIENT", "POST /auth/signup", "ROUTER", "AUTH SERVICE", "users TABLE")
            signup = client.post("/auth/signup", json={"email": "evaluation-owner@example.com", "password": password})
            assert signup.status_code == 201, signup.text
            owner_id = signup.json()["id"]
            result(f"email=evaluation-owner@example.com password=[masked] -> user_id={owner_id}, signup success")

            show("2/12", "Create second user for authorization checks")
            flow("CLIENT", "POST /auth/signup", "ROUTER", "AUTH SERVICE", "users TABLE")
            other_signup = client.post("/auth/signup", json={"email": "evaluation-other@example.com", "password": password})
            assert other_signup.status_code == 201, other_signup.text
            other_id = other_signup.json()["id"]
            result(f"email=evaluation-other@example.com password=[masked] -> user_id={other_id}, signup success")

            show("3/12", "Log in and issue JWT")
            flow("CLIENT", "POST /auth/login", "ROUTER", "PASSWORD VERIFY", "JWT SERVICE", "TOKEN")
            login = client.post("/auth/login", json={"email": "evaluation-owner@example.com", "password": password})
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]
            owner = {"Authorization": f"Bearer {token}"}
            result(f"user_id={owner_id} password=[masked] password_hash=[never printed] jwt=[masked] -> login success")

            show("4/12", "Browse centres and tests")
            flow("CLIENT", "GET /centres/tests", "ROUTER", "QUERY SERVICE", "CENTRES + TESTS TABLES")
            assert client.get("/health").status_code == 200
            assert client.get("/centres").status_code == 200
            assert client.get("/tests").status_code == 200
            centre_tests = client.get("/centres/1/tests")
            assert centre_tests.status_code == 200
            assert centre_tests.json()[0]["price"] == "500.00"
            result("health, centres, tests, and centre-specific pricing -> retrieval success")

            show("5/12", "Create pending booking")
            flow("CLIENT + JWT", "POST /bookings", "ROUTER", "BOOKING SERVICE", "PRICE LOOKUP", "bookings TABLE")
            booking_response = client.post("/bookings", headers=owner, json={"centre_id": 1, "test_id": 1, "appointment_at": future})
            assert booking_response.status_code == 201, booking_response.text
            booking = booking_response.json()
            booking_id = booking["id"]
            assert booking["status"] == "PENDING"
            assert booking["amount"] == "500.00"
            result(f"user_id={owner_id} -> booking_id={booking_id}, amount=500.00, status=PENDING")

            show("6/12", "Verify authorization enforcement")
            flow("SECOND USER + JWT", "BOOKING REQUEST", "OWNERSHIP CHECK", "REJECT")
            other_token = client.post("/auth/login", json={"email": "evaluation-other@example.com", "password": password}).json()["access_token"]
            other_user = {"Authorization": f"Bearer {other_token}"}
            assert client.get(f"/bookings/{booking_id}", headers=other_user).status_code == 404
            assert client.post(f"/bookings/{booking_id}/cancel", headers=other_user).status_code == 404
            assert client.post("/payments/", headers=other_user, json={"booking_id": booking_id}).status_code == 404
            result("second user cannot view, cancel, or pay the booking -> authorization success")

            show("7/12", "Process successful payment")
            flow("CLIENT + JWT", "POST /payments", "ROUTER", "PAYMENT SERVICE", "payments + bookings TABLES")
            payment_response = client.post("/payments/", headers=owner, json={"booking_id": booking_id, "simulate": "SUCCESS"})
            assert payment_response.status_code == 201, payment_response.text
            payment = payment_response.json()
            payment_id = payment["id"]
            assert client.get(f"/bookings/{booking_id}", headers=owner).json()["status"] == "CONFIRMED"
            result(f"booking_id={booking_id} -> payment_id={payment_id}, result=SUCCESS, booking=CONFIRMED")

            show("8/12", "Process the same webhook twice")
            flow("PAYMENT PROVIDER", "POST /payments/webhook", "WEBHOOK SERVICE", "UNIQUE event_id", "NO-OP DUPLICATE")
            event = {"event_id": "evaluation-success-event", "payment_id": payment_id, "status": "SUCCESS"}
            assert client.post("/payments/webhook/", json=event).status_code == 200
            assert client.post("/payments/webhook/", json=event).status_code == 200
            result("event_id=evaluation-success-event -> first processed, second ignored idempotently")

            show("9/12", "Process failed payment")
            flow("CLIENT + JWT", "POST /payments", "PAYMENT SERVICE", "FAILED RESULT", "bookings.status=FAILED")
            failed_booking = client.post("/bookings", headers=owner, json={"centre_id": 1, "test_id": 1, "appointment_at": future}).json()
            failed_payment = client.post("/payments/", headers=owner, json={"booking_id": failed_booking["id"], "simulate": "FAILED"})
            assert failed_payment.status_code == 201
            assert client.get(f"/bookings/{failed_booking['id']}", headers=owner).json()["status"] == "FAILED"
            result(f"booking_id={failed_booking['id']} -> result=FAILED, booking=FAILED")

            show("10/12", "Reject payment for cancelled booking")
            flow("CLIENT + JWT", "CANCEL BOOKING", "STATE MACHINE", "CANCELLED", "PAYMENT REJECTED")
            cancelled_booking = client.post("/bookings", headers=owner, json={"centre_id": 1, "test_id": 1, "appointment_at": future}).json()
            assert client.post(f"/bookings/{cancelled_booking['id']}/cancel", headers=owner).status_code == 200
            assert client.post("/payments/", headers=owner, json={"booking_id": cancelled_booking["id"]}).status_code == 409
            result(f"booking_id={cancelled_booking['id']} -> CANCELLED, payment rejected with 409")

            show("11/12", "Reject invalid requests")
            flow("INVALID REQUEST", "VALIDATION", "BUSINESS RULE", "HTTP ERROR")
            assert client.post("/bookings", headers=owner, json={"centre_id": 1, "test_id": 1, "appointment_at": "2020-01-01T00:00:00Z"}).status_code == 400
            assert client.post("/payments/webhook/", json={"event_id": "unknown", "payment_id": 99999, "status": "SUCCESS"}).status_code == 404
            result("past appointment -> 400; unknown payment webhook -> 404")

            show("12/12", "Verify persisted invariants")
            flow("DATABASE", "COUNT RECORDS", "CHECK CONSTRAINTS", "EVALUATION SUMMARY")
            with SessionLocal() as db:
                assert db.scalar(select(func.count()).select_from(Payment)) == 2
                assert db.scalar(select(func.count()).select_from(WebhookEvent)) == 1
                assert db.scalar(select(func.count()).select_from(User)) == 2
            result("2 users, 2 payments, 1 webhook event -> database invariants verified")
    finally:
        engine.dispose()
        database_path.unlink(missing_ok=True)

    print("\n+--------------------------------------------------+")
    print("|          AUTOMATED EVALUATION PASSED               |")
    print("|     Client -> Router -> Service -> Database        |")
    print("|      Auth -> Booking -> Payment -> Webhook         |")
    print("+----------------------------------------------------+")


if __name__ == "__main__":
    run_evaluation()
