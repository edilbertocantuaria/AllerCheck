"""Etapa de coleta: para cada pergunta, UMA recuperação compartilhada + todas as respostas (POST /evaluate/arms).

Gera, por pergunta, as respostas: sem_g1, sem_g2 (piso de ruído), com_g1, h5_g1 (controle de contexto),
sem_gemini e sem_claude (matriz de geradores), todas a partir dos mesmos contextos de cada braço.

Seguro para rodar de novo: grava uma linha por pergunta em JSONL (append + fsync). Ao retomar, perguntas já
completas são puladas; as que tiveram erro numa resposta são refeitas. Para sozinho se houver falhas seguidas
ou erro de crédito/chave (nada de queimar dinheiro em loop).

Uso:  python scripts/collect_arms.py <selecao.json> <saida.jsonl> [pilot_20|sub_60|sub_100|all]
Env:  API_BASE_URL, COLLECT_CONCURRENCY, COLLECT_ARMS_TIMEOUT_SECONDS, COLLECT_MAX_CONSECUTIVE_FAILURES,
      RATE_MAX_ATTEMPTS, RATE_BACKOFF_BASE_S, RATE_BACKOFF_MAX_S
"""
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_config  # noqa: E402
from cost_guard import fatal_reason  # noqa: E402

GENERATIONS = [
    {"key": "sem_g1", "arm": "sem"},
    {"key": "sem_g2", "arm": "sem"},
    {"key": "com_g1", "arm": "com"},
    {"key": "h5_g1", "arm": "h5"},
    {"key": "sem_gemini", "arm": "sem", "provider": "gemini"},
    {"key": "sem_claude", "arm": "sem", "provider": "claude"},
]
MIN_ANSWER_CHARS = 50
BRT = timezone(timedelta(hours=-3))


def _load_questions(path: str, subset: str):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    qs = data["questions"] if isinstance(data, dict) else data
    if subset.startswith("first:"):  # ex.: first:10 = as 10 primeiras da ordem do sorteio (contidas em pilot_20, sub_60...)
        n = int(subset.split(":", 1)[1])
        qs = sorted(qs, key=lambda q: q["sample_order"])[:n]
    elif subset != "all":
        qs = [q for q in qs if subset in q.get("subsets", [])]
        if not qs:
            print(f"❌ Subconjunto '{subset}' vazio ou inexistente no arquivo.")
            sys.exit(1)
    return qs


def _read_done(out: Path) -> dict:
    done = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["question_id"]] = rec  # a última linha vence
    return done


def _complete(rec: dict) -> bool:
    if rec.get("status") in ("ok", "emergency", "out_of_scope"):
        return True
    return False


def _validate(res: dict) -> tuple[bool, str]:
    if res.get("error"):
        return False, f"api: {res['error']}"
    if res.get("emergency"):
        return True, "emergency"
    if not res.get("is_in_scope", True):
        return True, "out_of_scope"
    bad = [k for k, a in res.get("answers", {}).items() if a.get("error") or len(a.get("answer_eval") or "") < MIN_ANSWER_CHARS]
    missing = [g["key"] for g in GENERATIONS if g["key"] not in res.get("answers", {})]
    if bad or missing:
        return False, f"respostas com erro/curtas: {bad}; ausentes: {missing}"
    return True, "ok"


async def _one(client, url, q, attempts, base, cap, timeout):
    body = {"question": q["question"], "use_hyde": True, "arms": ["sem", "com", "h5"], "generations": GENERATIONS}
    last = None
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        try:
            r = await client.post(f"{url}/evaluate/arms", json=body, timeout=timeout)
            text = r.text
            reason = fatal_reason(text)
            if reason:
                return None, {"fatal": reason, "detail": text[:300]}
            if r.status_code == 200:
                res = r.json()
                ok, why = _validate(res)
                return {"res": res, "ok": ok, "why": why, "seconds": round(time.monotonic() - t0, 1), "attempt": attempt}, None
            last = f"HTTP {r.status_code}: {text[:200]}"
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < attempts:
            await asyncio.sleep(min(base * 2 ** (attempt - 1), cap) * (0.75 + random.random() * 0.5))
    return {"res": {"error": last}, "ok": False, "why": last, "seconds": 0, "attempt": attempts}, None


