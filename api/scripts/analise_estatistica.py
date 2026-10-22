#!/usr/bin/env python3
"""Reproduz todos os cálculos estatísticos do TCC a partir dos JSONs de juízes.

Somente biblioteca padrão (sem numpy/scipy). Lê, por etapa, o arquivo
llm_judge_*.json (que já contém os escores RAGAS por pergunta e avaliador).

Uso (a partir de api/):
    python scripts/analise_estatistica.py
    python scripts/analise_estatistica.py --boot 10000 --seed 42 --saida resultados_estatisticos.json

Parâmetros fixos do estudo: IC bootstrap percentil 95%, B = 10000, semente 42.
Tudo o que o script imprime é derivado dos dados; nada é digitado à mão.
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

DADOS = Path(__file__).resolve().parents[1] / "tools" / "data" / "processed" / "llm_judge"
ARQUIVOS = {
    "A": "llm_judge_20261007_191141.json",
    "B": "llm_judge_20261007_221023.json",
    "C": "llm_judge_20261008_103408.json",
    "D": "llm_judge_20261007_224811.json",
}
PRELIMINAR = "llm_judge_20261006_215214.json"  # 42 perguntas da rodada preliminar (2026/2)
METRICAS = ["faithfulness", "answer_relevancy", "context_recall", "context_precision", "context_entity_recall"]
METRICAS_POR_ETAPA = {"A": METRICAS, "B": ["faithfulness", "answer_relevancy"], "C": METRICAS}
Z = 1.96


# ---------- primitivas estatísticas ----------
def cdf_normal(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def sinais_p(k, n):
    """Teste exato dos sinais, bicaudal, H0: p = 0,5."""
    if n == 0:
        return float("nan")
    m = max(k, n - k)
    cauda = sum(math.comb(n, i) for i in range(m, n + 1)) / 2 ** n
    return min(1.0, 2 * cauda)


def wilson(k, n, z=Z):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def cochran(N, e=0.05, p=0.5, z=Z):
    n0 = z * z * p * (1 - p) / (e * e)
    return n0, n0 / (1 + (n0 - 1) / N)


def margem_fpc(n, N, p=0.5, z=Z):
    return z * math.sqrt(p * (1 - p) / n * (N - n) / (N - 1))


def poder_mde(n, alpha=0.05, alvo=0.80):
    """Menor taxa verdadeira com poder >= alvo no teste exato dos sinais (bicaudal)."""
    kc = next(k for k in range(n // 2, n + 1)
              if 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n <= alpha)

    def poder(pi):
        return sum(math.comb(n, i) * pi ** i * (1 - pi) ** (n - i) for i in range(kc, n + 1))

    lo, hi = 0.5, 0.999
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if poder(mid) < alvo else (lo, mid)
    return kc, hi


def bootstrap_ic(d, B, rng):
    n = len(d)
    medias = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return medias[int(0.025 * B)], medias[int(0.975 * B) - 1]


def teste_normal_pareado(d):
    n = len(d)
    m = sum(d) / n
    s = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
    z = m / (s / math.sqrt(n))
    return m, s, z, 2 * (1 - cdf_normal(abs(z)))


def holm(pvals):
    """pvals: dict nome -> p bruto. Retorna lista ordenada (nome, p, limiar, p_ajustado, rejeita)."""
    m = len(pvals)
    ordem = sorted(pvals.items(), key=lambda kv: kv[1])
    out, prev, parar = [], 0.0, False
    for i, (nome, p) in enumerate(ordem, 1):
        lim = 0.05 / (m - i + 1)
        adj = min(1.0, max(prev, (m - i + 1) * p))
        prev = adj
        rej = (not parar) and p <= lim
        parar = parar or not rej
        out.append((nome, p, lim, adj, rej))
    return out


# ---------- leitura ----------
def carregar(etapa):
    return json.load(open(DADOS / ARQUIVOS[etapa], encoding="utf-8"))


def delta_ragas(q, metrica):
    """Δ por pergunta = média, entre os avaliadores disponíveis, de (condição 1 − condição 2)."""
    vals = []
    for ev in ("gpt", "gemini", "claude"):
        c = ((q.get("ragas_vs_judges") or {}).get(ev) or {}).get(metrica) or {}
        a, b = c.get("com"), c.get("sem")
        if a is not None and b is not None:
            vals.append(a - b)
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def contagens(resultados, ids=None):
    c = {"com_ontologia": 0, "sem_ontologia": 0, "ground_truth": 0, None: 0}
    for q in resultados:
        if ids is not None and q["question_id"] not in ids:
            continue
        c[q["consensus"]] = c.get(q["consensus"], 0) + 1
    return c


def pooled(resultados, ids=None):
    c = {"com_ontologia": 0, "sem_ontologia": 0}
    for q in resultados:
        if ids is not None and q["question_id"] not in ids:
            continue
        w = (q.get("pooled") or {}).get("consensus")
        if w in c:
            c[w] += 1
    return c


def longa_vence(resultados, ids=None, d_modo=False):
    k = n = 0
    for q in resultados:
        if ids is not None and q["question_id"] not in ids:
            continue
        w = q["consensus"]
        if w not in ("com_ontologia", "sem_ontologia", "ground_truth"):
            continue
        r = q["responses"]
        if not d_modo and w == "ground_truth":
            continue  # a referência do MedPT não entra na contagem de comprimento A–C
        lens = {s: len(r[s] or "") for s in r}
        outros = [s for s in lens if s != w and (d_modo or s != "ground_truth")]
        if not outros:
            continue
        mais_longa = max(lens[s] for s in lens if d_modo or s != "ground_truth")
        if sum(1 for s in lens if lens[s] == mais_longa and (d_modo or s != "ground_truth")) > 1:
            continue  # empate de comprimento
        n += 1
        k += lens[w] == mais_longa
    return k, n


# ---------- relatório ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--saida", default=None)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    out = {"parametros": {"bootstrap_B": a.boot, "semente": a.seed, "alpha": 0.05, "z": Z}}

    print("== 1. Amostra (Cochran)")
    n0, n = cochran(821)
    print(f"n0={n0:.2f}  n={n:.1f}  margem(262)={100*margem_fpc(262,821):.2f}%  margem(229)={100*margem_fpc(229,821):.2f}%")

    dados = {e: carregar(e) for e in "ABCD"}
    prel = {q["question_id"] for q in json.load(open(DADOS / PRELIMINAR, encoding="utf-8"))["results"]}
    print(f"perguntas da rodada preliminar encontradas no JSON: {len(prel)}")

    print("\n== 2. Juízes, consenso estrito (A–C): sinais + Wilson")
    pv = {}
    out["juizes"] = {}
    for e in "ABC":
        res = dados[e]["results"]
        c = contagens(res)
        s = dados[e]["summary"]["consensus_scores"]
        assert c["com_ontologia"] == s["com_ontologia"] and c["sem_ontologia"] == s["sem_ontologia"], f"divergência no resumo da etapa {e}"
        k, n_ = c["com_ontologia"], c["com_ontologia"] + c["sem_ontologia"]
        lo, hi = wilson(k, n_)
        p = sinais_p(k, n_)
        pv[f"Juízes {e}"] = p
        # sem as 42
        cs = contagens(res, ids={q["question_id"] for q in res} - prel)
        ks, ns = cs["com_ontologia"], cs["com_ontologia"] + cs["sem_ontologia"]
        ps = sinais_p(ks, ns)
        kc, mde = poder_mde(n_)
        print(f"{e}: {k}x{c['sem_ontologia']} (n={n_}; ref {c['ground_truth']}; sem consenso {c[None]})  taxa(1ª cond.)={100*k/n_:.1f}%  "
              f"Wilson[{100*lo:.1f};{100*hi:.1f}]  p={p:.3f} | sem as 42: {ks}x{cs['sem_ontologia']} taxa={100*ks/ns:.1f}% p={ps:.3f} "
              f"| poder80%: kc={kc} MDE={100*mde:.1f}%")
        out["juizes"][e] = dict(k=k, n=n_, outra=c["sem_ontologia"], ref=c["ground_truth"], sem_consenso=c[None], taxa=k / n_,
                                wilson=[lo, hi], p=p, sem42=dict(k=ks, n=ns, taxa=ks / ns, p=ps), poder=dict(kc=kc, mde=mde))
        kl, nl = longa_vence(res)
        print(f"   comprimento: resposta mais longa venceu {kl}/{nl}")
        pc = pooled(res)
        pp = sinais_p(pc["com_ontologia"], pc["com_ontologia"] + pc["sem_ontologia"])
        print(f"   contagem sem descarte: {pc['com_ontologia']}x{pc['sem_ontologia']}  p={pp:.3f}")
        out["juizes"][e]["comprimento"] = [kl, nl]
        out["juizes"][e]["sem_descarte"] = dict(**{"1": pc['com_ontologia'], "2": pc['sem_ontologia']}, p=pp)

    print("\n== 3. Etapa D (geradores; slots: com=Gemini, sem=GPT, ground_truth=Claude)")
    cd = contagens(dados["D"]["results"])
    dec = cd["com_ontologia"] + cd["sem_ontologia"] + cd["ground_truth"]
    lo, hi = wilson(cd["ground_truth"], dec)
    print(f"Claude {cd['ground_truth']}  Gemini {cd['com_ontologia']}  GPT {cd['sem_ontologia']}  sem consenso {cd[None]}  decididas={dec}  "
          f"Claude/decididas={100*cd['ground_truth']/dec:.1f}% Wilson[{100*lo:.1f};{100*hi:.1f}]  Claude/229={100*cd['ground_truth']/229:.1f}%")
    kl, nl = longa_vence(dados["D"]["results"], d_modo=True)
    print(f"   comprimento: resposta mais longa venceu {kl}/{nl}")
    pd_ = pooled(dados["D"]["results"])
    out["D"] = dict(counts={str(k): v for k, v in cd.items()}, decididas=dec, wilson=[lo, hi], comprimento=[kl, nl])

    print("\n== 4. RAGAS: Δ, bootstrap (IC95) e teste normal pareado")
    out["ragas"] = {}
    for e in "ABC":
        res = dados[e]["results"]
        for m in METRICAS_POR_ETAPA[e]:
            pares = [delta_ragas(q, m) for q in res]
            d = [x for x, nn in pares if x is not None]
            incompletos = sum(1 for x, nn in pares if x is not None and nn < 3)
            media, s, z, p = teste_normal_pareado(d)
            lo, hi = bootstrap_ic(d, a.boot, rng)
            # sem as 42
            d2 = [delta_ragas(q, m)[0] for q in res if q["question_id"] not in prel]
            d2 = [x for x in d2 if x is not None]
            m2 = sum(d2) / len(d2)
            pv[f"{e} {m}"] = p
            sig = "*" if (lo > 0 or hi < 0) else " "
            print(f"{e} {m:22s} n={len(d):3d} (<3 aval.: {incompletos:2d})  Δ={media:+.4f}  s_d={s:.4f}  z={z:+.2f}  p={p:.4f}  IC95[{lo:+.4f};{hi:+.4f}]{sig}  | sem as 42: Δ={m2:+.4f} (n={len(d2)})")
            out["ragas"][f"{e}/{m}"] = dict(n=len(d), incompletos=incompletos, delta=media, sd=s, z=z, p=p, ic=[lo, hi], sem42=m2)

    print("\n== 5. Holm (m = %d testes)" % len(pv))
    out["holm"] = []
    for nome, p, lim, adj, rej in holm(pv):
        print(f"{nome:36s} p={p:.4f}  limiar={lim:.4f}  p_aj={adj:.3f}  {'REJEITA' if rej else ''}")
        out["holm"].append(dict(teste=nome, p=p, limiar=lim, p_ajustado=adj, rejeita=rej))

    print("\n== 6. Qualidade dos votos dos juízes (inconsistência entre ordens)")
    out["inconsistencia"] = {}
    for e in "ABCD":
        q = dados[e]["summary"]["judge_vote_quality"]
        linha = {j: round(100 * v["order_inconsistency_rate"], 1) for j, v in q.items()}
        out["inconsistencia"][e] = linha
        print(e, linha)

    print("\n== 7. Divergência RAGAS × juízes (consenso estrito), por avaliador e métrica")
    out["divergencia"] = {}
    for e in "ABC":
        for ev, mets in dados[e]["summary"]["ragas_vs_judges"].items():
            for m, v in mets.items():
                if e == "B" and m not in METRICAS_POR_ETAPA["B"]:
                    continue
                den = v["agree"] + v["opposite"]
                taxa = v["opposite"] / den if den else float("nan")
                out["divergencia"][f"{e}/{ev}/{m}"] = dict(agree=v["agree"], opposite=v["opposite"], taxa=taxa)
        taxas = [x["taxa"] for k, x in out["divergencia"].items() if k.startswith(e + "/") and x["agree"] + x["opposite"] > 0]
        print(f"{e}: divergência mín={100*min(taxas):.1f}% máx={100*max(taxas):.1f}%  ({len(taxas)} combinações avaliador×métrica)")

    if a.saida:
        Path(a.saida).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nresultados gravados em {a.saida}")


if __name__ == "__main__":
    sys.exit(main())
