# 🛠️ Tools — Pipelines Reprodutíveis

Pipelines de processamento de dados e avaliação completamente documentados e reprodutíveis.

## 📁 Estrutura

```
tools/
├── data/                 # Data Lake com versionamento
│   ├── raw/             # Dados brutos (VERSIONADOS no git)
│   └── processed/       # Resultados com TIMESTAMP (NO git)
│
├── pipelines/           # Scripts de transformação de dados
│   ├── asbai/           # Extração + Sínteses ASBAI
│   ├── vigimed/         # ETL VigiMed
│   ├── allergia_meds/   # Sanitização de medicamentos
│   └── common/          # Utilitários compartilhados
│
├── evaluation/          # RAGAS + Benchmarks
│   ├── ragas/
│   │   ├── core/        # Lógica de avaliação
│   │   ├── cli/         # Interface CLI
│   │   └── scripts/     # Pós-processamento
│   └── benchmarks/      # Testes de desempenho
│
├── config/              # Configuração centralizada
└── scripts/             # Ad-hoc utilities
```

---

## ⚠️ VARIÁVEIS DE AMBIENTE CRÍTICAS

**ANTES de rodar qualquer coisa:**

1. Copie `.env.example` para `.env` na **raiz do projeto** (acima de `api/`):
   ```bash
   cd AllerCheck/                      # ← RAIZ
   cp .env.example .env               # ← AQUI, não em api/
   ```

2. Preencha os valores em `AllerCheck/.env` (NÃO em `api/.env`):
   ```bash
   # API Keys (OBRIGATÓRIOS)
   OPENAI_API_KEY=sk-...
   PINECONE_API_KEY=pcsk_...
   
   # Temperaturas (OBRIGATÓRIAS — sem fallback!)
   REWRITE_TEMPERATURE=0.1
   ANSWER_TEMPERATURE=0.2
   EVALUATOR_TEMPERATURE=0.0
   
   # LLM Configuration
   REWRITE_PROVIDER=openai
   ANSWER_PROVIDER=openai
   SLM_PROVIDER=ollama
   SLM_BASE_URL=http://ollama:11434
   ```

3. **NUNCA commite `.env`** — está no `.gitignore`

---

## 🚀 Como Reproduzir do Zero

### **Passo 1: Setup Inicial**

```bash
cd api/tools

# Criar estrutura de dados (já feito, mas validar)
python scripts/verify_inputs.py

# Instalar dependências (se necessário)
pip install -r pipelines/common/requirements.txt
```

### **Passo 2: Rodar Pipelines (em ordem)**

#### **2.1 ASBAI — Extração de PDF**

```bash
python -m pipelines.asbai.run
```

**O que faz:**
- Lê `data/raw/asbai/ALERGIA-PERGUNTAS-E-RESPOSTAS.pdf`
- Extrai texto completo
- Envia para GPT-4o para sínteses
- Salva em `data/processed/asbai/20260628_123456_asbai_sinteses.md`

**Input:** `data/raw/asbai/*.pdf`  
**Output:** `data/processed/asbai/*.md` (com TIMESTAMP)

---

#### **2.2 VigiMed — ETL de Dados**

```bash
python -m pipelines.vigimed.run
```

**O que faz:**
- Lê CSVs brutos: `Reacoes.csv`, `Medicamentos.csv`, `Notificacoes.csv`
- Limpa e valida dados
- Enriquece com mapeamentos
- Salva em `data/processed/vigimed/20260628_123456_base_rag_alergia.csv`

**Input:** `data/raw/vigimed/*.csv`  
**Output:** `data/processed/vigimed/*.csv` (com TIMESTAMP)

---

#### **2.3 Allergia Meds — Sanitização**

```bash
python -m pipelines.allergia_meds.run
```

**O que faz:**
- Lê XLSX de medicamentos com alergia
- Remove linhas inválidas
- Valida estrutura
- Salva em `data/processed/allergia_meds/20260628_123456_alergia_medicamentos.xlsx`

**Input:** `data/raw/allergia_meds/*.xlsx`  
**Output:** `data/processed/allergia_meds/*.xlsx` (com TIMESTAMP)

---

### **Passo 3: Avaliação RAGAS**

