# Guia de Adaptação do Projeto

Este documento lista tudo que precisa ser alterado para adaptar o projeto a um novo domínio ou nome.  
**Exemplo usado neste guia:** renomear de `AllerCheck` (saúde/farmacovigilância) para `jurisprudêncIA` (jurídico).

Slug técnico usado nos exemplos: `jurisprudencia-ia` (sem acento, sem maiúsculas — usado em banco, Pinecone, localStorage etc.).

---

## 1. Infraestrutura e banco de dados

### `docker-compose.yml`
```yaml
# Linha ~7 — nome do banco PostgreSQL
POSTGRES_DB: allercheck   →   jurisprudencia-ia
```

### `.env` (raiz do projeto)
```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/allercheck
→
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/jurisprudencia-ia
```

### `.env.example` (raiz)
Mesma substituição acima (é o template público).

### `api/app/core/settings.py`
Linha com o default hardcoded da `DATABASE_URL`:
```python
"postgresql+psycopg2://postgres:postgres@db:5432/allercheck"
→
"postgresql+psycopg2://postgres:postgres@db:5432/jurisprudencia-ia"
```

### `servers.json` (config do pgAdmin)
```json
"MaintenanceDB": "allercheck"   →   "jurisprudencia-ia"
```

---

## 2. Índice Pinecone

### `api/.env` ⚠️ não vai pro git
```env
INDEX_NAME=allercheck   →   jurisprudencia-ia
```

> O índice também precisa ser criado manualmente no painel do Pinecone com o novo nome e as mesmas dimensões (3072) e métrica (cosine).

---

## 3. Nome do projeto na API

### `api/app/main.py`
```python
title="AllerCheck API"   →   title="jurisprudêncIA API"
```

---

## 4. Logo e ícone

Esta é a alteração mais visual — a logo aparece em 4 lugares distintos da interface.

### Arquivo de imagem
```
web/public/logo.png   →   substituir pelo arquivo de imagem do novo projeto
```
O arquivo deve continuar se chamando `logo.png` (ou atualizar todas as referências abaixo).

### Referências no código

| Arquivo | Uso | O que alterar |
|---------|-----|---------------|
| `web/src/app/layout.tsx` (linhas 17, 21, 25, 29) | Favicon (aba do browser, Apple icon) | `url: "/logo.png"` → manter o nome ou renomear consistentemente |
| `web/src/app/login/page.tsx` (linha 43) | Logo na tela de login | `alt="AllerCheck"` → `alt="jurisprudêncIA"` |
| `web/src/app/register/page.tsx` (linha 56) | Logo na tela de cadastro | `alt="AllerCheck"` → `alt="jurisprudêncIA"` |
| `web/src/components/chat-interface/chat-interface-content.tsx` (linha 19) | Logo na tela inicial do chat (quando não há mensagens) | `alt="AllerCheck"` → `alt="jurisprudêncIA"` |

> A logo aparece como favicon na aba do browser, na tela de login, no cadastro e na tela inicial do chat. Substituir apenas o arquivo `web/public/logo.png` já atualiza a imagem em todos os lugares — mas os atributos `alt` precisam ser trocados manualmente nos 3 arquivos acima.

---

## 5. Interface web — textos e títulos

### `web/src/app/layout.tsx`
```tsx
title: "AllerCheck"   →   title: "jurisprudêncIA"
description: "Interface de chat para RAG com base em questionario publico sobre alergia a medicamentos"
→  descrição do novo domínio
```

### `web/src/app/login/page.tsx`
```tsx
<h1>AllerCheck</h1>   →   <h1>jurisprudêncIA</h1>
```

### `web/src/app/register/page.tsx`
```tsx
"Crie sua conta para acessar o AllerCheck"   →   "Crie sua conta para acessar o jurisprudêncIA"
```

### `web/src/components/chat-interface/chat-interface-header.tsx`
```tsx
<h1>AllerCheck</h1>   →   <h1>jurisprudêncIA</h1>
```

### `web/src/components/chat-interface/chat-interface-content.tsx`
```tsx
placeholder: "Faça uma pergunta sobre alergia a medicamentos"
→  "Faça uma pergunta sobre jurisprudência ou legislação"  (ou o tema do novo domínio)
```

### `web/package.json`
```json
"name": "allercheck"   →   "jurisprudencia-ia-web"
```

---

## 6. Chaves do localStorage (autenticação)

### `web/src/contexts/auth-context.tsx`
```ts
const TOKEN_KEY = "allercheck_access_token";   →   "jurisprudencia_ia_access_token"
const USER_KEY  = "allercheck_user";           →   "jurisprudencia_ia_user"
```

> Se não alterar, usuários com sessão aberta no navegador podem ter conflito caso o antigo e o novo projeto rodem no mesmo domínio.

---

## 7. Prompts do LLM

Estes arquivos definem a persona e o contexto do assistente. São a parte mais importante para a qualidade das respostas no novo domínio.

