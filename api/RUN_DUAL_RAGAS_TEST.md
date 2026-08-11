# 🚀 Executar Teste Dual RAGAS (3 amostras)

## Comando Único

```bash
cd C:\Users\edilb\OneDrive\Documentos\AllerCheck\api
conda activate LangChain
python run_dual_ragas.py
```

## O Que Acontece

```
┌────────────────────────────────────────────┐
│  RUN_DUAL_RAGAS.PY (Script Unificado)     │
└────────────────────────────────────────────┘
           │
           ├─ 🔄 PARALELO 1: COM ONTOLOGIA
           │  ├─ Coleta: OpenAI (gpt-4o-mini) via /chat
           │  ├─ Retrieval: Pinecone + ontologia_farma.json
           │  └─ Avaliação: Gemini (5 métricas)
           │
           └─ 🔄 PARALELO 2: SEM ONTOLOGIA
              ├─ Coleta: OpenAI (gpt-4o-mini) via /chat
              ├─ Retrieval: Pinecone (sem expansão)
              └─ Avaliação: Gemini (5 métricas)

           ⏱️  Tempo: ~30-45 min (3 amostras)
```

## Depois: Comparar Resultados

```bash
python compare_dual_ragas.py
```

Gera tabela de deltas (COM vs SEM ontologia):

```
📈 Avaliador: GEMINI
────────────────────────────────────────────
Métrica                  | Arquivo 1 | Arquivo 2 | Delta    | Δ%
────────────────────────────────────────────
faithfulness             |     0.600 |     0.650 | +0.050   | +8.3% ⬆️
answer_relevancy         |     0.700 |     0.720 | +0.020   | +2.9% ⬆️
context_precision        |     0.800 |     0.800 | +0.000   | +0.0% ➡️
context_recall           |     0.400 |     0.450 | +0.050   | +12.5% ⬆️
context_entity_recall    |     0.350 |     0.380 | +0.030   | +8.6% ⬆️
────────────────────────────────────────────
```

## Arquivos de Saída

| Arquivo | Descrição |
|---------|-----------|
| `ragas_evaluation_YYYYMMDD_HHMMSS.json` | COM ontologia (Gemini) |
| `ragas_evaluation_latest.json` | SEM ontologia (Gemini) |
| `comparacao_ragas.json` | Comparação estruturada |

---

## 📊 Se Correr Bem (com 3 amostras):

Depois escala para 30 amostras:

```python
# Em run_dual_ragas.py, mude:
"--max-samples", "30",  # Era "3", agora "30"
```

E roda novamente — desta vez vai levar ~2-3 horas mas completará tudo automaticamente!

---

**Tá pronto? É só rodar! 🚀**
