# Pipeline de Avaliação Epistemológica: RAGAS + LLM-as-Judge

## Objetivo
Comparar duas epistemologias de conhecimento:
- **COM ontologia**: RAG com RxNorm + mapping de medicamentos
- **SEM ontologia**: RAG com busca tradicional

Via duas ferramentas independentes:
1. **RAGAS**: 5 métricas automáticas (context_recall, faithfulness, etc)
2. **LLM-as-Judge**: 3 juízes LLM votam qual resposta é melhor clinicamente

## Arquitetura

```
Dataset: filtred_alergia_medicamentos.xlsx (821 questões)
    ↓
Pipeline seleciona N questões com seed fixo (reproducível)
    ↓
┌─────────────────────────────────────────┐
│ RAGAS (avaliação automática)            │
│ - Context Recall (aderência ao contexto)│
│ - Context Precision (precisão)          │
│ - Faithfulness (fidelidade)             │
│ - Answer Relevancy (relevância)         │
│ - Context Entity Recall (entidades)     │
└─────────────────────────────────────────┘
    ↓
Respostas COM/SEM ontologia + Ground Truth
    ↓
┌─────────────────────────────────────────┐
│ LLM-as-Judge (avaliação humana simulada)│
│ - GPT-4o-mini                           │
│ - Gemini 2.5 Flash Lite                 │
│ - Claude Haiku 4.5                      │
│ Cada juiz vota: A/B/C + confiança       │
└─────────────────────────────────────────┘
    ↓
Consolidação: mapeamento de divergências
    ↓
pipeline_consolidated_YYYYMMDD_HHMMSS.json
```

## Como Usar

### Opção A: Pipeline Completo (Com RAGAS local)
```bash
python run_pipeline.py --num-questions=3 --seed=42
```

**Requisitos:**
- FastAPI rodando: `docker compose up api`
- Dependências Python: RAGAS com suporte VertexAI

**Problemas conhecidos:**
- Conflitos de dependência RAGAS (langchain-community)
- Solução: usar containerizado

### Opção B: Pipeline Rápido (Reusa evaluation.json)
```bash
python run_pipeline_fast.py --num-questions=15 --seed=42
```

**Requisitos:**
- `api/tools/data/processed/evaluation/unified/evaluation_*.json` existente
- FastAPI rodando: `docker compose up api`

**Vantagens:**
- ✅ Sem problemas de dependência local
- ✅ Reutiliza RAGAS já executado (container ou manual)
- ✅ Foco em sincronização LLM + RAGAS
- ✅ Mais rápido (~15 min para 262 questões)

## Saída: Relatório Consolidado

Arquivo: `api/tools/data/processed/pipeline/pipeline_consolidated_YYYYMMDD_HHMMSS.json`

### Estrutura
```json
{
  "timestamp": "2026-10-05T23:58:47-03:00",
  "pipeline": "RAGAS + LLM-as-Judge Consolidado",
  "num_questions": 3,
  "questions": [
    {
      "question_id": 4,
      "question": "Tenho alergia a dipirona, posso a vacina do covid?",
      "responses": {
        "ground_truth": "...",
        "com_ontologia": "...",
        "sem_ontologia": "..."
      },
      "ragas": {
        "results": {
          "gemini": {
            "context_recall": 1.0,
            "context_precision": 0.95,
            "faithfulness": 0.9,
            "answer_relevancy": 0.88,
            "context_entity_recall": 0.85
          }
        }
      },
      "llm_judge": {
        "votes": [
          {
            "judge": "gpt-4o-mini",
            "choice": "C",
            "choice_source": "sem_ontologia",
            "confidence": 0.90,
            "reasoning": "..."
          },
          ...
        ],
        "consensus": "com_ontologia",
        "mapping": {"A": "com_ontologia", "B": "sem_ontologia", "C": "ground_truth"}
      },
      "analysis": {
        "judges_consensus": "com_ontologia",
        "agreement": true  // consenso juízes == melhor RAGAS
      }
    }
  ],
  "summary": {
    "total_questions": 3,
    "agreements": 2,
    "divergences": 1,
    "agreement_rate": 0.6667,
    "consensus_scores": {
      "com_ontologia": 2,
      "sem_ontologia": 0,
      "ground_truth": 1
    },
    "judges": ["gpt-4o-mini", "gemini", "claude"]
  }
}
```

## Métricas para Análise

### RAGAS (5 métricas automáticas)
- **context_recall**: % do ground truth recuperado no contexto
- **context_precision**: % do contexto que é relevante
- **faithfulness**: consistência entre resposta e contexto
- **answer_relevancy**: qual resposta melhor responde pergunta
- **context_entity_recall**: entidades clínicas identificadas

### LLM-as-Judge (votos qualitativos)
- **Consenso**: qual resposta 2+ juízes preferem
- **Confiança**: 0.0-1.0 (certeza do juiz)
- **Mapping**: qual resposta (A/B/C) é qual condição (COM/SEM)

### Análise Epistemológica
- **Taxa de concordância**: % de questões onde RAGAS + Juízes concordam
- **Divergências**: onde máquina e humanos discordam
- **Preferência ontológica**: juízes preferem COM ou SEM ontologia?

## Escalabilidade: Caminhos para 262 Questões

### Path 1: Local (rápido, sem container)
```bash
python run_pipeline_fast.py --num-questions=262 --seed=42
# ~30-40 min (3 juízes × 262 questões × 1 chamada API/juiz)
```

### Path 2: Container (integrado, mais robusto)
```bash
docker compose up -d api
python run_pipeline.py --num-questions=262 --seed=42
# ~60-90 min (inclui coleta RAGAS dentro container)
```

## Troubleshooting

### Erro: `ModuleNotFoundError: langchain_community.chat_models.vertexai`
**Solução:** Use pipeline_fast.py em vez de pipeline_complete.py

### Erro: `UnicodeEncodeError` (Windows)
**Solução:** Já corrigido - scripts forçam UTF-8 stdout

### Erro: `evaluation_*.json não encontrado`
**Solução:** Rode RAGAS primeiro:
```bash
# No container
docker exec allercheck-api python api/evaluate_with_ontology_robust.py \
  tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx 262 42
```

## Próximos Passos

1. ✅ Testar com 3 questões (prova de conceito)
2. ⏳ Testar com 15 questões (validar escalabilidade)
3. 🎯 Rodar com 262 questões (full evaluation)
4. 📊 Análise de divergências e padrões clínicos
5. 📝 Relatório epistemológico para professor

## Documentação de Código

- `api/pipeline_complete.py` — Orquestrador completo
- `api/pipeline_fast.py` — Orquestrador rápido (reusa RAGAS)
- `api/ragas_with_selected_questions.py` — Wrapper RAGAS
- `llm_as_judge_test_local.py` — Avaliador LLM local
- `run_pipeline.py` — CLI entrada completa
- `run_pipeline_fast.py` — CLI entrada rápida
