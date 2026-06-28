# Instrucoes de Ingestao (RAG)

Este guia descreve como a ingestao esta configurada, como monitorar execucoes e como operar sem indisponibilizar a API.

## Objetivo

- Manter a API disponivel enquanto a base vetorial e atualizada.
- Processar automaticamente mudancas em PDFs (novos, atualizados, removidos, inalterados).
- Gerar trilha de auditoria completa de cada execucao.

## Arquitetura Atual

A ingestao roda em um servico dedicado no Docker Compose:

- Servico: `ingest-worker`
- Comportamento: loop infinito
- Frequencia padrao: a cada 2 horas (7200 segundos)
- API: permanece disponivel durante toda a ingestao

## Como subir o ambiente

No root do projeto:

```bash
docker compose up -d --build
```

Esse comando sobe:

- db
- pgadmin
- api
- web
- ingest-worker

## Frequencia da ingestao automatica

Padrao:

- `INGEST_INTERVAL_SECONDS=7200`

Exemplo para alterar para 1 hora:

```bash
INGEST_INTERVAL_SECONDS=3600 docker compose up -d --build
```

## Executar ingestao manual sem esperar 2h

Para disparar imediatamente uma ingestao adicional:

```bash
docker compose run --rm ingest-worker python ingestion/ingest_documents.py
```

Observacoes:

- O container dessa execucao manual e removido ao finalizar (flag `--rm`).
- Evite executar manualmente ao mesmo tempo que o ciclo automatico esta rodando.

Fluxo seguro para evitar concorrencia:

```bash
docker compose stop ingest-worker
docker compose run --rm ingest-worker python ingestion/ingest_documents.py
docker compose up -d ingest-worker
```

## Monitorar progresso em tempo real

Ver logs do worker:

```bash
docker compose logs -f ingest-worker
```

A ingestao imprime progresso por etapas no formato `[n/11]` e detalhes por item nas fases principais.

## Comportamento incremental

A ingestao processa somente o delta:

- Novo documento: adiciona vetores.
- Documento atualizado: remove vetores antigos desse arquivo e reindexa.
- Documento removido: remove vetores correspondentes.
- Documento inalterado: não reprocessa.

## Regras de origem documental

- Origem padrao: `api/docs`
- A ingestao processa todos os arquivos `.pdf` dessa pasta (incluindo subpastas).
- Opcionalmente, voce pode definir `INGEST_SOURCE_PATH` apontando para um PDF, uma pasta com PDFs ou um ZIP.

Para forcar reextracao (somente quando `INGEST_SOURCE_PATH` for ZIP):

```bash
INGEST_FORCE_EXTRACT=true python ingestion/ingest_documents.py
```

## Rebuild completo do indice

Por padrao a ingestao e incremental.

Para apagar/recriar o indice e reindexar tudo:

```bash
INGEST_FORCE_RECREATE_INDEX=true python ingestion/ingest_documents.py
```

## Auditoria gerada

A cada execucao sao gerados:

- Manifesto incremental:
  - `api/logs/ingestion_manifest.json`
- Auditoria JSON (historico):
  - `api/logs/ingestion_audit.jsonl`
- Auditoria JSON (ultimo estado):
  - `api/logs/ingestion_audit_latest.json`
- Resumo textual por execucao:
  - `api/logs/ingestion_YYYYMMDD_HHMMSS.txt`

## O que a auditoria mostra

- Contagem de PDFs descobertos e processados.
- Mudancas detectadas: novos, atualizados, removidos, inalterados.
- Arquivos sem texto extraivel.
- Falhas de loader.
- Chunks por arquivo.
- Auditoria do Pinecone:
  - vetores antes/depois
  - delta de vetores
  - namespaces antes/depois
  - operacoes de delete/reindex/upsert

## Troubleshooting rapido

1. Nao vejo progresso:
- Use `docker compose logs -f ingest-worker`.

2. Quero rodar na hora:
- Use `docker compose run --rm ingest-worker python ingestion/ingest_documents.py`.

3. Quero evitar conflito entre auto e manual:
- Pare o worker automatico antes da execucao manual e religue ao final.

4. Mudancas nao refletiram como esperado:
- Verifique `api/logs/ingestion_audit_latest.json` e o arquivo txt mais recente em `api/logs`.
