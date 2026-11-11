#!/usr/bin/env python3
"""Gera a trilha de auditoria (prestação de contas) das etapas A-D.

Para cada etapa e cada pergunta, junta em um só registro:
  candidatos (resposta, geração/modelo, fragmentos de contexto), notas RAGAS,
  votos dos juízes (por ordem de apresentação) e a resposta escolhida
  (consenso estrito e contagem sem descarte).

Os arquivos de avaliação/juízes usam os rótulos 'com_ontologia'/'sem_ontologia'/
'ground_truth' como SLOTS genéricos. Nas etapas B, C e D eles NÃO significam o
que o nome diz; este script traduz cada slot para a geração real (sem_g1, sem_g2,
com_g1, h5_g1 = top-k ampliado, sem_gemini, sem_claude).

Só lê api/results/ (cópias finais). Python 3 puro.
Uso:  cd api && python scripts/trilha_auditoria.py
"""
import csv, json, sys
from pathlib import Path

RES = Path(__file__).resolve().parent.parent / "results"
OUT = RES / "trilha_auditoria"

NOME_GERACAO = {
    "com_g1": "com ontologia (geração 1)",
    "sem_g1": "sem ontologia (geração 1)",
    "sem_g2": "sem ontologia (geração 2)",
    "h5_g1": "sem ontologia, top-k ampliado (geração 1)",
    "sem_gemini": "sem ontologia, gerador Gemini",
    "sem_claude": "sem ontologia, gerador Claude",
    "ground_truth_medpt": "resposta de referência do MedPT",
}
ETAPAS = {
    "A": ("evaluation/evaluation_A_20261007_184922.json", "llm_judge/llm_judge_20261007_191141.json",
          "com ontologia × sem ontologia"),
    "B": ("evaluation/evaluation_B_20261007_214746.json", "llm_judge/llm_judge_20261007_221023.json",
          "duas gerações de sem ontologia (piso de ruído)"),
    "C": ("evaluation/evaluation_C_20261008_101132.json", "llm_judge/llm_judge_20261008_103408.json",
          "com ontologia × sem ontologia, top-k ampliado"),
    "D": ("evaluation/evaluation_D_20261007_222543.json", "llm_judge/llm_judge_20261007_224811.json",
          "geradores GPT × Gemini × Claude sobre o mesmo contexto"),
}


def carrega(p):
    with open(RES / p, encoding="utf-8") as f:
        return json.load(f)


