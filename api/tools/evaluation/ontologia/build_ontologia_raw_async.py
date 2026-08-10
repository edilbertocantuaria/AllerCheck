"""
FASE 2 — Consulta às APIs Públicas (Async/Paralelo)
====================================================
Versão paralela com asyncio + aiohttp.
Processa múltiplos medicamentos simultaneamente com controle de concorrência.

Saída: api/tools/data/processed/evaluation/ontologia/ontologia_raw.json

Uso:
    conda activate LangChain
    cd C:\\Users\\edilb\\OneDrive\\Documentos\\AllerCheck\\api
    python tools/evaluation/ontologia/build_ontologia_raw_async.py

Variáveis de ambiente (.env):
    MAX_MEDICAMENTOS   — limitar total, 0 = sem limite (padrão: 0)
    CONCURRENCY        — workers simultâneos (padrão: 10)
    REQUEST_DELAY_MS   — delay entre requests do mesmo worker em ms (padrão: 100)
    REQUEST_TIMEOUT    — timeout por request em s (padrão: 10)
    CHECKPOINT_EVERY   — salvar checkpoint a cada N itens (padrão: 25)
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT  = Path(__file__).resolve().parents[4]
TOOLS_ROOT    = PROJECT_ROOT / "api" / "tools"
INPUT_FILE    = TOOLS_ROOT / "data" / "processed" / "evaluation" / "ontologia" / "medicamentos_unicos.json"
OUTPUT_DIR    = TOOLS_ROOT / "data" / "processed" / "evaluation" / "ontologia"
OUTPUT_FILE   = OUTPUT_DIR / "ontologia_raw.json"
CHECKPOINT    = OUTPUT_DIR / "ontologia_raw_checkpoint.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env", override=True)

MAX_MEDICAMENTOS  = int(os.getenv("MAX_MEDICAMENTOS", "0"))
CONCURRENCY       = int(os.getenv("CONCURRENCY", "10"))
REQUEST_DELAY     = float(os.getenv("REQUEST_DELAY_MS", "100")) / 1000
REQUEST_TIMEOUT   = float(os.getenv("REQUEST_TIMEOUT", "10"))
CHECKPOINT_EVERY  = int(os.getenv("CHECKPOINT_EVERY", "25"))
MAX_RETRIES       = 3

# ---------------------------------------------------------------------------
# HTTP helpers (async)
# ---------------------------------------------------------------------------
async def get_json(session: aiohttp.ClientSession, url: str, params: dict = None) -> dict | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await asyncio.sleep(REQUEST_DELAY)
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
                elif r.status == 404:
                    return None
                else:
                    logging.debug("HTTP %s para %s (tentativa %s)", r.status, url, attempt)
        except asyncio.TimeoutError:
            logging.debug("Timeout em %s (tentativa %s)", url, attempt)
        except Exception as e:
            logging.debug("Erro em %s: %s (tentativa %s)", url, e, attempt)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(REQUEST_DELAY * 2)
    return None

# ---------------------------------------------------------------------------
# APIs (async)
# ---------------------------------------------------------------------------
async def get_rxcui(session, nome_ingles: str) -> str | None:
    data = await get_json(session, "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                          params={"name": nome_ingles, "search": "2"})
    if not data:
        return None
    ids = data.get("idGroup", {}).get("rxnormId", [])
    return ids[0] if ids else None

async def get_sinonimos(session, rxcui: str) -> list[str]:
    data = await get_json(session, f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/allrelated.json")
    if not data:
        return []
    sinonimos = []
    for grupo in data.get("allRelatedGroup", {}).get("conceptGroup", []):
        if grupo.get("tty", "") in ("IN", "BN", "PIN"):
            for c in grupo.get("conceptProperties", []):
                nome = c.get("name", "").strip().lower()
                if nome:
                    sinonimos.append(nome)
    return list(set(sinonimos))

async def get_classes_atc(session, rxcui: str) -> list[dict]:
    """Retorna TODAS as classes ATC (tty=IN ou PIN) para um medicamento."""
    data = await get_json(session, "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json",
                          params={"rxcui": rxcui, "relaSource": "ATC"})
    if not data:
        return []

    infos = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
    classes = []
    seen_ids = set()

    # Primeira passagem: classes com tty=IN (mais relevantes)
    for info in infos:
        if info.get("minConcept", {}).get("tty", "") == "IN":
            item = info.get("rxclassMinConceptItem", {})
            class_id = item.get("classId", "")
            if class_id and class_id not in seen_ids:
                seen_ids.add(class_id)
                classes.append({
                    "classId": class_id,
                    "className": item.get("className", ""),
                    "classType": item.get("classType", "")
                })

    # Segunda passagem: classes com tty=PIN (menos relevantes, mas ainda relevantes)
    for info in infos:
        if info.get("minConcept", {}).get("tty", "") == "PIN":
            item = info.get("rxclassMinConceptItem", {})
            class_id = item.get("classId", "")
            if class_id and class_id not in seen_ids:
                seen_ids.add(class_id)
                classes.append({
                    "classId": class_id,
                    "className": item.get("className", ""),
                    "classType": item.get("classType", "")
                })

    return classes

async def get_membros_classe(session, class_id: str) -> list[dict]:
    data = await get_json(session, "https://rxnav.nlm.nih.gov/REST/rxclass/classMembers.json",
                          params={"classId": class_id, "relaSource": "ATC"})
    if not data:
        return []
    return [
        {"rxcui": m.get("minConcept", {}).get("rxcui", ""),
         "name": m.get("minConcept", {}).get("name", "").lower(),
         "tty": m.get("minConcept", {}).get("tty", "")}
        for m in data.get("drugMemberGroup", {}).get("drugMember", [])
    ]

async def get_hierarquia_atc(session, class_id: str) -> list[dict]:
    data = await get_json(session, "https://rxnav.nlm.nih.gov/REST/rxclass/classContext.json",
                          params={"classId": class_id})
    if not data:
        return []
    paths = data.get("classPathList", {}).get("classPath", [])
    if not paths:
        return []
    return [{"classId": n.get("classId", ""), "className": n.get("className", "")}
            for n in paths[0].get("rxclassMinConcept", [])]

async def get_pharm_class(session, nome_ingles: str) -> list[str]:
    data = await get_json(session, "https://api.fda.gov/drug/ndc.json",
                          params={"search": f"generic_name:{nome_ingles}", "limit": "1"})
    if not data:
        return []
    results = data.get("results", [])
    return results[0].get("pharm_class", []) if results else []

# ---------------------------------------------------------------------------
# Processar um medicamento
# ---------------------------------------------------------------------------
async def processar_medicamento(session: aiohttp.ClientSession, med: dict) -> dict:
    nome_original = med["nome_original"]
    nome_ingles   = med["nome_ingles"]

    resultado = {
        "nome_original":    nome_original,
        "nome_normalizado": med["nome_normalizado"],
        "nome_ingles":      nome_ingles,
        "sinonimos_en":     med.get("sinonimos_en", []),
        "fonte_traducao":   med.get("fonte_traducao", "whodrug"),
        "rxcui":            None,
        "sinonimos_rxnorm": [],
        "classes_atc":      [],  # MUDADO: lista em vez de dict único
        "membros_classe":   [],
        "hierarquia_atc":   [],
        "pharm_class":      [],
        "cobertura":        [],
    }

    if not nome_ingles:
        return resultado

    # RxCUI
    rxcui = await get_rxcui(session, nome_ingles)
    if rxcui:
        resultado["rxcui"] = rxcui
        resultado["cobertura"].append("rxnorm_rxcui")

        # Sinônimos
        sinonimos = await get_sinonimos(session, rxcui)
        if sinonimos:
            resultado["sinonimos_rxnorm"] = sinonimos
            resultado["cobertura"].append("rxnorm_sinonimos")

        # TODAS as Classes ATC (não apenas uma)
        classes = await get_classes_atc(session, rxcui)
        if classes:
            resultado["classes_atc"] = classes
            resultado["cobertura"].append("rxclass_atc")

            # Membros: consolidar de TODAS as classes, deduplicando por rxcui
            membros_dict = {}  # {rxcui: {name, tty, from_class}}
            for classe in classes:
                membros = await get_membros_classe(session, classe["classId"])
                for membro in membros:
                    rxcui_membro = membro.get("rxcui", "")
                    if rxcui_membro and rxcui_membro not in membros_dict:
                        membros_dict[rxcui_membro] = {
                            "rxcui": rxcui_membro,
                            "name": membro.get("name", ""),
                            "tty": membro.get("tty", ""),
                            "from_class": classe["classId"]
                        }

            if membros_dict:
                resultado["membros_classe"] = list(membros_dict.values())
                resultado["cobertura"].append("rxclass_membros")

            # Hierarquia: consolidar de TODAS as classes, deduplicando por classId
            hierarquia_dict = {}  # {classId: {className}}
            for classe in classes:
                hierarquia = await get_hierarquia_atc(session, classe["classId"])
                for nivel in hierarquia:
                    class_id = nivel.get("classId", "")
                    if class_id and class_id not in hierarquia_dict:
                        hierarquia_dict[class_id] = {
                            "classId": class_id,
                            "className": nivel.get("className", "")
                        }

            if hierarquia_dict:
                resultado["hierarquia_atc"] = list(hierarquia_dict.values())
                resultado["cobertura"].append("rxclass_hierarquia")

    # openFDA (independente do RxCUI)
    pharm_class = await get_pharm_class(session, nome_ingles)
    if pharm_class:
        resultado["pharm_class"] = pharm_class
        resultado["cobertura"].append("openfda_ndc")

    return resultado

# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------
def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        with open(CHECKPOINT, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_checkpoint(data: dict) -> None:
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# Main async
# ---------------------------------------------------------------------------
async def main_async(medicamentos: list[dict], checkpoint: dict) -> dict:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    resultados = dict(checkpoint)
    lock = asyncio.Lock()
    contador = {"done": 0, "total": len(medicamentos)}

    pendentes = [m for m in medicamentos if m["nome_original"] not in resultados]
    logging.info("   Pendentes: %d | Já processados: %d", len(pendentes), len(resultados))

    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2)
    async with aiohttp.ClientSession(connector=connector) as session:

        async def processar_com_semaforo(med):
            async with semaphore:
                try:
                    resultado = await processar_medicamento(session, med)
                except Exception as e:
                    logging.error("Erro em %s: %s", med["nome_original"], e)
                    resultado = {
                        "nome_original": med["nome_original"],
                        "nome_ingles": med["nome_ingles"],
                        "erro": str(e),
                        "cobertura": [],
                    }

                async with lock:
                    resultados[med["nome_original"]] = resultado
                    contador["done"] += 1
                    done = contador["done"]
                    total_proc = len(resultados)

                    logging.info("[%d/%d] %-35s → cobertura: %s",
                                 done, len(pendentes),
                                 med["nome_original"][:35],
                                 resultado.get("cobertura", []))

                    if done % CHECKPOINT_EVERY == 0:
                        save_checkpoint(resultados)
                        logging.info("   💾 Checkpoint salvo (%d processados)", total_proc)

        await asyncio.gather(*[processar_com_semaforo(m) for m in pendentes])

    return resultados

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not INPUT_FILE.exists():
        logging.error("Arquivo não encontrado: %s", INPUT_FILE)
        logging.error("Execute primeiro a Fase 1: build_medicamentos_unicos.py")
        return 1

    with open(INPUT_FILE, encoding="utf-8") as f:
        medicamentos = json.load(f)

    if MAX_MEDICAMENTOS > 0:
        logging.info("⚠️  Modo teste: limitando a %d medicamentos", MAX_MEDICAMENTOS)
        medicamentos = medicamentos[:MAX_MEDICAMENTOS]

    total = len(medicamentos)
    logging.info("📋 %d medicamentos para processar", total)
    logging.info("   Concorrência: %d workers | Delay: %.0fms | Timeout: %.0fs",
                 CONCURRENCY, REQUEST_DELAY * 1000, REQUEST_TIMEOUT)

    checkpoint = load_checkpoint()
    logging.info("   Checkpoint: %d já processados", len(checkpoint))

    t0 = time.monotonic()
    resultados = asyncio.run(main_async(medicamentos, checkpoint))
    elapsed = time.monotonic() - t0

    # Salvar resultado final
    resultado_lista = list(resultados.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultado_lista, f, ensure_ascii=False, indent=2)

    # Limpar checkpoint
    if CHECKPOINT.exists():
        CHECKPOINT.unlink()

    # Relatório
    n_com_rxcui  = sum(1 for r in resultado_lista if r.get("rxcui"))
    n_com_classe = sum(1 for r in resultado_lista if r.get("classe_atc"))
    n_com_fda    = sum(1 for r in resultado_lista if r.get("pharm_class"))
    total_final  = len(resultado_lista)

    logging.info("")
    logging.info("✅ Fase 2 concluída em %.1f minutos!", elapsed / 60)
    logging.info("   Arquivo: %s", OUTPUT_FILE)
    logging.info("   Total processado: %d", total_final)
    logging.info("   Com RxCUI:      %d (%.0f%%)", n_com_rxcui,  100 * n_com_rxcui  / total_final if total_final else 0)
    logging.info("   Com classe ATC: %d (%.0f%%)", n_com_classe, 100 * n_com_classe / total_final if total_final else 0)
    logging.info("   Com openFDA:    %d (%.0f%%)", n_com_fda,    100 * n_com_fda    / total_final if total_final else 0)
    logging.info("   Velocidade:     %.1f med/min", total_final / (elapsed / 60))

    if MAX_MEDICAMENTOS > 0:
        logging.info("")
        logging.info("⚠️  Modo teste ativo (MAX_MEDICAMENTOS=%d). Para rodar completo:", MAX_MEDICAMENTOS)
        logging.info("   Defina MAX_MEDICAMENTOS=0 no .env")

    return 0


if __name__ == "__main__":
    sys.exit(main())