```bash
# Rodar avaliação completa
python -m evaluation.ragas.cli.main evaluate \
  --dataset data/raw/evaluation/dataset.xlsx \
  --samples 262

# Filtrar resultados (remove campos desnecessários)
python -m evaluation.ragas.scripts.filter_results \
  --input data/processed/evaluation/ragas_full.json \
  --output data/processed/evaluation/ragas_clean.json

# Análise e estatísticas
python -m evaluation.ragas.scripts.analyze_results \
  data/processed/evaluation/ragas_clean.json
```

**Outputs:**
- `data/processed/evaluation/20260628_123456_ragas_results.json`
- `data/processed/evaluation/20260628_123456_ragas_analysis.json`

---

### **Passo 4: Benchmarks Ollama**

```bash
# Testar modelos locais
python -m evaluation.benchmarks.ollama.run \
  --models "mistral,llama2,neural-chat" \
  --timeout 240 \
  --samples 20
```

**Outputs:**
- `evaluation/benchmarks/results/20260628_123456_benchmark.json`

---

## 📊 Versionamento de Dados

Todos os outputs têm **TIMESTAMP no nome do arquivo**:

```
20260628_012345_base_rag_alergia.csv
│         │
│         └─ HH:MM:SS
└─ YYYYMMDD (20260628 = 28 jun 2026)
```

**Benefícios:**
- ✅ Fácil rastrear quando foi gerado
- ✅ Múltiplas runs sem sobrescrever
- ✅ Histórico completo de processamentos

**Limpar dados antigos:**
```bash
# Listar todos os processamentos
ls -lh data/processed/**/*.csv

# Remover resultados de mais de 7 dias
find data/processed -name "*.csv" -mtime +7 -delete
```

---

## 🐳 Docker Compose

Tudo funciona dentro de Docker:

```bash
# Na raiz do projeto
docker compose up -d --build

# Rodar pipeline dentro do container
docker compose exec api python -m tools.pipelines.vigimed.run

# Ver logs
docker compose logs -f api
```

**IMPORTANTE:** Variáveis de ambiente vêm do `.env`:
```yaml
# docker-compose.yml
services:
  api:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - REWRITE_TEMPERATURE=${REWRITE_TEMPERATURE}
      # ... etc
```

---

## 🧪 Testes de Sanidade

### **Verificar que tudo está configurado:**
```bash
python scripts/verify_inputs.py
```

Checa:
- ✅ Arquivo `.env` existe
- ✅ Variáveis obrigatórias definidas
- ✅ Arquivos de entrada existem
- ✅ Diretórios de saída criáveis

### **Testar conectividade de APIs:**
```bash
python scripts/test_api_keys.py
```

Testa:
- ✅ OpenAI API
- ✅ Gemini API
- ✅ Anthropic API
- ✅ Pinecone

---

## ❌ Troubleshooting

| Problema | Solução |
|----------|---------|
| `ImportError: No module 'tools'` | Rode do diretório `api/` (onde `tools/` está) |
| `KeyError: REWRITE_TEMPERATURE` | Preencha `.env` — variável obrigatória! |
| `FileNotFoundError: data/raw/vigimed/...` | Copie arquivos para `data/raw/` |
| `ConnectionError: Pinecone` | Verifique PINECONE_API_KEY e conexão de rede |
| Dados não aparecem em `data/processed/` | Check logs com timestamp: `ls -lh data/processed/` |

---

## 📚 Pipelines Adicionais

Quer criar um novo pipeline? Copie a estrutura:

```bash
mkdir -p pipelines/seu_pipeline
cp -r pipelines/asbai/*.py pipelines/seu_pipeline/
```

Estructura básica:
```python
# pipelines/seu_pipeline/run.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipelines.common import setup_logger, save_with_timestamp

def main():
    logger = setup_logger("seu_pipeline")
    logger.info("Iniciando seu pipeline...")
    
    # Seu código aqui
    
    # Salvar resultado com timestamp
    save_with_timestamp(data, Path("data/processed/seu_pipeline"), "resultado")

if __name__ == "__main__":
    main()
```

---

## 🎯 Próximas Etapas

- [ ] Documentar entrada/saída de cada pipeline em seus READMEs
- [ ] Adicionar validação de schemas para CSVs/JSONs
- [ ] Criar CI/CD que roda pipelines em schedule
- [ ] Implementar notificações quando pipeline falha
- [ ] Adicionar suporte a versionamento de modelos RAGAS

---

**Mantido com 💙 para reproducibilidade!**
