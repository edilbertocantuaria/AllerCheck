# api/results

Cópias dos arquivos finais usados nos resultados do TCC. Os originais continuam em `api/tools/data/processed/` (nada foi movido ou apagado). Cada cópia foi conferida com SHA-256 contra o original.

| Pasta | Conteúdo | Origem |
|---|---|---|
| `sample/` | Amostra de 262 perguntas (seed 42) e a seleção por etapa (`selected_{A,B,C,D}_*.json`) | `evaluation/` e `evaluation/unified/` |
| `collection/` | `coleta_262.jsonl` (original) e `coleta_262.json` (o mesmo conteúdo como array JSON): respostas, contextos recuperados e expansão por ontologia de cada pergunta | `evaluation/unified/` |
| `ragas/` | Escores brutos do RAGAS das etapas A, B e C (`ragas_{A,B,C}_262.jsonl`) | `evaluation/unified/` |
| `evaluation/` | Avaliação unificada por etapa (`evaluation_{A,B,C,D}_*.json`) | `evaluation/unified/` |
| `llm_judge/` | Votos dos juízes por etapa (A: `..._191141`, B: `..._221023`, C: `..._103408`, D: `..._224811`) | `llm_judge/` |
| `CALIBRAÇÃO/` | Rodada de calibração de 2026/2 (42 perguntas concluídas, de 50 selecionadas), usada nos limites de empate e na sensibilidade. `sample/`: as 50 selecionadas; `evaluation/`: avaliação com e sem ontologia (`..._213928`) e piso de ruído (`..._baseline_223239`); `llm_judge/`: votos dos juízes (`..._215214` e `..._224944`) | `evaluation/`, `evaluation/unified/` e `llm_judge/` |
| `statistical_analysis/` | Saída de `scripts/analise_estatistica.py` (10.000 reamostragens, semente 42) | `processed/` |

Não incluídos de propósito: arquivos `*.judge_progress.jsonl` (logs de execução), piloto, checkpoints, execuções de teste e o grafo local `ontologia_farma.*` (as etapas finais usam o RxNorm por consulta, e a expansão de cada pergunta está em `collection/coleta_262.jsonl`).

O script `scripts/analise_estatistica.py` ainda lê os originais em `tools/data/processed/llm_judge/`.
