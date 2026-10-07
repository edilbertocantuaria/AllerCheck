"""RAGAS sobre a coleta por braços (collect_arms.py), sem pagar nada duas vezes.

Métricas de CONTEXTO (context_precision/recall/entity_recall) dependem só da pergunta, do gabarito e dos
contextos: são calculadas 1x por (pergunta, braço). Métricas de RESPOSTA (faithfulness/answer_relevancy)
são calculadas 1x por (pergunta, resposta), contra os contextos do braço que gerou a resposta.

Cada "unidade" fica numa linha do JSONL de saída (append + fsync); ao retomar, unidades sem erro são puladas.

Uso (no host, a partir de api/):
  python scripts/ragas_arms.py <coleta.jsonl> <saida.jsonl> --arms sem,com --keys sem_g1,com_g1 \
         --evaluators gpt,gemini,claude [--limit N] [--ids 1,2,3] [--yes]
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import eval_config
from cost_guard import ABORT, check_budget_or_exit, fatal_reason, preflight

api_root = Path(__file__).resolve().parent.parent
eval_config.load_env()
os.chdir(str(api_root))
sys.path.insert(0, str(api_root))

BRT = timezone(timedelta(hours=-3))
CTX_METRICS = ("context_precision", "context_recall", "context_entity_recall")
ANS_METRICS = ("faithfulness", "answer_relevancy")
CTX_SHARE, ANS_SHARE = 0.6, 0.4  # fração do custo "por item (5 métricas)" de cada tipo de unidade (estimativa; o piloto calibra)


def read_collection(path):
    recs = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["question_id"]] = r
    return {qid: r for qid, r in recs.items() if r.get("status") == "ok"}


def read_units(path):
    done, params = {}, None
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if "_params" in row:
                params = row["_params"]
            else:
                done[row["unit_id"]] = row
    return params, done


def unit_id(qid, kind, name):
    return f"{qid}|{kind}|{name}"


def contexts_of(rec, arm):
    return [c["content"] for c in rec["result"]["arms"][arm]["chunks"]]


def plan_units(recs, arms, keys):
    units = []
    for qid, rec in sorted(recs.items()):
        for arm in arms:
            units.append((qid, "ctx", arm))
        for key in keys:
            units.append((qid, "ans", key))
    return units


async def run_unit(evaluator, rec, kind, name):
    errors = []
    kw = {"_errors": errors, "_fatal_check": fatal_reason}
    clean = evaluator._sanitize
    question, gt = clean(rec["question"]), clean(rec["ground_truth"])
    if kind == "ctx":
        ctxs = [clean(c) for c in contexts_of(rec, name)]
        cp, cr, cer = await asyncio.gather(
            evaluator.evaluate_context_precision(question, ctxs, gt, **kw),
            evaluator.evaluate_context_recall(question, ctxs, gt, **kw),
            evaluator.evaluate_context_entity_recall(ctxs, gt, **kw),
        )
        by_metric = {"context_precision": cp, "context_recall": cr, "context_entity_recall": cer}
    else:
        ans = rec["result"]["answers"][name]
        ctxs = [clean(c) for c in contexts_of(rec, ans["arm"])]
        answer = clean(ans["answer_eval"])
        fa, ar = await asyncio.gather(
            evaluator.evaluate_faithfulness(question, answer, ctxs, **kw),
            evaluator.evaluate_answer_relevancy(question, answer, **kw),
        )
        by_metric = {"faithfulness": fa, "answer_relevancy": ar}
    evs = sorted({ev for scores in by_metric.values() for ev in scores})
    results = {ev: {m: scores.get(ev) for m, scores in by_metric.items()} for ev in evs}
    return results, errors


async def main(args):
    evaluators = [e for e in args.evaluators.split(",") if e]
    arms = [a for a in args.arms.split(",") if a]
    keys = [k for k in args.keys.split(",") if k]
    unit_conc = eval_config.require_int("RAGAS_UNIT_CONCURRENCY")
    unit_timeout = eval_config.require_int("RAGAS_UNIT_TIMEOUT_SECONDS")
    max_bad = eval_config.require_int("RAGAS_MAX_CONSECUTIVE_UNIT_ERRORS")

    recs = read_collection(args.collected)
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",")}
        recs = {q: r for q, r in recs.items() if q in wanted}
    if args.limit:
        recs = dict(list(sorted(recs.items()))[: args.limit])
    for key in keys:
        bad = [q for q, r in recs.items() if key not in r["result"]["answers"]]
        if bad:
            print(f"❌ Resposta '{key}' ausente na coleta de {len(bad)} perguntas (ex.: {bad[:3]}). Nada foi gasto.")
            sys.exit(1)

    models = eval_config.ragas_models()
    params = {"collected": Path(args.collected).name, "arms": arms, "keys": keys,
              "evaluators": sorted(evaluators), "models": {e: models[e] for e in sorted(evaluators)},
              "temperature": os.environ["EVALUATOR_TEMPERATURE"]}
    out = Path(args.out)
    saved_params, done = read_units(out)
    if saved_params is not None and saved_params != params:
        diffs = [f"{k}: salvo={saved_params.get(k)!r} atual={params.get(k)!r}" for k in sorted(set(saved_params) | set(params)) if saved_params.get(k) != params.get(k)]
        print("❌ Parâmetros diferentes do arquivo de saída existente: " + "; ".join(diffs))
        sys.exit(1)

    units = plan_units(recs, arms, keys)
    todo = [u for u in units if (u_id := unit_id(*u)) not in done or done[u_id].get("errors")]
    n_ctx = sum(1 for u in todo if u[1] == "ctx")
    n_ans = len(todo) - n_ctx
    print(f"{len(recs)} perguntas; {len(units)} unidades ({len(units) - len(todo)} já prontas, {len(todo)} a fazer: {n_ctx} de contexto, {n_ans} de resposta).")
    if not todo:
        print("Nada a fazer.")
        return
    check_budget_or_exit(round(n_ctx * CTX_SHARE + n_ans * ANS_SHARE, 1), evaluators, label=f"RAGAS {Path(args.out).name}")
    if not args.yes and sys.stdin.isatty():
        if input("Continuar? [s/N] ").strip().lower() not in ("s", "sim", "y"):
            print("Cancelado, nada foi gasto.")
            return
    print("🔎 Checagem prévia (1 chamada mínima por avaliador)...")
    pre = await preflight([(e, models[e]) for e in evaluators])
    for name, err in pre.items():
        print(f"   {'✅' if not err else '❌'} {name}" + (f": {err}" if err else ""))
    if any(pre.values()):
        print("❌ Checagem prévia falhou; nada foi avaliado. Corrija chave/crédito e rode de novo.")
        sys.exit(1)

    from tools.evaluation.ragas.evaluator import RagasEvaluator
    from tools.evaluation.ragas.rate_limit import all_summaries  # mesmo módulo que o evaluator usa (mesmos limitadores)

    evaluator = RagasEvaluator(evaluators=evaluators)
    out.parent.mkdir(parents=True, exist_ok=True)
    fh = out.open("a", encoding="utf-8")
    if saved_params is None:
        fh.write(json.dumps({"_params": params}, ensure_ascii=False) + "\n")
        fh.flush()

    sem, lock = asyncio.Semaphore(unit_conc), asyncio.Lock()
    st = {"n": 0, "bad": 0, "consec": 0}
    t0 = time.monotonic()

    async def work(u):
        qid, kind, name = u
        async with sem:
            if ABORT.tripped:
                return
            row = {"unit_id": unit_id(*u), "question_id": qid, "kind": kind, "name": name,
                   "arm": name if kind == "ctx" else recs[qid]["result"]["answers"][name]["arm"],
                   "results": {}, "errors": [], "at": datetime.now(BRT).isoformat(timespec="seconds")}
            try:
                results, errors = await asyncio.wait_for(run_unit(evaluator, recs[qid], kind, name), unit_timeout)
                row["results"], row["errors"] = results, errors
                if not any(v is not None for m in results.values() for v in m.values()):
                    row["errors"].append({"evaluator": "*", "metric": "*", "error": "nenhum valor retornado"})
            except Exception as e:
                full = f"{type(e).__name__}: {e}"
                marker = fatal_reason(full)
                if marker:
                    ABORT.trigger(marker)
                row["errors"].append({"evaluator": "*", "metric": "*", "error": full[:600]})
        async with lock:
            if ABORT.tripped and row["errors"] and fatal_reason(json.dumps(row["errors"])):
                return  # unidade perdida por erro fatal: não grava, será refeita
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            st["n"] += 1
            if row["errors"]:
                st["bad"] += 1
                st["consec"] += 1
                print(f"   ⚠️  {row['unit_id']}: {row['errors'][0]['evaluator']}/{row['errors'][0]['metric']}: {row['errors'][0]['error'][:140]}")
                if st["consec"] >= max_bad:
                    ABORT.trigger(f"{st['consec']} unidades seguidas com erro")
            else:
                st["consec"] = 0
            if st["n"] % 20 == 0:
                print(f"   … {st['n']}/{len(todo)} unidades ({st['bad']} com erro), {time.monotonic() - t0:.0f}s")

    await asyncio.gather(*[work(u) for u in todo])
    fh.close()
    print(f"\nConcluído: {st['n']}/{len(todo)} unidades gravadas, {st['bad']} com erro, {time.monotonic() - t0:.0f}s.")
    for line in all_summaries():
        print(f"   ⏱️  {line}")
    if ABORT.tripped:
        print(f"❌ ABORTADO: {ABORT.reason}. Rode o mesmo comando para retomar (unidades prontas são puladas).")
        sys.exit(2)
    if st["bad"]:
        print("⚠️  Unidades com erro serão refeitas ao rodar de novo.")
        sys.exit(3)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("collected")
    ap.add_argument("out")
    ap.add_argument("--arms", default="")
    ap.add_argument("--keys", default="")
    ap.add_argument("--evaluators", default="gpt,gemini,claude")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="")
    ap.add_argument("--yes", action="store_true")
    asyncio.run(main(ap.parse_args()))
