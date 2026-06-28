from fastapi.testclient import TestClient


def test_register_and_login_issue_token(client: TestClient, auth_headers_factory) -> None:
    headers = auth_headers_factory("auth.layer@example.com")
    assert "Authorization" in headers


def test_login_with_wrong_password_fails(client: TestClient) -> None:
    client.post("/auth/register", json={"email": "wrong-pass@example.com", "password": "123456"})

    login_response = client.post(
        "/auth/login",
        json={"email": "wrong-pass@example.com", "password": "senha-invalida"},
    )
    assert login_response.status_code == 401


def test_token_endpoint_with_form(client: TestClient) -> None:
    client.post("/auth/register", json={"email": "oauth-form@example.com", "password": "123456"})

    token_response = client.post(
        "/auth/token",
        data={"username": "oauth-form@example.com", "password": "123456"},
    )
    assert token_response.status_code == 200
    payload = token_response.json()
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"


def test_auth_headers_access_protected_route(client: TestClient, auth_headers) -> None:
    list_response = client.get("/conversations", headers=auth_headers)
    assert list_response.status_code == 200


def test_missing_auth_is_rejected(client: TestClient) -> None:
    response = client.get("/conversations")
    assert response.status_code == 401


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    payload = {"email": "duplicate@example.com", "password": "123456"}
    first = client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/auth/register", json=payload)
    assert second.status_code == 409


def test_login_nonexistent_user_fails(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "naoexiste@example.com", "password": "qualquer"},
    )
    assert response.status_code == 401


def test_token_endpoint_wrong_password_fails(client: TestClient) -> None:
    client.post("/auth/register", json={"email": "form-wrong@example.com", "password": "123456"})

    response = client.post(
        "/auth/token",
        data={"username": "form-wrong@example.com", "password": "errada"},
    )
    assert response.status_code == 401


def test_register_invalid_email_returns_422(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "nao-e-um-email", "password": "123456"},
    )
    assert response.status_code == 422


def test_register_response_contains_expected_fields(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "fields@example.com", "password": "123456"},
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["email"] == "fields@example.com"
    assert "created_at" in body


def test_login_response_contains_token_type(client: TestClient) -> None:
    client.post("/auth/register", json={"email": "tokentype@example.com", "password": "abc123"})
    response = client.post(
        "/auth/login",
        json={"email": "tokentype@example.com", "password": "abc123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 10
