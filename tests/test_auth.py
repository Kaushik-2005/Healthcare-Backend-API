def test_signup_login_and_duplicate_email(client):
    response = client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 201
    assert "password" not in response.text
    assert client.post("/auth/signup", json={"email": "A@example.com", "password": "password123"}).status_code == 409
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrongpass"}).status_code == 401


def test_protected_endpoint_requires_valid_token(client):
    assert client.get("/bookings").status_code == 401
    assert client.get("/bookings", headers={"Authorization": "Bearer invalid"}).status_code == 401

