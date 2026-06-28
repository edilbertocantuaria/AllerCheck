# Allercheck Web

Frontend Next.js da aplicacao, com autenticacao, historico de conversas e interface de chat em streaming.

## Escopo deste modulo

1. Login/cadastro por email e login Google.
2. Proxy para a API por meio de rotas internas `app/api/*`.
3. Interface de chat com renderizacao incremental da resposta.
4. Sidebar com gerenciamento de conversas.

## Stack

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS
- shadcn/ui + Radix UI

## Estrutura principal

```text
web/
├── app/
│   ├── page.tsx
│   ├── login/page.tsx
│   ├── register/page.tsx
│   └── api/
│       ├── auth/
│       ├── chat/
│       └── conversations/
├── components/
├── contexts/
├── hooks/
└── package.json
```

## Variaveis de ambiente

Arquivo local: `web/.env.local`

```dotenv
API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
```

Notas:

- `API_BASE_URL` e usada pelas rotas proxy em `app/api/*`.
- Em Docker Compose, o valor padrao e `http://api:8000`.
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` e injetada no build do web via `docker-compose.yml`.

## Rodando em desenvolvimento

```bash
cd web
pnpm install
pnpm dev
```

Acesse: `http://localhost:3000`.

## Rodando com Docker Compose

No diretorio raiz do projeto:

```bash
docker compose up -d --build web api db
```

Para subir todo o ambiente (incluindo pgadmin e ingest-worker):

```bash
docker compose up -d --build
```

## Fluxo de integracao com API

1. Browser chama as rotas Next internas (`/api/...`).
2. Cada rota interna encaminha a requisicao para a API FastAPI (`API_BASE_URL`).
3. O token JWT e gerenciado no cliente e enviado no header `Authorization`.
4. No chat, o proxy repassa o streaming da API para o browser.

## Scripts

```bash
cd web
pnpm dev
pnpm lint
pnpm build
pnpm start
```

## Troubleshooting rapido

1. Erro de conexao com a API no frontend:
	confira `API_BASE_URL` e se a API esta acessivel.
2. Botao Google indisponivel:
	valide `NEXT_PUBLIC_GOOGLE_CLIENT_ID`.
3. Falha no build Docker do web:
	confirme se `GOOGLE_CLIENT_ID` esta definido no `.env` da raiz.
