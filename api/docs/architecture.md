# Arquitetura da API

Este documento descreve a organizacao do backend em um padrao de manutencao mais limpo e escalavel.

## Camadas

1. `routers/`
- Responsavel apenas por HTTP (entrada, status code, serializacao e dependencias).

2. `services/`
- Regras de negocio organizadas em CQRS leve por dominio.
- `services/auth/commands.py`: fluxos de escrita/autenticacao com efeito colateral.
- `services/auth/queries.py`: fluxos de leitura/consulta sem mutacao.
- `services/conversations/commands.py`: criacao/remocao de conversa.
- `services/conversations/queries.py`: listagens e leitura de mensagens.
- `services/chat/queries.py`: preparacao de contexto da consulta e validacoes.
- `services/chat/commands.py`: execucao do streaming e persistencia da resposta.
- `rag_service.py`: ciclo completo de RAG (retrieval, reescrita, montagem de contexto e prompts).
- `chat_response_service.py`: regras de exibicao de fontes na resposta.
- `conversation_service.py`: funcoes de dominio/repository adapter reutilizadas pelos casos de uso.

3. `prompts/`
- Pasta exclusiva para prompts versionaveis.
- `templates/*.md`: textos de prompt em arquivos separados.
- `registry.py`: ponto unico para carregar prompts com cache.

4. `core/`
- Configuracao centralizada e cacheada da aplicacao.
- `settings.py`: leitura de variaveis de ambiente (arquivo `.env`).

5. `config.py`
- Camada de compatibilidade que expoe constantes legadas e cliente Pinecone lazy.

6. `db/`
- Pacote dedicado para componentes de persistencia.
- Reexporta `Base`, `engine`, `SessionLocal`, `get_db` e `init_db` durante a transicao.

## Principios aplicados

- Separacao de responsabilidades: HTTP fora da regra de negocio.
- Separacao command/query: escrita e leitura em modulos distintos por dominio.
- Menor acoplamento: prompts e RAG desacoplados de routers.
- Configuracao central: menos estado global espalhado.
- Evolucao incremental: refatoracao sem quebra de contratos de API.

## Convencoes para evolucoes futuras

1. Novo prompt: adicionar arquivo em `prompts/templates` e registrar no `PromptKey`.
2. Nova regra de chat: implementar em `services/`, nao em `routers/chat.py`.
3. Novas configuracoes: adicionar em `AppSettings` e mapear em `config.py`.
4. Integracoes externas: inicializacao lazy para evitar falha global em import.
5. Casos de uso novos: decidir explicitamente entre `commands.py` ou `queries.py`.
