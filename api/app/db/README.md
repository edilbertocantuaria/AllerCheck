# DB Package

Ponto de entrada para artefatos de persistencia da aplicacao.

No estado atual, este pacote reexporta os componentes legados de `app.database` para manter compatibilidade.

## Conteudo atual

- `Base`
- `engine`
- `SessionLocal`
- `get_db`
- `init_db`

## Evolucao sugerida

- mover gradualmente `app/database.py` para este pacote;
- separar configuracao de engine/session de migracoes;
- manter imports publicos estaveis durante a transicao.
