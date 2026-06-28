from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def conversation_factory(
    client: TestClient,
    auth_headers_factory: Callable[[str | None, str], dict[str, str]],
) -> Callable[[str | None, str], tuple[dict[str, str], str]]:
    def _factory(
        email: str | None = None,
        title: str = "Conversa de teste",
    ) -> tuple[dict[str, str], str]:
        headers = auth_headers_factory(email)

        response = client.post(
            "/conversations",
            json={"title": title},
            headers=headers,
        )
        assert response.status_code == 201

        conversation_id = response.json()["id"]
        return headers, conversation_id

    return _factory
