#!/usr/bin/env python3
"""
Auditoria refinada: ignora rotas de administração (S/D) e foca em
combinações realmente incompatíveis.
"""

import json
from collections import defaultdict

ATC_GROUPS = {
    'A': 'Alimentary tract and metabolism',
    'B': 'Blood and blood forming organs',
    'C': 'Cardiovascular system',
    'D': 'Dermatologicals',
    'G': 'Genito urinary system',
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

# Grupos que indicam apenas rota de administração (não terapia real)
ADMIN_ROUTES = {'S', 'D'}  # Oftálmico/tópico

# Combinações suspeitas de terapias incompatíveis
SUSPICIOUS_PAIRS = [
    ('N', 'M'),  # Sistema nervoso + musculoesquelético (sem relação plausível)
    ('L', 'J'),  # Oncológico + infeccioso (a menos que seja especial)
    ('N', 'L'),  # Sistema nervoso + oncológico (sem relação)
    ('H', 'L'),  # Hormonal + oncológico
]

print("TAREFA 4: AUDITORIA REFINADA (REDUZINDO FALSOS POSITIVOS)\n")
print("Critérios:")
print("  • Ignora rotas de administração (S=oftálmico, D=tópico)")
print("  • Foca em combinações terapeuticamente incompatíveis")
print()

with open("tools/data/processed/evaluation/ontologia/ontologia_raw.json", encoding="utf-8") as f:
    data = json.load(f)

candidatos_refinados = []

for med in data:
    classes = med.get("classes_atc", [])
    if len(classes) <= 1:
        continue

    # Extrair grupos, ignorando rotas de administração
    grupos = set()
    for cls in classes:
        class_id = cls.get("classId", "")
        if class_id:
            grupo = class_id[0].upper()
            if grupo not in ADMIN_ROUTES:
                grupos.add(grupo)

    # Se ainda tem 2+ grupos após filtrar rotas, é candidato
    if len(grupos) >= 2:
        # Verificar se é uma combinação suspeita
        grupos_sorted = sorted(grupos)
        is_suspicious = False
        for g1, g2 in SUSPICIOUS_PAIRS:
            if (g1 in grupos and g2 in grupos) or (g2 in grupos and g1 in grupos):
                is_suspicious = True
                break

        candidatos_refinados.append({
            "nome_original": med.get("nome_original", ""),
            "nome_ingles": med.get("nome_ingles", ""),
            "rxcui": med.get("rxcui", ""),
            "grupos_anatomicos": sorted(list(grupos)),
            "is_suspicious": is_suspicious,
            "classes_atc": [
                {"classId": cls.get("classId"), "className": cls.get("className")}
                for cls in classes
            ],
        })

# Ordenar: suspeitos primeiro, depois por número de grupos
candidatos_refinados.sort(key=lambda x: (-x["is_suspicious"], -len(x["grupos_anatomicos"])))

print(f"Total de medicamentos: {len(data)}")
print(f"Com múltiplas classes (antes do filtro): {sum(1 for m in data if len(m.get('classes_atc', [])) > 1)}")
print(f"Com múltiplos grupos após remover rotas: {len(candidatos_refinados)}")
print(f"Potencialmente suspeitos: {sum(1 for c in candidatos_refinados if c['is_suspicious'])}\n")

print("="*100)
print("TOP 30 CANDIDATOS (POTENCIALMENTE SUSPEITOS PRIMEIRO)")
print("="*100 + "\n")

for rank, cand in enumerate(candidatos_refinados[:30], 1):
    marca = "⚠️ SUSPEITO" if cand["is_suspicious"] else "   Normal"
    print(f"{rank:2}. {marca} | {cand['nome_ingles']:<30} | RXCUI: {cand['rxcui']:<10}")
    print(f"    Grupos: {', '.join(cand['grupos_anatomicos'])}")
    print(f"    Classes:")
    for cls in cand["classes_atc"]:
        print(f"      • {cls['classId']:<10} — {cls['className']}")
    print()

# Salvar resultado
output_path = "tools/data/processed/evaluation/ontologia/auditoria_classes_atc_refinada.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(candidatos_refinados, f, ensure_ascii=False, indent=2)

print(f"\n✅ Resultados salvos em: {output_path}")
