"""
FASE 1b — Correção de Nomes em Português / Corrompidos
=======================================================
Identifica medicamentos cujo nome_ingles ficou em português ou corrompido
(_x000d_, acentos, termos PT-BR) e corrige via OpenAI em uma única chamada.

Atualiza: api/tools/data/processed/evaluation/ontologia/medicamentos_unicos.json

Uso:
    conda activate LangChain
    cd C:\\Users\\edilb\\OneDrive\\Documentos\\AllerCheck\\api
    python tools/evaluation/ontologia/fix_nomes_ingles.py
"""

import json
import os
import sys
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[4]
INPUT_FILE   = PROJECT_ROOT / "api" / "tools" / "data" / "processed" / "evaluation" / "ontologia" / "medicamentos_unicos.json"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env", override=True)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# ---------------------------------------------------------------------------
# Detectar nomes problemáticos
# ---------------------------------------------------------------------------
PALAVRAS_PT = [
    'trihidrato', 'micronizado', 'sodico', 'potassico', 'besilato',
    'palmitato', 'fumarato', 'succinato', 'cloridrato', 'fosfato',
    '_x000d_', 'acido', 'humana', 'sodica', 'dipropionato', 'bupivacaina',
    'condroitina', 'desvenlafaxina', 'benserazida', 'betametasona',
    'sulfametoxazol', 'ampicilina', 'amoxicilina', 'palonosetrona',
    'budesonida', 'peroxido', 'benzoila', 'anlodipino', 'arginina',
    'cianocobalamina',
]

def parece_portugues(nome: str) -> bool:
    nfkd = unicodedata.normalize('NFD', nome)
    tem_acento = any(unicodedata.category(c) == 'Mn' for c in nfkd)
    return tem_acento or any(p in nome.lower() for p in PALAVRAS_PT)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    with open(INPUT_FILE, encoding='utf-8') as f:
        medicamentos = json.load(f)

    # Identificar problemáticos
    problematicos = [
        m for m in medicamentos
        if m.get('nome_ingles') and parece_portugues(m['nome_ingles'])
    ]

    print(f"Total medicamentos: {len(medicamentos)}")
    print(f"Com nome problemático: {len(problematicos)}")

    if not problematicos:
        print("Nenhum problema encontrado.")
        return 0

    # Montar lista para o prompt
    lista = "\n".join(
        f'- nome_original: "{m["nome_original"]}" | nome_ingles_atual: "{m["nome_ingles"]}"'
        for m in problematicos
    )

    prompt = (
        "Os itens abaixo têm o campo nome_ingles incorreto — está em português, corrompido com _x000d_, "
        "ou contém sufixos de sal farmacêutico. Corrija para o nome genérico em inglês limpo.\n"
        "Regras:\n"
        "- Use apenas o nome genérico principal em inglês (ex: 'amoxicillin', não 'amoxicillin trihydrate')\n"
        "- Para combinações (ex: amoxicilina + clavulanato), use o ingrediente principal\n"
        "- Remova _x000d_ e qualquer caractere de controle\n"
        "- Se for uma vacina ou produto biológico complexo sem nome genérico simples, use o nome mais reconhecível\n"
        "- Responda APENAS com JSON válido no formato:\n"
        '{"items": [{"nome_original": "...", "nome_ingles": "..."}]}\n'
        "Sem markdown, sem texto fora do JSON.\n\n"
        f"Itens:\n{lista}"
    )

    print(f"\nEnviando {len(problematicos)} itens para OpenAI ({OPENAI_MODEL})...")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY não encontrada no .env")
        return 1

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": "Responda apenas com JSON válido, sem markdown."},
            {"role": "user", "content": prompt},
        ],
    )

    content = (response.choices[0].message.content or "").strip()

    # Extrair JSON
    import re
    fenced = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', content)
    if fenced:
        content = fenced.group(1).strip()
    else:
        first, last = content.find('{'), content.rfind('}')
        if first != -1 and last != -1:
            content = content[first:last+1]

    payload = json.loads(content)
    correcoes = {item["nome_original"]: item["nome_ingles"] for item in payload.get("items", [])}

    print(f"Correções recebidas: {len(correcoes)}")

    # Aplicar correções
    atualizados = 0
    for m in medicamentos:
        if m["nome_original"] in correcoes:
            nome_novo = correcoes[m["nome_original"]].strip().lower()
            nome_antigo = m["nome_ingles"]
            if nome_novo and nome_novo != nome_antigo:
                m["nome_ingles"] = nome_novo
                m["fonte_traducao"] = "llm_fix"
                atualizados += 1
                print(f"  ✓ {m['nome_original'][:40]:<40} {nome_antigo} → {nome_novo}")

    # Salvar
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(medicamentos, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {atualizados} nomes corrigidos em {INPUT_FILE}")
    print(f"   Não corrigidos: {len(problematicos) - atualizados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())