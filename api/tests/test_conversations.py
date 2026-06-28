from fastapi.testclient import TestClient


def test_create_and_list_conversations(client: TestClient, auth_headers) -> None:
    create_response = client.post(
        "/conversations",
        json={"title": "Conversation Layer"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201

    list_response = client.get("/conversations", headers=auth_headers)
    assert list_response.status_code == 200
    conversations = list_response.json()
    assert len(conversations) >= 1


def test_get_messages_empty_initially(client: TestClient, auth_headers) -> None:
    create_response = client.post(
        "/conversations",
        json={"title": "Mensagem vazia"},
        headers=auth_headers,
    )
    conversation_id = create_response.json()["id"]

    messages_response = client.get(f"/conversations/{conversation_id}", headers=auth_headers)
    assert messages_response.status_code == 200
    assert messages_response.json() == []


def test_delete_conversation(client: TestClient, conversation_factory) -> None:
    headers, conversation_id = conversation_factory(email="delete.conv@example.com")

    delete_response = client.delete(f"/conversations/{conversation_id}", headers=headers)
    assert delete_response.status_code == 204

    fetch_response = client.get(f"/conversations/{conversation_id}", headers=headers)
    assert fetch_response.status_code == 404


def test_cannot_access_other_users_conversation(
    client: TestClient,
    auth_headers_factory,
    conversation_factory,
) -> None:
    _, conversation_id = conversation_factory(email="owner@example.com")
    other_headers = auth_headers_factory("intruder@example.com")

    response = client.get(f"/conversations/{conversation_id}", headers=other_headers)
    assert response.status_code == 404


def test_cannot_delete_other_users_conversation(
    client: TestClient,
    auth_headers_factory,
    conversation_factory,
) -> None:
    _, conversation_id = conversation_factory(email="owner2@example.com")
    other_headers = auth_headers_factory("intruder2@example.com")

    response = client.delete(f"/conversations/{conversation_id}", headers=other_headers)
    assert response.status_code == 404


def test_get_nonexistent_conversation_returns_404(client: TestClient, auth_headers) -> None:
    response = client.get("/conversations/id-que-nao-existe", headers=auth_headers)
    assert response.status_code == 404


def test_delete_nonexistent_conversation_returns_404(client: TestClient, auth_headers) -> None:
    response = client.delete("/conversations/id-que-nao-existe", headers=auth_headers)
    assert response.status_code == 404


def test_conversation_list_is_isolated_per_user(
    client: TestClient,
    auth_headers_factory,
) -> None:
    headers_a = auth_headers_factory("userA@example.com")
    headers_b = auth_headers_factory("userB@example.com")

    client.post("/conversations", json={"title": "Conversa do User A"}, headers=headers_a)

    list_b = client.get("/conversations", headers=headers_b).json()
    titles = [c["title"] for c in list_b]
    assert "Conversa do User A" not in titles


def test_create_conversation_response_shape(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/conversations",
        json={"title": "Shape test"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert "title" in body
    assert "created_at" in body
    assert body["title"] == "Shape test"


def test_deleted_conversation_disappears_from_list(
    client: TestClient,
    conversation_factory,
) -> None:
    headers, conversation_id = conversation_factory(email="list.delete@example.com")

    client.delete(f"/conversations/{conversation_id}", headers=headers)

    conversations = client.get("/conversations", headers=headers).json()
    ids = [c["id"] for c in conversations]
    assert conversation_id not in ids
