def test_centre_and_price_retrieval(client):
    centres = client.get("/centres")
    assert centres.status_code == 200
    centre_id = centres.json()[0]["id"]
    tests = client.get(f"/centres/{centre_id}/tests")
    assert tests.status_code == 200
    assert tests.json()[0]["price"] == "500.00"

