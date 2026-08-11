#!/usr/bin/env python3
"""
Script para testar APENAS a condição SEM ONTOLOGIA e diagnosticar qual pergunta falha.
Executa 30 amostras com logging explícito de cada item.
"""

import subprocess
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Carregar .env do diretório raiz do projeto
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

os.chdir("C:/Users/edilb/OneDrive/Documentos/AllerCheck/api")

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"

print("[INFO] Executando RAGAS SEM ONTOLOGIA (30 amostras)")
print("[INFO] Procurando pela pergunta que falha...")
print()

cmd = [
    sys.executable,
    "-m", "tools.evaluation.ragas.cli",
    "pipeline",
    "--input-file", "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
    "--max-samples", "30",
    "--seed", "42",
    "--evaluators", "gemini",
    # --use-ontology NÃO adicionado = sem ontologia (false)
]

# Copiar todas as variáveis de ambiente (incluindo as do .env)
env.update(os.environ)

result = subprocess.run(
    cmd,
    env=env,
    encoding="utf-8",
    errors="replace",
)

sys.exit(result.returncode)
