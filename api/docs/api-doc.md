# Allercheck API - API Documentation

## Overview

REST API em FastAPI com autenticacao JWT, login Google, persistencia em PostgreSQL e resposta de chat em streaming.

- Base URL local: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

## Authentication

Endpoints protegidos exigem header:

```http
Authorization: Bearer <access_token>
```

Fluxo recomendado:

1. `POST /auth/register` (opcional para criar conta).
2. `POST /auth/login` ou `POST /auth/google`.
3. Usar `access_token` nas chamadas protegidas.

## Error Shape

```json
{
  "detail": "Human-readable message"
}
```

## Endpoints

### 1. Register

`POST /auth/register`

Cria conta por email/senha.

Request:

```json
{
  "email": "user@example.com",
  "password": "minimum6chars"
}
```

Responses:

- `201 Created`

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "created_at": "2026-03-15T14:00:00.000000+00:00"
}
```

- `409` email ja cadastrado
- `422` payload invalido
- `503` DB indisponivel

### 2. Login (JSON)

`POST /auth/login`

Request:

```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```

Response `200`:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```

Erros comuns:

- `401` credenciais invalidas
- `422` payload invalido
- `503` DB indisponivel

### 3. Login OAuth2 Form (Swagger)

`POST /auth/token`

Body: `application/x-www-form-urlencoded`

- `username`: email
- `password`: senha

Resposta igual a `/auth/login`.

### 4. Login com Google

`POST /auth/google`

Request:

```json
{
  "id_token": "google-id-token"
}
```

Comportamento:

1. Valida `id_token` no endpoint `https://oauth2.googleapis.com/tokeninfo`.
2. Verifica `aud` igual a `GOOGLE_CLIENT_ID`.
3. Exige email verificado.
4. Cria usuario automaticamente se não existir.

Response `200`:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```

Erros comuns:

- `401` token invalido ou email não verificado
- `503` Google auth não configurado ou servico indisponivel

### 5. Create Conversation

`POST /conversations` (protegido)

Request:

```json
{
  "title": "Minha conversa"
}
```

`title` pode ser `null`.

Response `201`:

```json
{
  "id": "uuid",
  "title": "Minha conversa",
  "created_at": "2026-03-15T14:05:00.000000+00:00"
}
```

### 6. List Conversations

`GET /conversations` (protegido)

Response `200`:

```json
[
  {
    "id": "uuid",
    "title": "Minha conversa",
    "created_at": "2026-03-15T14:05:00.000000+00:00"
  }
]
```

### 7. Get Conversation Messages

`GET /conversations/{conversation_id}` (protegido)

Response `200`:

```json
[
  {
    "id": "uuid",
    "role": "user",
    "content": "Pergunta",
    "created_at": "2026-03-15T14:10:00.000000+00:00"
  },
  {
    "id": "uuid",
    "role": "assistant",
    "content": "Resposta",
    "created_at": "2026-03-15T14:10:03.000000+00:00"
  }
]
```

Erros:

- `404` conversa não encontrada

### 8. Delete Conversation

`DELETE /conversations/{conversation_id}` (protegido)

Response `204 No Content`.

Erros:

- `404` conversa não encontrada

### 9. Chat (Streaming)

`POST /chat` (autenticado ou anonimo)

Request:

```json
{
  "conversation_id": "uuid-opcional",
  "history": [
    { "role": "user", "content": "Pergunta anterior" },
    { "role": "assistant", "content": "Resposta anterior" }
  ],
  "question": "Quais sinais podem indicar alergia a medicamentos?"
}
```

Response `200`:

- `Content-Type: text/plain`
- corpo em streaming (chunked)

Nao retorna JSON nesse endpoint. O cliente deve ler stream incrementalmente.

Comportamentos relevantes:

1. Com token JWT: usa `conversation_id`, busca historico no banco e persiste novas mensagens.
2. Sem token: aceita chat anonimo e usa `history` enviado pelo cliente como contexto.
3. Se autenticado e titulo estiver vazio/untitled, gera titulo automaticamente por LLM.

Erros:

- `400` quando autenticado sem `conversation_id`
- `404` conversa não encontrada
- `422` payload invalido

## Exemplo de consumo do /chat (Frontend)

```ts
const response = await fetch('http://localhost:8000/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  },
  body: JSON.stringify({
    conversation_id: conversationId, // opcional em modo anonimo
    history: localHistory, // opcional, usado no modo anonimo
    question: message,
  }),
})

if (!response.ok || !response.body) {
  throw new Error('Chat request failed')
}

const reader = response.body.getReader()
const decoder = new TextDecoder()
let fullText = ''

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  fullText += decoder.decode(value, { stream: true })
}
```

## Notes for Integrators

1. Prefira usar as rotas proxy do frontend (`web/app/api/*`) para evitar expor URL interna da API no browser.
2. O token JWT atual não possui refresh token; refaca login quando expirar.
3. Para login Google em ambiente local, configure origem `http://localhost:3000` no Google Cloud.