| Arquivo | O que alterar |
|---------|--------------|
| `api/app/prompts/templates/question_init.md` | Persona ("Especialista em Alergia e Imunologia Clínica, com foco em Farmacovigilância" → persona jurídica, ex: "Especialista em Direito, com foco em Jurisprudência") e regras de resposta específicas do domínio |
| `api/app/prompts/templates/question_rewrite.md` | Referência a "base de dados de farmacovigilância" e termos como "fármaco", "princípio ativo", "medicamento" → termos jurídicos como "processo", "acórdão", "legislação" |
| `api/app/prompts/templates/question_title.md` | Geração de título ainda menciona contexto medicamentoso → adaptar para jurídico |
| `api/app/prompts/templates/classify_risk.md` | Critérios de urgência com contexto clínico (VERMELHO/AMARELO/VERDE) → critérios do novo domínio |

---

## 8. Serviços de negócio (lógica RAG)

### `api/app/services/rag_service.py`
- `_HYDE_PROMPT`: substitua "redator de documentos técnicos de farmacovigilância" e "de farmacovigilância sobre o tema da query" pela descrição do novo domínio.

### `api/app/services/chat_response_service.py`
- Texto "registros de farmacovigilância consultados" → descrição dos documentos do novo domínio (ex: "documentos jurídicos consultados").

---

## 9. Documentos ingeridos (base de conhecimento)

### O essencial — qualquer pessoa consegue fazer

Apague os PDFs e o MDs do domínio antigo e coloque os documentos do novo domínio no mesmo lugar:

```
# Remover
api/docs/pdf_files/5k analises sobre alergias medicamentosas.pdf
api/docs/pdf_files/asbai-sinteses.pdf
api/docs/asbai-sinteses.md

# Adicionar
api/docs/pdf_files/<seus-documentos>.pdf   (quantos quiser)
```

O pipeline de ingestão já varre automaticamente tudo que estiver em `api/docs/pdf_files/`. Depois de colocar os arquivos, basta rodar:

```bash
docker compose run --rm ingest-worker
```

### Para perfis mais técnicos — utilitários opcionais

Os diretórios `api/utils/VigiMed/`, `api/utils/ASBAI` e `api/utils/alergia_medicamentos/` são scripts auxiliares usados para baixar, limpar e exportar dados da fonte original (VigiMed/ANVISA) antes de virar PDF. **Para um novo domínio, podem simplesmente ser apagados.**

Se quiser aproveitar a estrutura para a nova fonte de dados (ex: baixar acórdãos de uma API do Tribunal, sanitizar planilhas jurídicas), esses scripts servem de referência — mas reescrever do zero para o novo formato costuma ser mais simples do que adaptar.

O arquivo `filtred_alergia_medicamentos.xlsx` em `api/ragas_evaluation/data/input/` também pode ser removido; ele é usado apenas para rodar a avaliação RAGAS com perguntas do domínio antigo. Ao montar um dataset de avaliação para o novo domínio, coloque o novo `.xlsx` no mesmo diretório.

---

## 10. Testes automatizados

### `api/tests/test_chat.py`
Perguntas de exemplo usam contexto de alergia a medicamentos → substituir por perguntas do novo domínio.

### `api/tests/test_rag_service_unit.py`
```python
"Tenho alergia à penicilina"   →   pergunta do novo domínio (ex: "Qual o prazo prescricional para ação trabalhista?")
```

---

## 11. Documentação e metadados do repositório

| Arquivo | O que alterar |
|---------|--------------|
| `README.md` | Título, descrição e exemplos de uso |

---

## Checklist de adaptação

```
[ ] web/public/logo.png            — substituir arquivo de imagem
[ ] docker-compose.yml             — POSTGRES_DB
[ ] .env (raiz)                    — DATABASE_URL
[ ] .env.example                   — DATABASE_URL
[ ] api/app/core/settings.py       — DATABASE_URL default
[ ] servers.json                   — MaintenanceDB
[ ] api/.env                       — INDEX_NAME
[ ] Pinecone (painel web)          — criar novo índice com mesmo dim/métrica
[ ] api/app/main.py                — title da API
[ ] web/src/app/layout.tsx         — title + description + alt dos ícones
[ ] web/src/app/login/page.tsx     — alt da logo + título h1
[ ] web/src/app/register/page.tsx  — alt da logo + texto de boas-vindas
[ ] chat-interface-header.tsx      — título h1
[ ] chat-interface-content.tsx     — alt da logo + placeholder
[ ] web/package.json               — name
[ ] auth-context.tsx               — TOKEN_KEY + USER_KEY
[ ] prompts/templates/*.md         — persona e contexto do domínio
[ ] rag_service.py                 — HYDE_PROMPT
[ ] chat_response_service.py       — descrição dos registros
[ ] api/docs/pdf_files/            — apagar PDFs antigos, adicionar os do novo domínio
[ ] api/docs/asbai-sinteses.md    — apagar
[ ] api/utils/VigiMed/            — apagar (opcional: guardar como referência técnica)
[ ] api/utils/alergia_medicamentos/ — apagar (idem)
[ ] api/tests/                     — atualizar perguntas de exemplo
[ ] README.md                      — atualizar documentação
[ ] Rodar pipeline de ingestão     — reindexar Pinecone
```
