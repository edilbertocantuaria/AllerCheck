from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ask_chat_question(client: TestClient) -> Callable[[dict[str, str], str, str, bool], str]:
    def _ask(
        headers: dict[str, str],
        conversation_id: str,
        question: str,
        use_hyde: bool = False,
    ) -> str:
        response = client.post(
            "/chat",
            json={
                "conversation_id": conversation_id,
                "question": question,
                "use_hyde": use_hyde,
            },
            headers=headers,
        )
        assert response.status_code == 200
        return response.text

    return _ask
