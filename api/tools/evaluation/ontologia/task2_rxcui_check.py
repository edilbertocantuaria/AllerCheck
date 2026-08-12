#!/usr/bin/env python3
import json
import requests

print("TAREFA 2: VERIFICAR RXCUI DA NIMESULIDA\n")

# 1. RxCUI do nosso dado
with open("tools/data/processed/evaluation/ontologia/ontologia_raw.json", encoding="utf-8") as f:
    data = json.load(f)

candidatos = [d for d in data if "nimesulid" in d.get("nome_original", "").lower()
              or "nimesulid" in d.get("nome_ingles", "").lower()]

if candidatos:
    nosso_rxcui = candidatos[0].get("rxcui")
    print(f"✓ RxCUI no nosso ontologia_raw.json: {nosso_rxcui}\n")
else:
    print("❌ Nimesulida não encontrada")
    exit(1)

# 2. RxCUI real da API
print("Consultando API RxNav...")
try:
    resp = requests.get("https://rxnav.nlm.nih.gov/REST/rxcui.json?name=nimesulide&search=2")
    api_data = resp.json()
    print(f"Resposta da API: {json.dumps(api_data, indent=2)}\n")

    if api_data.get("idGroup", {}).get("rxUis"):
        api_rxcui = api_data["idGroup"]["rxUis"][0]
        print(f"✓ RxCUI real na API RxNav: {api_rxcui}\n")

        if str(api_rxcui) == str(nosso_rxcui):
            print("✅ RxCUIs CONFEREM — problema está em Fase 2 ou 3 (classes/grafo)")
        else:
            print(f"⚠️  RxCUIs DIVERGEM:")
            print(f"   Nosso dado: {nosso_rxcui}")
            print(f"   API real:   {api_rxcui}")
            print("   ⚠️  Isso significa a nimesulida foi associada ao RxCUI errado desde o início!")
    else:
        print("❌ API não retornou RxCUI válido")
except Exception as e:
    print(f"❌ Erro ao consultar API: {e}")