def main():
    coleta = {x["question_id"]: x for x in carrega("collection/coleta_262.json")}
    OUT.mkdir(parents=True, exist_ok=True)
    indice, resumo, problemas = [], {}, []

    for et, (f_ev, f_jd, titulo) in ETAPAS.items():
        ev, jd = carrega(f_ev), carrega(f_jd)
        slots = ev["comparison"]["slots"]
        slot2real = {s: (r if r else "ground_truth_medpt") for s, r in slots.items()}
        real2slot = {v: k for k, v in slot2real.items()}
        tr = lambda s: slot2real.get(s, s)  # slot -> geração real ('empate' etc. passam)

        # notas RAGAS por (geração real, question_id)
        ragas = {}
        for cond in ev["conditions"]:
            for it in cond["items"]:
                ragas[(it["answer_key"], it["question_id"])] = it.get("results") or None

        registros, cont_estrito, cont_pool = [], {}, {}
        for r in jd["results"]:
            qid = r["question_id"]
            c = coleta[qid]
            res = c["result"]
            cands = {}
            for slot, real in slot2real.items():
                if real == "ground_truth_medpt":
                    cands[real] = {"slot_no_arquivo": slot, "rotulo": NOME_GERACAO[real],
                                   "resposta": c["ground_truth"]}
                    continue
                a = res["answers"][real]
                arm = a["arm"]
                bloco = res["arms"][arm]
                txt_juiz = r["responses"][slot]
                if (a.get("answer_eval") or "") != txt_juiz:
                    problemas.append(f"{et} q{qid}: texto do juiz difere da coleta em {real}")
                cands[real] = {
                    "slot_no_arquivo": slot, "rotulo": NOME_GERACAO[real],
                    "condicao_de_contexto": arm, "modelo": a.get("model"), "provedor": a.get("provider"),
                    "resposta": a.get("answer_eval"),
                    "n_fragmentos": len(bloco["chunks"]),
                    "fragmentos_de_ontologia": bloco.get("ontology_chunks_added", 0),
                    "fragmentos": [{"posicao": ch.get("rank"), "origem_da_busca": ch.get("retrieval_source"),
                                    "fonte": ch.get("source"), "similaridade": ch.get("score"),
                                    "nota_reranker": ch.get("rerank_score"), "texto": ch.get("content")}
                                   for ch in bloco["chunks"]],
                    "ragas": ragas.get((real, qid)),
                }
            ordens = []
            for o in r["judge_orders"]:
                mp = {l: tr(s) for l, s in o["mapping"].items()}
                votos = []
                for v in o["votes"]:
                    votos.append({"juiz": v["judge"], "escolha_letra": v.get("choice"),
                                  "escolha": mp.get(v.get("choice")) if v.get("choice") else None,
                                  "confianca": v.get("confidence"), "justificativa": v.get("reasoning"),
                                  "erro": v.get("error")})
                ordens.append({"ordem": o["order"], "letra_para_geracao": mp, "votos": votos})
            jv = {j: {"status": d.get("status"), "ordem_1": tr(d.get("order_1")) if d.get("order_1") else None,
                      "ordem_2": tr(d.get("order_2")) if d.get("order_2") else None,
                      "escolha_valida": tr(d["choice_source"]) if d.get("choice_source") else None}
                  for j, d in r["judge_votes"].items()}
            esc = tr(r["consensus"]) if r.get("consensus") else None
            pool = r["pooled"]
            esc_pool = tr(pool["consensus"]) if pool.get("consensus") else None
            cont_estrito[esc or "sem_consenso"] = cont_estrito.get(esc or "sem_consenso", 0) + 1
            cont_pool[esc_pool or "sem_consenso"] = cont_pool.get(esc_pool or "sem_consenso", 0) + 1
            leg = r.get("legacy_ragas_winner")
            reg = {
                "etapa": et, "question_id": qid, "pergunta": r["question"],
                "resposta_referencia_medpt": c["ground_truth"],
                "reescrita_da_pergunta": res.get("question_rewrite"),
                "hyde": res.get("hyde_reformulation"),
                "termos_da_ontologia": res.get("ontology_expansion"),
                "candidatos": cands,
                "julgamento": {"ordens": ordens, "por_juiz": jv,
                               "votos_validos": r.get("n_valid_votes"),
                               "consenso_estrito": esc, "forca_do_consenso": r.get("consensus_strength"),
                               "contagem_sem_descarte": {tr(k): v for k, v in pool["counts"].items()},
                               "escolha_sem_descarte": esc_pool},
                "resposta_escolhida": {"consenso_estrito": esc, "contagem_sem_descarte": esc_pool},
                "vencedor_ragas": tr(leg) if leg else None,
            }
            registros.append(reg)
            indice.append({
                "etapa": et, "question_id": qid,
                **{f"fragmentos_{k}": v["n_fragmentos"] for k, v in cands.items() if "n_fragmentos" in v},
                "consenso_estrito": esc or "sem_consenso", "forca": r.get("consensus_strength"),
                "sem_descarte": esc_pool or "sem_consenso", "vencedor_ragas": tr(leg) if leg else "",
            })
        meta = {"etapa": et, "titulo": titulo, "n_perguntas": len(registros),
                "slots_no_arquivo_para_geracao_real": slot2real,
                "arquivos_de_origem": {"coleta": "collection/coleta_262.json", "avaliacao": f_ev, "juizes": f_jd},
                "juizes": ev and jd["judge_config"]["judges"],
                "prompt_sha256": jd["judge_config"]["prompt_sha256"], "seed": jd["judge_config"]["seed"]}
        with open(OUT / f"etapa_{et}.json", "w", encoding="utf-8") as f:
            json.dump({"meta": meta, "registros": registros}, f, ensure_ascii=False, indent=1)
        resumo[et] = {"consenso_estrito": cont_estrito, "sem_descarte": cont_pool}

    cols = sorted({k for l in indice for k in l}, key=lambda k: (k not in ("etapa", "question_id"), k))
    with open(OUT / "indice_decisoes.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(indice)
    with open(OUT / "conferencia_totais.json", "w", encoding="utf-8") as f:
        json.dump({"totais": resumo, "divergencias": problemas}, f, ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False, indent=1)); print("divergencias texto:", len(problemas))
    for p in problemas[:10]: print(" ", p)


if __name__ == "__main__":
    sys.exit(main())
