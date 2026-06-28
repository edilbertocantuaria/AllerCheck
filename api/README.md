# AllerCheck API

Backend FastAPI responsável por autenticação, gerenciamento de conversas e respostas RAG com suporte a múltiplos provedores de LLM (OpenAI, Gemini, Ollama local).

## Escopo deste módulo

1. Autenticação: Cadastro/login com JWT e Google OAuth.
2. Gerenciamento de conversas: CRUD com isolamento por usuário.
3. Chat em streaming (`POST /chat`): RAG em tempo real.
4. Avaliação detalhada: Análise com reescrita, reranking e provider info.
5. Comparação LLM vs SLM: Benchmark de custo/latência entre provedores.
6. Ingestionração incremental: Indexação de PDFs com auditoria.
7. Persistência em PostgreSQL e vector database (Pinecone).

## Documentação de referência

- Endpoints e contratos: `docs/api-doc.md`
- Operação de ingestão: `docs/ingest-instruction.md`
- Arquitetura geral: `docs/architecture.md`

## Stack

- **Python 3.11** + **FastAPI 0.120+**
- **SQLAlchemy** + **psycopg2** (PostgreSQL)
- **LangChain** (LLM orchestration)
- **Pinecone** (vector database)
- **OpenAI**, **Gemini**, **Ollama** (múltiplos provedores)
- **RAGAS** (avaliação automática)

Dependências completas em `requirements.txt`.

## Estrutura principal

```text
api/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── core/
│   │   └── settings.py
│   ├── auth.py
│   ├── models.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   └── templates/
│   ├── routers/
│   │   ├── auth.py
│   │   ├── conversations.py
│   │   └── chat.py
│   └── services/
│       ├── chat_service.py
│       ├── chat_response_service.py
│       └── conversation_service.py
├── ingestion/
│   └── ingest_documents.py
├── docs/
├── logs/
└── tests/
```

## Configuração

A API lê configuração **apenas de variáveis de ambiente** (arquivo `.env` na raiz do projeto).

**Nota**: `api/config.yaml` é **deprecated** e mantido apenas para compatibilidade de código antigo.

### Variáveis Obrigatórias

- `OPENAI_API_KEY` ou `GEMINI_API_KEY` (conforme provider)
- `PINECONE_API_KEY`
- `JWT_SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- **Temperaturas** (sem fallback):
  - `REWRITE_TEMPERATURE` (padrão: 0.1)
  - `ANSWER_TEMPERATURE` (padrão: 0.2)
  - `EVALUATOR_TEMPERATURE` (padrão: 0)

### Variáveis de LLM Provider

```env
REWRITE_PROVIDER=gemini              # openai, gemini, ollama
REWRITE_MODEL=gemini-2.5-flash-lite
ANSWER_PROVIDER=gemini
ANSWER_MODEL=gemini-2.5-flash-lite
```

### Variáveis de Ollama Local

```env
SLM_PROVIDER=ollama
SLM_BASE_URL=http://ollama:11434     # Docker: ollama:11434 | Local: localhost:11434
SLM_MODEL=mistral:latest             # Alternativas: qwen2.5:7b, neural-chat:latest, phi:latest
```

Todas as variáveis estão documentadas em `.env.example` na raiz do projeto.

## Execução Local (sem Docker)

1. Criar ambiente e instalar dependências:

```bash
cd api
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
```

2. Copiar `.env.example` (raiz) para `.env` e preencher variáveis obrigatórias.

3. Subir a API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Validar:

- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Execução com Docker Compose

Na raiz do repositório:

```bash
docker compose build --no-cache
docker compose up -d
```

Comportamento:

- Container `api`: sobe e fica disponível em `http://localhost:8000`.
- Container `ingest-worker`: roda ingestão de forma assíncrona (intervalo: 2h).
- Container `ollama`: LLM local em `http://localhost:11434` (opcional, se `SLM_PROVIDER=ollama`).

Para acompanhar ingestão em tempo real:

```bash
docker compose logs -f ingest-worker
```

## Ingestao RAG

Execucao manual (a partir de `api/`):

```bash
python ingestion/ingest_documents.py
```

Execucao manual via compose:

```bash
docker compose run --rm ingest-worker python ingestion/ingest_documents.py
```

Comportamento incremental:

- Novo PDF: adiciona vetores.
- PDF atualizado: remove vetores antigos do arquivo e reindexa.
- PDF removido: remove vetores desse arquivo.
- PDF inalterado: nao reprocessa.

Arquivos de auditoria gerados em `logs/`:

- `ingestion_manifest.json`
- `ingestion_audit_latest.json`
- `ingestion_audit.jsonl`
- `ingestion_YYYYMMDD_HHMMSS.txt`

Flags uteis:

```bash
INGEST_FORCE_RECREATE_INDEX=true python ingestion/ingest_documents.py
INGEST_FORCE_EXTRACT=true python ingestion/ingest_documents.py
```

## Utilitários

### Sanitização de Planilha

```bash
cd api
python -m utils.alergia_medicamentos.sanitizar_alergia_medicamentos \
  --input utils/alergia_medicamentos/alergia_medicamentos.xlsx \
  --output utils/alergia_medicamentos/alergia_medicamentos_sanitizado.xlsx
```

Usa `OPENAI_API_KEY` e `OPENAI_MODEL` (padrão: `gpt-4o`) para processar cada linha. A saída é um `.xlsx` com abas `sanitizadas` e `nao_sanitizadas`.

### Benchmark de Modelos Ollama

```bash
docker compose exec api python utils/slm/benchmark_ollama_models.py
```

Testa latência e qualidade de modelos locais (Mistral, Qwen, etc.) configurados em `.env` via `BENCHMARK_MODELS`.

Saída: `api/ragas_evaluation/data/output/ollama_benchmark_YYYYMMDD_HHMMSS.json`

## Testes

```bash
cd api
pytest
```

## Troubleshooting rapido

1. `Database unavailable`:
	valide `DATABASE_URL` e conectividade com PostgreSQL.
2. `Google authentication is not configured`:
	configure `GOOGLE_CLIENT_ID`.
3. Erro de indexacao RAG:
	confira chaves OpenAI/Pinecone e logs em `logs/`.
