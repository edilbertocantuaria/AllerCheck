"""
FASE 1 — Extração de Medicamentos Únicos do VigiMed
====================================================
Lê base_rag_alergia.csv, extrai NOME_MEDICAMENTO_WHODRUG e
PRINCIPIOS_ATIVOS_WHODRUG, deduplica, normaliza e usa OpenAI apenas
como fallback para medicamentos sem princípio ativo em inglês.

Saída: api/tools/data/processed/evaluation/ontologia/medicamentos_unicos.json

Uso:
    conda activate LangChain
    cd C:\\Users\\edilb\\OneDrive\\Documentos\\AllerCheck\\api
    python -m tools.evaluation.ontologia.build_medicamentos_unicos

Variáveis de ambiente (.env):
    OPENAI_API_KEY               — obrigatória para fallback LLM
    OPENAI_MODEL                 — padrão: gpt-4.1-mini
    BATCH_SIZE                   — tamanho do lote para fallback (padrão: 10)
    MAX_RETRIES                  — tentativas por lote (padrão: 8)
    MIN_REQUEST_INTERVAL_SECONDS — intervalo mínimo entre requests (padrão: 2.0)
    MAX_MEDICAMENTOS             — limitar total processado, 0 = sem limite (padrão: 0)
"""

import json
import logging
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import APIError, APITimeoutError, OpenAI, RateLimitError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOOLS_ROOT   = PROJECT_ROOT / "api" / "tools"
RAW_CSV      = TOOLS_ROOT / "data" / "raw" / "vigimed" / "base_rag_alergia.csv"
OUTPUT_DIR   = TOOLS_ROOT / "data" / "processed" / "evaluation" / "ontologia"
OUTPUT_FILE  = OUTPUT_DIR / "medicamentos_unicos.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env", override=True)

OPENAI_MODEL         = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
BATCH_SIZE           = int(os.getenv("BATCH_SIZE", "10"))
MAX_RETRIES          = int(os.getenv("MAX_RETRIES", "8"))
RETRY_BASE_SECONDS   = 2.0
RETRY_MAX_SECONDS    = float(os.getenv("RETRY_MAX_SECONDS", "120"))
REQUEST_TIMEOUT      = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "90"))
MIN_REQUEST_INTERVAL = float(os.getenv("MIN_REQUEST_INTERVAL_SECONDS", "2.0"))
MAX_MEDICAMENTOS     = int(os.getenv("MAX_MEDICAMENTOS", "0"))  # 0 = sem limite

_LAST_REQUEST_AT = 0.0

# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------
SUFIXOS_SAL = [
    "sodium", "potassium", "hydrochloride", "hcl", "mesylate", "mesilate",
    "acetate", "maleate", "tartrate", "phosphate", "sulfate", "monohydrate",
    "dihydrate", "anhydrous", "monosodium", "disodium",
    "cloridrato de", "cloridrato", "fosfato de", "fosfato",
    "bissulfato de", "bissulfato", "sulfato de", "sulfato",
    "sodico", "potassico", "mesilato de", "acetato de",
    "maleato de", "tartarato de",
]

def normalizar(nome: str) -> str:
    nome = nome.lower().strip()
    nome = unicodedata.normalize("NFD", nome)
    nome = "".join(c for c in nome if unicodedata.category(c) != "Mn")
    for sufixo in SUFIXOS_SAL:
        nome = re.sub(rf"\b{re.escape(sufixo)}\b", "", nome)
    return re.sub(r"\s+", " ", nome).strip()

# ---------------------------------------------------------------------------
# Leitura do CSV
# ---------------------------------------------------------------------------
def load_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(path, sep=";", dtype=str, encoding=encoding, low_memory=False)
            return df.fillna("")
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("codec", b"", 0, 1, f"Não foi possível ler {path}")

# ---------------------------------------------------------------------------
# Throttle + retry helpers
# ---------------------------------------------------------------------------
def _throttle():
    global _LAST_REQUEST_AT
    now = time.monotonic()
    elapsed = now - _LAST_REQUEST_AT
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _LAST_REQUEST_AT = time.monotonic()

def _extract_retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return float(retry_after)
        except (TypeError, ValueError):
            pass
    match = re.search(r"Please try again in\s*([0-9]+(?:\.[0-9]+)?)s", str(exc))
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            pass
    return None

