ALLOWED_ORIGIN = "http://localhost:5173"
DISALLOWED_ORIGIN = "https://evil.example"


def test_cors_simple_request_echoes_allowed_origin(client):
    response = client.get("/jobs", headers={"Origin": ALLOWED_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_cors_preflight_allows_get_from_allowed_origin(client):
    response = client.options(
        "/jobs",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_cors_disallowed_origin_is_not_echoed(client):
    response = client.get("/jobs", headers={"Origin": DISALLOWED_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != DISALLOWED_ORIGIN