async def main(selection: str, out_path: str, subset: str):
    url = eval_config.require("API_BASE_URL").rstrip("/")
    conc = eval_config.require_int("COLLECT_CONCURRENCY")
    timeout = eval_config.require_int("COLLECT_ARMS_TIMEOUT_SECONDS")
    max_fail = eval_config.require_int("COLLECT_MAX_CONSECUTIVE_FAILURES")
    attempts = eval_config.require_int("RATE_MAX_ATTEMPTS")
    base = eval_config.require_float("RATE_BACKOFF_BASE_S")
    cap = eval_config.require_float("RATE_BACKOFF_MAX_S")

    questions = _load_questions(selection, subset)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = _read_done(out)
    todo = [q for q in questions if not _complete(done.get(q["question_id"], {}))]
    print(f"Coleta '{subset}': {len(questions)} perguntas, {len(questions) - len(todo)} já completas, {len(todo)} a fazer; concorrência {conc}.")

    async with httpx.AsyncClient() as probe:
        try:
            r = await probe.get(f"{url}/docs", timeout=10)
            print(f"API respondeu ({r.status_code}).")
        except Exception as e:
            print(f"❌ API inacessível em {url}: {e}. Nada foi gasto.")
            sys.exit(1)

    sem = asyncio.Semaphore(conc)
    lock = asyncio.Lock()
    state = {"consecutive": 0, "abort": None, "ok": 0, "bad": 0, "n": 0}
    fh = out.open("a", encoding="utf-8")

    async def work(client, q):
        if state["abort"]:
            return
        async with sem:
            if state["abort"]:
                return
            got, fatal = await _one(client, url, q, attempts, base, cap, timeout)
            async with lock:
                if fatal:
                    state["abort"] = f"erro fatal: {fatal['fatal']} ({fatal['detail']})"
                    return
                status = got["why"] if got["ok"] else "error"
                rec = {
                    "question_id": q["question_id"], "question": q["question"], "ground_truth": q["answer"],
                    "status": status if got["ok"] else "error", "why": got["why"],
                    "seconds": got["seconds"], "attempt": got["attempt"],
                    "collected_at": datetime.now(BRT).isoformat(timespec="seconds"), "result": got["res"],
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                state["n"] += 1
                if got["ok"]:
                    state["ok"] += 1
                    state["consecutive"] = 0
                else:
                    state["bad"] += 1
                    state["consecutive"] += 1
                    print(f"   ⚠️  Q{q['question_id']}: {got['why'][:160]}")
                    if state["consecutive"] >= max_fail:
                        state["abort"] = f"{state['consecutive']} falhas seguidas (última: {got['why'][:120]})"
                if state["n"] % 10 == 0:
                    print(f"   … {state['n']}/{len(todo)} (ok {state['ok']}, falhas {state['bad']})")

    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[work(client, q) for q in todo])
    fh.close()

    final = _read_done(out)
    wanted = {q["question_id"] for q in questions}
    complete = sum(1 for qid in wanted if _complete(final.get(qid, {})))
    kinds = {}
    for qid in wanted:
        s = final.get(qid, {}).get("status", "pendente")
        kinds[s] = kinds.get(s, 0) + 1
    print(f"\nResumo: {complete}/{len(wanted)} completas em {time.monotonic() - t0:.0f}s; por status: {kinds}")
    if state["abort"]:
        print(f"❌ ABORTADO: {state['abort']}. Rode de novo para retomar (as completas são puladas).")
        sys.exit(2)
    if complete < len(wanted):
        print("⚠️  Há perguntas pendentes/com erro: rode de novo para refazer só elas.")
        sys.exit(3)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "all"))
