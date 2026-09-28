def test_request_id_is_returned(client):
    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_sensitive_endpoints_return_rate_limit_headers(client):
    response = client.post("/auth/login", json={"email": "missing@example.com", "password": "password123"})
    assert response.status_code == 401
    assert response.headers["X-RateLimit-Limit"] == "20"
    assert "X-RateLimit-Remaining" in response.headers
