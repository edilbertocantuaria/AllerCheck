"""
FASE 2 — Consulta às APIs Públicas (RxNorm + RxClass + openFDA)
================================================================
Lê medicamentos_unicos.json e para cada medicamento consulta:
  2a. RxNorm  → RxCUI
  2b. RxNorm  → sinônimos (allrelated, tty=IN/BN)
  2c. RxClass → classe ATC (byRxcui, filtrar tty=IN)
  2d. RxClass → membros da classe (classMembers)
  2e. RxClass → hierarquia ATC (classContext)
  2f. openFDA → pharm_class EPC/CS/MoA (drug/ndc)

Saída: api/tools/data/processed/evaluation/ontologia/ontologia_raw.json

Uso:
    conda activate LangChain
    cd C:\\Users\\edilb\\OneDrive\\Documentos\\AllerCheck\\api
    python tools/evaluation/ontologia/build_ontologia_raw.py

Variáveis de ambiente (.env):
    MAX_MEDICAMENTOS   — limitar total, 0 = sem limite (padrão: 0)
    REQUEST_DELAY_MS   — delay entre requests em ms (padrão: 200)
    REQUEST_TIMEOUT    — timeout por request em s (padrão: 10)
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOOLS_ROOT   = PROJECT_ROOT / "api" / "tools"
INPUT_FILE   = TOOLS_ROOT / "data" / "processed" / "evaluation" / "ontologia" / "medicamentos_unicos.json"
OUTPUT_DIR   = TOOLS_ROOT / "data" / "processed" / "evaluation" / "ontologia"
OUTPUT_FILE  = OUTPUT_DIR / "ontologia_raw.json"
CHECKPOINT   = OUTPUT_DIR / "ontologia_raw_checkpoint.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env", override=True)

MAX_MEDICAMENTOS = int(os.getenv("MAX_MEDICAMENTOS", "0"))
REQUEST_DELAY    = float(os.getenv("REQUEST_DELAY_MS", "200")) / 1000
REQUEST_TIMEOUT  = float(os.getenv("REQUEST_TIMEOUT", "10"))

# ---------------------------------------------------------------------------
# HTTP helper com retry simples
# ---------------------------------------------------------------------------
def get_json(url: str, params: dict = None, retries: int = 3) -> dict | None:
    for attempt in range(1, retries + 1):
        try:
            time.sleep(REQUEST_DELAY)
            r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 404:
                return None
            else:
                logging.warning("HTTP %s para %s (tentativa %s/%s)", r.status_code, url, attempt, retries)
        except requests.exceptions.Timeout:
            logging.warning("Timeout em %s (tentativa %s/%s)", url, attempt, retries)
        except Exception as e:
            logging.warning("Erro em %s: %s (tentativa %s/%s)", url, e, attempt, retries)
        if attempt < retries:
            time.sleep(REQUEST_DELAY * 2)
    return None

# ---------------------------------------------------------------------------
# 2a. RxNorm — RxCUI
# ---------------------------------------------------------------------------
def get_rxcui(nome_ingles: str) -> str | None:
    data = get_json(
        "https://rxnav.nlm.nih.gov/REST/rxcui.json",
        params={"name": nome_ingles, "search": "2"},
    )
    if not data:
        return None
    ids = data.get("idGroup", {}).get("rxnormId", [])
    return ids[0] if ids else None

# ---------------------------------------------------------------------------
# 2b. RxNorm — sinônimos (allrelated)
# ---------------------------------------------------------------------------
def get_sinonimos(rxcui: str) -> list[str]:
    data = get_json(f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/allrelated.json")
    if not data:
        return []

    sinonimos = []
    grupos = data.get("allRelatedGroup", {}).get("conceptGroup", [])
    for grupo in grupos:
        tty = grupo.get("tty", "")
        if tty in ("IN", "BN", "PIN"):
            for conceito in grupo.get("conceptProperties", []):
                nome = conceito.get("name", "").strip().lower()
                if nome:
                    sinonimos.append(nome)
    return list(set(sinonimos))

# ---------------------------------------------------------------------------
# 2c. RxClass — classe ATC (filtrar tty=IN)
# ---------------------------------------------------------------------------
def get_classe_atc(rxcui: str) -> dict | None:
    data = get_json(
        "https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json",
        params={"rxcui": rxcui, "relaSource": "ATC"},
    )
    if not data:
        return None

    infos = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
    # Priorizar tty=IN (ingrediente ativo), ignorar MIN (combinações)
    for info in infos:
        tty = info.get("minConcept", {}).get("tty", "")
        if tty == "IN":
            item = info.get("rxclassMinConceptItem", {})
            return {
                "classId":   item.get("classId", ""),
                "className": item.get("className", ""),
                "classType": item.get("classType", ""),
            }
    # Fallback: pegar o primeiro se não houver IN
    if infos:
        item = infos[0].get("rxclassMinConceptItem", {})
        return {
            "classId":   item.get("classId", ""),
            "className": item.get("className", ""),
            "classType": item.get("classType", ""),
        }
    return None

# ---------------------------------------------------------------------------
# 2d. RxClass — membros da classe (crossReactsWith)
# ---------------------------------------------------------------------------
def get_membros_classe(class_id: str) -> list[dict]:
    data = get_json(
        "https://rxnav.nlm.nih.gov/REST/rxclass/classMembers.json",
        params={"classId": class_id, "relaSource": "ATC"},
    )
    if not data:
        return []

    membros = []
    for membro in data.get("drugMemberGroup", {}).get("drugMember", []):
        conceito = membro.get("minConcept", {})
        membros.append({
            "rxcui": conceito.get("rxcui", ""),
            "name":  conceito.get("name", "").lower(),
            "tty":   conceito.get("tty", ""),
        })
    return membros

# ---------------------------------------------------------------------------
# 2e. RxClass — hierarquia ATC completa
# ---------------------------------------------------------------------------
def get_hierarquia_atc(class_id: str) -> list[dict]:
    data = get_json(
        "https://rxnav.nlm.nih.gov/REST/rxclass/classContext.json",
        params={"classId": class_id},
    )
    if not data:
        return []

    paths = data.get("classPathList", {}).get("classPath", [])
    if not paths:
        return []

    hierarquia = []
    for nivel in paths[0].get("rxclassMinConcept", []):
        hierarquia.append({
            "classId":   nivel.get("classId", ""),
            "className": nivel.get("className", ""),
        })
    return hierarquia

# ---------------------------------------------------------------------------
# 2f. openFDA — pharm_class EPC/CS/MoA
# ---------------------------------------------------------------------------
def get_pharm_class(nome_ingles: str) -> list[str]:
    data = get_json(
        "https://api.fda.gov/drug/ndc.json",
        params={"search": f"generic_name:{nome_ingles}", "limit": "1"},
    )
    if not data:
        return []

    results = data.get("results", [])
    if not results:
        return []

    return results[0].get("pharm_class", [])

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

    # Aplicar limite
    if MAX_MEDICAMENTOS > 0:
        logging.info("⚠️  Modo teste: limitando a %d medicamentos", MAX_MEDICAMENTOS)
        medicamentos = medicamentos[:MAX_MEDICAMENTOS]

    total = len(medicamentos)
    logging.info("📋 %d medicamentos para processar", total)
    logging.info("   Delay entre requests: %.0fms | Timeout: %.0fs", REQUEST_DELAY * 1000, REQUEST_TIMEOUT)

    # Carregar checkpoint (retomar de onde parou)
    checkpoint = load_checkpoint()
    logging.info("   Checkpoint: %d já processados", len(checkpoint))

    resultados = dict(checkpoint)
    sem_rxcui  = 0
    sem_classe = 0

    for i, med in enumerate(medicamentos, 1):
        nome_original = med["nome_original"]
        nome_ingles   = med["nome_ingles"]

        # Pular se já no checkpoint
        if nome_original in resultados:
            continue

        logging.info("[%d/%d] %s → %s", i, total, nome_original, nome_ingles)

        resultado = {
            "nome_original":    nome_original,
            "nome_normalizado": med["nome_normalizado"],
            "nome_ingles":      nome_ingles,
            "sinonimos_en":     med.get("sinonimos_en", []),
            "fonte_traducao":   med.get("fonte_traducao", "whodrug"),
            "rxcui":            None,
            "sinonimos_rxnorm": [],
            "classe_atc":       None,
            "membros_classe":   [],
            "hierarquia_atc":   [],
            "pharm_class":      [],
            "cobertura":        [],  # quais APIs retornaram dados
        }

        if not nome_ingles:
            logging.warning("   ⚠️  Sem nome em inglês — pulando APIs")
            resultados[nome_original] = resultado
            save_checkpoint(resultados)
            continue

        # 2a. RxCUI
        rxcui = get_rxcui(nome_ingles)
        if rxcui:
            resultado["rxcui"] = rxcui
            resultado["cobertura"].append("rxnorm_rxcui")
            logging.info("   RxCUI: %s", rxcui)

            # 2b. Sinônimos
            sinonimos = get_sinonimos(rxcui)
            if sinonimos:
                resultado["sinonimos_rxnorm"] = sinonimos
                resultado["cobertura"].append("rxnorm_sinonimos")

            # 2c. Classe ATC
            classe = get_classe_atc(rxcui)
            if classe:
                resultado["classe_atc"] = classe
                resultado["cobertura"].append("rxclass_atc")
                logging.info("   Classe ATC: %s — %s", classe["classId"], classe["className"])

                # 2d. Membros da classe
                membros = get_membros_classe(classe["classId"])
                if membros:
                    resultado["membros_classe"] = membros
                    resultado["cobertura"].append("rxclass_membros")
                    logging.info("   Membros: %d", len(membros))

                # 2e. Hierarquia ATC
                hierarquia = get_hierarquia_atc(classe["classId"])
                if hierarquia:
                    resultado["hierarquia_atc"] = hierarquia
                    resultado["cobertura"].append("rxclass_hierarquia")
            else:
                sem_classe += 1
                logging.info("   ⚠️  Sem classe ATC")
        else:
            sem_rxcui += 1
            logging.info("   ⚠️  Sem RxCUI")

        # 2f. openFDA (independente do RxCUI)
        pharm_class = get_pharm_class(nome_ingles)
        if pharm_class:
            resultado["pharm_class"] = pharm_class
            resultado["cobertura"].append("openfda_ndc")
            logging.info("   pharm_class: %s", pharm_class)

        resultados[nome_original] = resultado

        # Checkpoint a cada 10
        if i % 10 == 0:
            save_checkpoint(resultados)
            logging.info("   💾 Checkpoint salvo (%d/%d)", i, total)

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
    logging.info("✅ Fase 2 concluída!")
    logging.info("   Arquivo: %s", OUTPUT_FILE)
    logging.info("   Total processado: %d", total_final)
    logging.info("   Com RxCUI:        %d (%.0f%%)", n_com_rxcui,  100 * n_com_rxcui  / total_final if total_final else 0)
    logging.info("   Com classe ATC:   %d (%.0f%%)", n_com_classe, 100 * n_com_classe / total_final if total_final else 0)
    logging.info("   Com openFDA:      %d (%.0f%%)", n_com_fda,    100 * n_com_fda    / total_final if total_final else 0)
    logging.info("   Sem RxCUI:        %d", sem_rxcui)
    logging.info("   Sem classe ATC:   %d", sem_classe)

    if MAX_MEDICAMENTOS > 0:
        logging.info("")
        logging.info("⚠️  Modo teste ativo (MAX_MEDICAMENTOS=%d). Para rodar completo:", MAX_MEDICAMENTOS)
        logging.info("   Defina MAX_MEDICAMENTOS=0 no .env")

    return 0


if __name__ == "__main__":
    sys.exit(main())