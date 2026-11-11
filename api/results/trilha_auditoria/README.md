# Trilha de auditoria (prestação de contas)

Gerada por `api/scripts/trilha_auditoria.py` a partir das cópias finais em `api/results/`
(`collection/`, `evaluation/`, `llm_judge/`). Para regenerar: `cd api && python scripts/trilha_auditoria.py`.
Os totais por etapa são conferidos em `conferencia_totais.json` e coincidem com o capítulo de resultados.

## Arquivos
- `etapa_A.json` ... `etapa_D.json`: um registro por pergunta dentro do escopo (229 por etapa).
- `indice_decisoes.csv`: uma linha por pergunta e etapa (abre no Excel), com a resposta escolhida.
- `conferencia_totais.json`: contagens recomputadas da escolha por etapa.

## Atenção: os rótulos dos arquivos de avaliação e de juízes
Os arquivos originais chamam os dois lados de `com_ontologia` e `sem_ontologia` em TODAS as etapas.
Nesta trilha cada rótulo já está traduzido para a geração real (campo `slot_no_arquivo` guarda o original):

| Etapa | slot `com_ontologia` | slot `sem_ontologia` | slot `ground_truth` |
|---|---|---|---|
| A | `com_g1` (com ontologia) | `sem_g1` (sem ontologia) | referência MedPT |
| B | `sem_g2` (2ª geração) | `sem_g1` (1ª geração) | referência MedPT |
| C | `com_g1` (com ontologia) | `h5_g1` (sem ontologia, top-k ampliado) | referência MedPT |
| D | `sem_gemini` | `sem_g1` (GPT) | `sem_claude` (NÃO é a referência) |

`h5` é o nome interno da condição *sem ontologia, top-k ampliado*.

## Estrutura de cada registro
`pergunta`, `resposta_referencia_medpt`, `reescrita_da_pergunta`, `hyde`, `termos_da_ontologia`;
`candidatos`: por geração, `resposta`, `modelo`, `condicao_de_contexto`, `n_fragmentos`,
`fragmentos_de_ontologia`, `fragmentos` (posição, origem da busca, fonte, similaridade, nota do reranker, texto)
e `ragas` (5 métricas × 3 avaliadores; ausente nas etapas D e para a referência);
`julgamento`: votos de cada juiz nas duas ordens (letra, geração escolhida, confiança, justificativa),
`consenso_estrito`, `forca_do_consenso`, `contagem_sem_descarte`, `escolha_sem_descarte`;
`resposta_escolhida`: `consenso_estrito` e `contagem_sem_descarte` (`null` = sem consenso/empate);
`vencedor_ragas`: vencedor pelo RAGAS (legado).

## Etapa D
Os três candidatos (GPT, Gemini, Claude) respondem sobre o MESMO contexto (condição sem ontologia),
por isso os fragmentos se repetem nos três. Sem RAGAS e sem referência MedPT nessa etapa.

## Não incluídos (por tamanho)
O prompt completo enviado a cada juiz e a resposta bruta. Estão em `llm_judge/` (hash do prompt em `meta.prompt_sha256`).
