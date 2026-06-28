from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_headers_factory(client: TestClient) -> Callable[[str | None, str], dict[str, str]]:
    def _factory(email: str | None = None, password: str = "123456") -> dict[str, str]:
        resolved_email = email or f"test-{uuid4().hex}@example.com"

        register_response = client.post(
            "/auth/register",
            json={"email": resolved_email, "password": password},
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/auth/login",
            json={"email": resolved_email, "password": password},
        )
        assert login_response.status_code == 200

        token = login_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _factory


@pytest.fixture()
def auth_headers(auth_headers_factory: Callable[[str | None, str], dict[str, str]]) -> dict[str, str]:
    return auth_headers_factory()
