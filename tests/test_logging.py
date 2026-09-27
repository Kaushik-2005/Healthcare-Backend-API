def test_request_id_is_returned(client):
    response = client.get("/health", headers={"X-Request-ID": "test-request-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"

