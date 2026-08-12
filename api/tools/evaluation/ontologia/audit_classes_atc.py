#!/usr/bin/env python3
"""
Auditoria de classes ATC na ontologia.

Identifica medicamentos com múltiplos grupos anatômicos distintos,
sinalizando candidatos a revisão/correção sem aplicar filtro automático.
"""

import json
from pathlib import Path
from collections import defaultdict

# Mapa de primeira letra ATC → grupo anatômico
ATC_GROUPS = {
    'A': 'Alimentary tract and metabolism',
    'B': 'Blood and blood forming organs',
    'C': 'Cardiovascular system',
    'D': 'Dermatologicals',
    'G': 'Genito urinary system and sex hormones',
    'H': 'Systemic hormonal preparations',
    'J': 'Antiinfectives for systemic use',
    'L': 'Antineoplastic and immunomodulating agents',
    'M': 'Musculo-skeletal system',
    'N': 'Nervous system',
    'P': 'Antiparasitic products',
    'R': 'Respiratory system',
    'S': 'Sensory organs',
    'V': 'Various',
}

def main():
    # 1. CARREGAR ONTOLOGIA
    onto_path = Path("tools/data/processed/evaluation/ontologia/ontologia_raw.json")
    if not onto_path.exists():
        print(f"❌ Arquivo não encontrado: {onto_path}")
        return

    with open(onto_path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"📊 AUDITORIA DE CLASSES ATC")
    print(f"{'='*80}\n")

    # 2. ANALISAR MEDICAMENTOS
    candidatos = []
    total_meds = len(data)
    multi_class_meds = 0
    multi_group_meds = 0

    for med_entry in data:
        nome_original = med_entry.get("nome_original", "Unknown")
        nome_ingles = med_entry.get("nome_ingles", "Unknown")
        rxcui = med_entry.get("rxcui", "Unknown")
        classes = med_entry.get("classes_atc", [])

        if len(classes) <= 1:
            continue

        multi_class_meds += 1

        # Extrair grupos anatômicos de topo
        grupos = set()
        for cls in classes:
            class_id = cls.get("classId", "")
            if class_id and len(class_id) > 0:
                first_letter = class_id[0].upper()
                grupos.add(first_letter)

        # Se tem múltiplos grupos, é candidato a revisão
        if len(grupos) >= 2:
            multi_group_meds += 1
            candidatos.append({
                "nome_original": nome_original,
                "nome_ingles": nome_ingles,
                "rxcui": rxcui,
                "grupos_anatomicos": sorted(list(grupos)),
                "classes_atc": [
                    {
                        "classId": cls.get("classId", ""),
                        "className": cls.get("className", "")
                    }
                    for cls in classes
                ],
            })

    # 3. ORDENAR POR NÚMERO DE GRUPOS (decrescente)
    candidatos.sort(key=lambda x: len(x["grupos_anatomicos"]), reverse=True)

    # 4. SALVAR RELATÓRIO
    output_path = Path("tools/data/processed/evaluation/ontologia/auditoria_classes_atc.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(candidatos, f, ensure_ascii=False, indent=2)

    # 5. IMPRIMIR ESTATÍSTICAS
    print(f"Total de medicamentos no ontologia_raw.json: {total_meds}")
    print(f"Medicamentos com múltiplas classes ATC: {multi_class_meds} ({multi_class_meds*100/total_meds:.1f}%)")
    print(f"Medicamentos com múltiplos grupos anatômicos distintos: {multi_group_meds} ({multi_group_meds*100/total_meds:.1f}%)")
    print(f"\n{'='*80}")
    print(f"TOP 30 CANDIDATOS A REVISÃO (ordenados por nº de grupos)\n")

    for rank, cand in enumerate(candidatos[:30], 1):
        grupos_str = ", ".join(cand["grupos_anatomicos"])
        grupos_desc = ", ".join(ATC_GROUPS.get(g, "?") for g in cand["grupos_anatomicos"])
        print(f"{rank:2}. {cand['nome_ingles']:<30} | RXCUI: {cand['rxcui']:<10}")
        print(f"    Grupos: [{grupos_str}] ({grupos_desc})")
        print(f"    Classes ATC:")
        for cls in cand["classes_atc"]:
            print(f"      • {cls['classId']:<12} — {cls['className']}")
        print()

    print(f"{'='*80}")
    print(f"✅ Auditoria salva em: {output_path}\n")

if __name__ == "__main__":
    main()
