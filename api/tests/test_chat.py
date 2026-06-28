from fastapi.testclient import TestClient


def test_chat_flow_multiple_questions(client: TestClient, conversation_factory, ask_chat_question) -> None:
    headers, conversation_id = conversation_factory(
        email="chat.flow@example.com",
        title="Fluxo de teste",
    )

    questions = [
        "Quais são os sinais mais comuns de alergia a medicamentos?",
        "O que devo fazer ao suspeitar de uma reação alérgica?",
        "Quais informações devo levar para uma consulta sobre alergia medicamentosa?",
    ]

    for question in questions:
        response_text = ask_chat_question(headers, conversation_id, question)
        assert "Resposta de teste" in response_text

    messages_response = client.get(f"/conversations/{conversation_id}", headers=headers)
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 6


def test_chat_without_conversation_id(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/chat",
        json={"conversation_id": None, "question": "O que é anafilaxia?"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "conversation_id" in response.json()["detail"]


def test_chat_anonymous_without_auth(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={"conversation_id": None, "question": "O que é anafilaxia?"},
    )
    assert response.status_code == 200


def test_chat_with_use_hyde_flag(client: TestClient, conversation_factory) -> None:
    headers, conversation_id = conversation_factory(email="hyde.on@example.com")
    response = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "question": "Quais antihistamínicos causam sonolência?", "use_hyde": True},
        headers=headers,
    )
    assert response.status_code == 200


def test_chat_with_hyde_disabled(client: TestClient, conversation_factory) -> None:
    headers, conversation_id = conversation_factory(email="hyde.off@example.com")
    response = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "question": "Quais antihistamínicos causam sonolência?", "use_hyde": False},
        headers=headers,
    )
    assert response.status_code == 200


def test_chat_saves_messages_to_conversation(
    client: TestClient,
    conversation_factory,
    ask_chat_question,
) -> None:
    headers, conversation_id = conversation_factory(email="save.msg@example.com")

    ask_chat_question(headers, conversation_id, "Pergunta de teste")

    messages = client.get(f"/conversations/{conversation_id}", headers=headers).json()
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles


def test_chat_response_is_streaming_text(client: TestClient, conversation_factory) -> None:
    headers, conversation_id = conversation_factory(email="streaming@example.com")
    response = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "question": "Teste de streaming"},
        headers=headers,
    )
    assert response.status_code == 200
    assert isinstance(response.text, str)


def test_evaluate_chunks_endpoint(client: TestClient) -> None:
    response = client.post(
        "/evaluate/chunks",
        json={"conversation_id": None, "question": "Reação a dipirona"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "question" in body
    assert "chunks" in body
    assert "total_chunks" in body


def test_evaluate_detailed_endpoint(client: TestClient) -> None:
    response = client.post(
        "/evaluate/detailed",
        json={"conversation_id": None, "question": "Alergia a penicilina"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "question" in body
    assert "chunks" in body
    assert "use_hyde" in body
