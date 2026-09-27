import os

os.environ["DATABASE_URL"] = "sqlite:///./test_eve_healthcare.db"
os.environ["JWT_SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Booking, CentreTest, DiagnosticCentre, DiagnosticTest, Payment, User, WebhookEvent


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for model in (WebhookEvent, Payment, Booking, CentreTest, DiagnosticCentre, DiagnosticTest, User):
            db.execute(delete(model))
        db.commit()
        centre = DiagnosticCentre(name="EVE Diagnostics", location="Bengaluru")
        test = DiagnosticTest(name="Complete Blood Count", description="CBC blood test")
        db.add_all([centre, test])
        db.flush()
        db.add(CentreTest(centre_id=centre.id, test_id=test.id, price=500))
        db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_and_token(client):
    client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

