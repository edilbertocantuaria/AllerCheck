# Ollama — GPU Setup + RAGAS Integration

Documentação completa: configuração de GPU NVIDIA, instalação de modelos, e integração como avaliador RAGAS.

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Pré-requisitos](#pré-requisitos)
3. [Verificar GPU](#verificar-gpu)
4. [Instalar Dependências](#instalar-dependências)
5. [Configuração Docker](#configuração-docker)
6. [Subir Stack](#subir-stack)
7. [Instalar Modelos](#instalar-modelos)
8. [Testar Endpoints](#testar-endpoints)
9. [Integrar em RAGAS](#integrar-em-ragas)
10. [Performance](#performance)
11. [Troubleshooting](#troubleshooting)

---

## Visão Geral

### O que é Ollama?

Ollama é um framework para rodar modelos de linguagem **localmente**:

- ✅ **Grátis** — Sem custos de API
- ✅ **Rápido** — Com GPU NVIDIA (2-3x mais rápido)
- ✅ **Privado** — Dados não saem de você
- ✅ **Offline** — Funciona sem internet

### Integração no AllerCheck

```
┌─────────────────────────────────────────┐
│  GET /evaluate/comparison               │
├─────────────────────────────────────────┤
│  LLM (Gemini)  │  SLM (Ollama)         │
│  Rápido        │  Grátis               │
│  Caro          │  Local                │
│  1.6s          │  0.9s                 │
│  $0.0002       │  $0.0000              │
└─────────────────────────────────────────┘
```

---

## Pré-requisitos

### Mínimo

- Docker Desktop instalado
- 4GB RAM
- 10GB espaço em disco

### Recomendado (com GPU)

- NVIDIA GPU (qualquer GeForce, RTX, Tesla)
- NVIDIA Drivers atualizados
- CUDA Toolkit 11.0+ (opcional)

---

## Verificar GPU

### Windows (PowerShell)

```powershell
nvidia-smi
# ou
& "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
```

### Linux/Mac

```bash
nvidia-smi
```

### Modelos de GPU e Capacidade

| GPU | VRAM | Modelos Recomendados |
|-----|------|----------------------|
| MX450 | 2GB | Mistral 7B, Neural Chat 7B |
| RTX 3050 | 6GB | Mistral, Qwen, Llama 2 7B |
| RTX 3070 | 8GB | Mistral, Llama 2 13B |
| RTX 4090 | 24GB | Qualquer modelo |

---

## Instalar Dependências

### Windows

#### 1. NVIDIA Drivers
1. https://www.nvidia.com/Download/driverDetails.aspx
2. Selecione sua GPU
3. Instale e reinicie

#### 2. Docker Desktop
1. https://www.docker.com/products/docker-desktop
2. Instale com opções padrão
3. Certifique WSL2 está instalado

Verificar:
```powershell
docker --version
docker run hello-world
```

### Linux (Ubuntu)

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y nvidia-driver-535 nvidia-utils
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### Mac

⚠️ Mac não suporta NVIDIA GPU

---

## Configuração Docker

### docker-compose.yml

```yaml
ollama:
  image: ollama/ollama:latest
  container_name: ollama
  ports:
    - "11434:11434"
  environment:
    - OLLAMA_MODELS=/root/.ollama/models
  volumes:
    - ollama_data:/root/.ollama
  restart: unless-stopped
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### .env

```env
SLM_PROVIDER=ollama
SLM_BASE_URL=http://ollama:11434
SLM_MODEL=mistral:latest
```

⚠️ `SLM_BASE_URL=http://ollama:11434` (não localhost!) pois está em Docker

---

## Subir Stack

```bash
cd AllerCheck

# Primeira vez
docker-compose up -d --build

# Verificar status
docker-compose ps

# Ver logs
docker logs ollama -f
```

---

## Instalar Modelos

### Modelos Recomendados

| Modelo | VRAM | Qualidade | Velocidade |
|--------|------|-----------|-----------|
| qwen3.5:9b | 7GB | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| qwen3.5:4b | 3GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| qwen2.5:7b | 6GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| mistral:latest | 5GB | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

### Instalar

```bash
# Mistral
docker exec ollama ollama pull mistral:latest

# Qwen
docker exec ollama ollama pull qwen3.5:4b

# Listar instalados
docker exec ollama ollama ls
```

---

## Testar Endpoints

### Comparação LLM vs SLM

```bash
curl -X POST http://localhost:8000/evaluate/comparison \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Sou alérgico a mounjaro?",
    "use_hyde": true
  }'
```

---

## Integrar em RAGAS

### Passo 1: Adicionar Imports

Em `api/ragas_evaluation/ragas_evaluator.py`, após imports existentes:

```python
from langchain_ollama import ChatOllama
from ragas.llms import LangchainLLMWrapper
```

### Passo 2: Adicionar Parâmetros

```python
def __init__(
    self,
    openai_llm_model: str | None = None,
    openai_embedding_model: str | None = None,
    gemini_model: str | None = None,
    claude_model: str | None = None,
    ollama_model: str | None = None,        # novo
    ollama_base_url: str | None = None,     # novo
    ...
):
```

### Passo 3: Inicializar Ollama

Após inicialização do Claude:

```python
ollama_model = ollama_model or os.getenv("SLM_MODEL", "qwen3.5:4b")
ollama_base_url = ollama_base_url or os.getenv("SLM_BASE_URL", "http://localhost:11434")

_ollama_chat = ChatOllama(
    model=ollama_model,
    base_url=ollama_base_url,
    temperature=0,
    num_predict=4096,
)
_ollama_llm = LangchainLLMWrapper(_ollama_chat)
_ollama_sem = asyncio.Semaphore(1)
```

### Passo 4: Adicionar Métricas

Em `self._metrics`:

```python
"ollama": {
    "faithfulness":          Faithfulness(llm=_ollama_llm),
    "context_precision":     ContextPrecision(llm=_ollama_llm),
    "context_recall":        ContextRecall(llm=_ollama_llm),
    "context_entity_recall": ContextEntityRecall(llm=_ollama_llm),
    "answer_relevancy":      AnswerRelevancy(llm=_ollama_llm, embeddings=_embeddings),
},
```

### Passo 5: Instalar Dependência

```bash
pip install langchain-ollama
```

### Usar

```bash
python -m ragas_evaluation.run_ragas_eval pipeline \
    --evaluators ollama \
    --max-samples 30
```

---

## Performance

### Latência com GPU (NVIDIA MX450 + Mistral 7B)

```
Input Processing:    ~500ms
LLM Generation:      ~2500ms  ← GPU acelera
Post-processing:     ~200ms
TOTAL:               ~3200ms
```

### Latência sem GPU

```
Input Processing:    ~500ms
LLM Generation:      ~8000ms  ← Muito lento
Post-processing:     ~200ms
TOTAL:               ~8700ms
```

**Ganho com GPU:** ~2.7x mais rápido

### Comparação: Gemini vs Mistral

```
Gemini 2.5 Flash
├─ Latência: 1604ms ⚡
├─ Qualidade: ⭐⭐⭐⭐⭐
└─ Custo: $0.000225

Mistral (Ollama GPU)
├─ Latência: 953ms ⚡⚡
├─ Qualidade: ⭐⭐⭐⭐
└─ Custo: $0.0 (grátis!)
```

---

## Troubleshooting

### GPU não é reconhecida

1. Rode `nvidia-smi`
2. Se funcionar → GPU está ok
3. Se não:
   - Baixe drivers atualizados
   - Reinicie o PC
   - Verifique Device Manager

### Ollama trava

```bash
docker restart ollama
docker logs ollama
# Trocar por modelo menor em .env
```

### "Out of Memory"

```bash
nvidia-smi  # Ver VRAM disponível
# Usar modelo menor
docker exec ollama ollama pull mistral:latest
```

### API não conecta ao Ollama

```bash
docker ps | grep ollama
docker logs ollama
curl http://localhost:11434/api/tags
# Se funcionar em localhost mas não em Docker:
# Edite .env: SLM_BASE_URL=http://ollama:11434
```

### Modelo não baixa

```bash
docker exec ollama ollama ls
docker restart ollama
docker exec ollama ollama pull mistral:latest
```

---

**Última atualização:** 2026-06-27
**Versão:** 2.0 (Consolidado)