def _extract_json(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", stripped)
    if fenced:
        return fenced.group(1).strip()
    first, last = stripped.find("{"), stripped.rfind("}")
    if first != -1 and last != -1 and last > first:
        return stripped[first:last + 1]
    return stripped

# ---------------------------------------------------------------------------
# OpenAI — tradução em lote
# ---------------------------------------------------------------------------
def _build_prompt(nomes: list[str]) -> str:
    lista = "\n".join(f"- {n}" for n in nomes)
    return (
        "Traduza os nomes de medicamentos abaixo para o nome genérico em inglês.\n"
        "Use apenas o nome genérico, sem sufixos de sal (ex: 'sodium', 'hydrochloride').\n"
        "Responda APENAS com JSON válido:\n"
        '{"items": [{"nome_original": "...", "nome_ingles": "..."}]}\n'
        "Sem markdown, sem texto fora do JSON.\n\n"
        f"Medicamentos:\n{lista}"
    )

def traduzir_lote(nomes: list[str], client: OpenAI) -> dict[str, str]:
    prompt = _build_prompt(nomes)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _throttle()
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": "Responda apenas com JSON válido, sem markdown."},
                    {"role": "user", "content": prompt},
                ],
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("Resposta vazia da OpenAI")

            payload = json.loads(_extract_json(content))
            result = {}
            for item in payload.get("items", []):
                orig = str(item.get("nome_original", "")).strip()
                en   = str(item.get("nome_ingles", "")).strip().lower()
                if orig and en:
                    result[orig] = en
            return result

        except (RateLimitError, APITimeoutError) as exc:
            retry_after = _extract_retry_after(exc)
            backoff = RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            wait = min(retry_after if retry_after else backoff, RETRY_MAX_SECONDS)
            logging.warning("Tentativa %s/%s: rate limit/timeout. Aguardando %.1fs.", attempt, MAX_RETRIES, wait)
            time.sleep(wait)

        except APIError as exc:
            retriable = getattr(exc, "status_code", None) in {408, 409, 429, 500, 502, 503, 504}
            if retriable and attempt < MAX_RETRIES:
                backoff = RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                wait = min(backoff, RETRY_MAX_SECONDS)
                logging.warning("Tentativa %s/%s: APIError %s. Aguardando %.1fs.", attempt, MAX_RETRIES, getattr(exc, "status_code", "?"), wait)
                time.sleep(wait)
                continue
            raise

        except Exception as exc:
            if attempt < MAX_RETRIES:
                wait = min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5), RETRY_MAX_SECONDS)
                logging.warning("Tentativa %s/%s: erro inesperado: %s. Aguardando %.1fs.", attempt, MAX_RETRIES, exc, wait)
                time.sleep(wait)
                continue
            raise

    raise RuntimeError(f"Não foi possível traduzir lote após {MAX_RETRIES} tentativas")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not RAW_CSV.exists():
        logging.error("CSV não encontrado: %s", RAW_CSV)
        logging.error("Execute primeiro: python -m tools.pipelines.vigimed.run")
        return 1

    logging.info("📂 Lendo %s...", RAW_CSV)
    df = load_csv(RAW_CSV)
    logging.info("   %d linhas carregadas", len(df))

    # -----------------------------------------------------------------------
    # 1. Extrair pares únicos
    # -----------------------------------------------------------------------
    vistos: dict[str, dict] = {}

    for _, row in df.iterrows():
        nome_original = str(row.get("NOME_MEDICAMENTO_WHODRUG", "")).strip()
        principios    = str(row.get("PRINCIPIOS_ATIVOS_WHODRUG", "")).strip()

        if not nome_original or nome_original.lower() == "nan":
            continue

        chave = nome_original.lower()
        ativos = (
            [p.strip() for p in principios.split("|") if p.strip()]
            if principios and principios.lower() not in ("nan", "")
            else []
        )

        if chave not in vistos:
            vistos[chave] = {"nome_original": nome_original, "principios_raw": set(ativos)}
        else:
            vistos[chave]["principios_raw"].update(ativos)

    unicos = [
        {**v, "principios_raw": sorted(v["principios_raw"])}
        for v in vistos.values()
    ]

    # Ordenar antes de limitar para resultado determinístico
    unicos.sort(key=lambda x: x["nome_original"].lower())

    # Aplicar limite de teste
    if MAX_MEDICAMENTOS > 0:
        logging.info("⚠️  Modo teste: limitando a %d medicamentos (MAX_MEDICAMENTOS=%d)", MAX_MEDICAMENTOS, MAX_MEDICAMENTOS)
        unicos = unicos[:MAX_MEDICAMENTOS]

    com_principio = [r for r in unicos if r["principios_raw"]]
    sem_principio = [r for r in unicos if not r["principios_raw"]]

    logging.info("   %d medicamentos únicos%s", len(unicos), f" (de {len(vistos)} totais)" if MAX_MEDICAMENTOS > 0 else "")
    logging.info("   Com princípio ativo (WHODrug): %d", len(com_principio))
    logging.info("   Sem princípio ativo (fallback LLM): %d", len(sem_principio))

    # -----------------------------------------------------------------------
    # 2. LLM fallback via OpenAI (só se necessário)
    # -----------------------------------------------------------------------
    traducoes_llm: dict[str, str] = {}

    if sem_principio:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logging.warning("OPENAI_API_KEY não encontrada — %d medicamentos sem tradução.", len(sem_principio))
        else:
            client = OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=0)
            nomes_sem = [r["nome_original"] for r in sem_principio]
            total_lotes = -(-len(nomes_sem) // BATCH_SIZE)

            logging.info("🤖 Traduzindo %d medicamentos via OpenAI (%s)...", len(nomes_sem), OPENAI_MODEL)
            for i in range(0, len(nomes_sem), BATCH_SIZE):
                lote = nomes_sem[i:i + BATCH_SIZE]
                lote_num = i // BATCH_SIZE + 1
                logging.info("   Lote %d/%d (%d itens)...", lote_num, total_lotes, len(lote))
                try:
                    resultado_lote = traduzir_lote(lote, client)
                    traducoes_llm.update(resultado_lote)
                    logging.info("   ✓ %d traduções obtidas", len(resultado_lote))
                except Exception as exc:
                    logging.error("   ✗ Erro no lote %d: %s", lote_num, exc)

    # -----------------------------------------------------------------------
    # 3. Montar estrutura final
    # -----------------------------------------------------------------------
    resultado = []

    for r in unicos:
        nome_original = r["nome_original"]
        principios    = r["principios_raw"]

        if principios:
            nomes_norm   = [n for n in (normalizar(p) for p in principios) if n]
            nome_ingles  = nomes_norm[0] if nomes_norm else ""
            sinonimos_en = nomes_norm[1:] if len(nomes_norm) > 1 else []
            fonte        = "whodrug"
        else:
            nome_ingles  = traducoes_llm.get(nome_original, "").strip()
            sinonimos_en = []
            fonte        = "llm" if nome_ingles else "desconhecido"

        resultado.append({
            "nome_original":    nome_original,
            "nome_normalizado": normalizar(nome_original),
            "nome_ingles":      nome_ingles,
            "sinonimos_en":     sinonimos_en,
            "principios_raw":   principios,
            "fonte_traducao":   fonte,
        })

    # -----------------------------------------------------------------------
    # 4. Salvar
    # -----------------------------------------------------------------------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------------
    # 5. Relatório
    # -----------------------------------------------------------------------
    n_whodrug      = sum(1 for r in resultado if r["fonte_traducao"] == "whodrug")
    n_llm          = sum(1 for r in resultado if r["fonte_traducao"] == "llm")
    n_desconhecido = sum(1 for r in resultado if r["fonte_traducao"] == "desconhecido")
    total          = len(resultado)

    logging.info("")
    logging.info("✅ Fase 1 concluída!")
    logging.info("   Arquivo: %s", OUTPUT_FILE)
    logging.info("   Total: %d medicamentos únicos", total)
    logging.info("   WHODrug: %d (%.0f%%)", n_whodrug, 100 * n_whodrug / total if total else 0)
    logging.info("   LLM:     %d (%.0f%%)", n_llm, 100 * n_llm / total if total else 0)
    logging.info("   Sem tradução: %d (%.0f%%)", n_desconhecido, 100 * n_desconhecido / total if total else 0)
    logging.info("")
    logging.info("Preview (primeiros 10):")
    for r in resultado[:10]:
        sin = f" | sinônimos: {r['sinonimos_en']}" if r["sinonimos_en"] else ""
        logging.info("   %-35s → %-25s [%s]%s",
                     r["nome_original"], r["nome_ingles"] or "(sem tradução)",
                     r["fonte_traducao"], sin)

    if MAX_MEDICAMENTOS > 0:
        logging.info("")
        logging.info("⚠️  Modo teste ativo (MAX_MEDICAMENTOS=%d). Para rodar completo:", MAX_MEDICAMENTOS)
        logging.info("   Remova MAX_MEDICAMENTOS do .env ou defina MAX_MEDICAMENTOS=0")

    return 0


if __name__ == "__main__":
    sys.exit(main())