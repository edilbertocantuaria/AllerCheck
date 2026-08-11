#!/usr/bin/env python3
"""
🚀 Script Unificado: Roda RAGAS COM e SEM ontologia em paralelo
- OpenAI (gpt-4o-mini) para gerar respostas
- Gemini (gemini-2.5-flash-lite) para avaliar
- 3 amostras de teste (seed 42)
"""

import asyncio
import subprocess
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Carregar variáveis do .env (da raiz do projeto)
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ROOT = Path("c:/Users/edilb/OneDrive/Documentos/AllerCheck/api")
OUTPUT_DIR = PROJECT_ROOT / "tools/data/processed/evaluation"
DATASET_FILE = "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx"

COMMON_ARGS = [
    "python", "-m", "tools.evaluation.ragas.cli", "pipeline",
    "--input-file", DATASET_FILE,
    "--max-samples", "30",  # 🧪 Teste com 3 amostras
    "--evaluators", "gemini",
    "--gemini-model", "gemini-2.5-flash-lite",
    "--seed", "42",
    "--skip-api-check",  # ✅ Pular validação (chaves estão no server)
    "--output-dir", str(OUTPUT_DIR),
]

async def run_ragas(name: str, use_ontology: bool) -> dict:
    """Roda pipeline RAGAS e retorna resultado."""

    args = COMMON_ARGS.copy()
    if use_ontology:
        args.append("--use-ontology")

    ontology_str = "COM ontologia" if use_ontology else "SEM ontologia"
    print(f"\n{'='*70}")
    print(f"INICIANDO: {name} ({ontology_str})")
    print(f"{'='*70}\n")

    try:
        # Chamar python diretamente (já está no env ativado)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=PROJECT_ROOT,
            env=env,
        )

        # Log output em tempo real
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(line.rstrip())

        proc.wait()

        if proc.returncode == 0:
            print(f"\n[OK] {name} COMPLETADO COM SUCESSO\n")
            return {"status": "success", "use_ontology": use_ontology}
        else:
            print(f"\n[ERRO] {name} FALHOU (exit code {proc.returncode})\n")
            return {"status": "failed", "use_ontology": use_ontology}

    except Exception as e:
        print(f"\n[ERRO] Erro ao rodar {name}: {e}\n")
        return {"status": "error", "use_ontology": use_ontology, "error": str(e)}

async def main():
    """Roda ambas as análises em paralelo."""

    print(f"\n{'#'*70}")
    print("# DUAL RAGAS EVALUATION: COM vs SEM ONTOLOGIA")
    print(f"#{'='*68}#")
    print(f"# Dataset: filtred_alergia_medicamentos.xlsx")
    print(f"# Amostras: 3 (teste)")
    print(f"# Seed: 42")
    print(f"# Avaliador: Gemini (gemini-2.5-flash-lite)")
    print(f"# Gerador: OpenAI (via /chat)")
    print(f"# Timestamp: {datetime.now().isoformat()}")
    print(f"#{'='*68}#\n")

    # Rodar ambas em paralelo
    print("[INFO] Rodando ambas as análises em paralelo...\n")

    results = await asyncio.gather(
        run_ragas("RAGAS COM ONTOLOGIA", use_ontology=True),
        run_ragas("RAGAS SEM ONTOLOGIA", use_ontology=False),
    )

    # Relatório final
    print(f"\n{'='*70}")
    print("RELATORIO FINAL")
    print(f"{'='*70}\n")

    with_ontology = results[0]
    without_ontology = results[1]

    print(f"1. COM Ontologia:     {'[OK] SUCESSO' if with_ontology['status'] == 'success' else '[ERRO] FALHA'}")
    print(f"2. SEM Ontologia:     {'[OK] SUCESSO' if without_ontology['status'] == 'success' else '[ERRO] FALHA'}")

    if with_ontology['status'] == 'success' and without_ontology['status'] == 'success':
        print(f"\n[OK] AMBAS AS ANALISES COMPLETADAS!")
        print(f"\n[INFO] Arquivos de saida em: {OUTPUT_DIR}/")
        print(f"\n[INFO] Proximo passo: Comparar resultados")
        print(f"  $ python compare_dual_ragas.py")
    else:
        print(f"\n[AVISO] Algumas analises falharam. Verifique os logs acima.")

    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(main())
