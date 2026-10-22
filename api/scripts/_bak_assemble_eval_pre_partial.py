"""Monta, a partir da coleta por braços (+ RAGAS por unidades), os arquivos `evaluation_*.json` que o juiz lê.

O juiz compara 3 textos nos "slots" ground_truth / com_ontologia / sem_ontologia. Cada comparação é uma
atribuição de respostas coletadas a esses slots; o arquivo registra a atribuição em `comparison.slots`
(o relatório deve sempre traduzir os rótulos do slot para o que ele representa nesta comparação).

  A  ontologia   com_ontologia := com_g1       sem_ontologia := sem_g1        ground_truth := GT real
  B  ruído       com_ontologia := sem_g2       sem_ontologia := sem_g1        ground_truth := GT real
  C  contexto    com_ontologia := com_g1       sem_ontologia := h5_g1         ground_truth := GT real
  D  geradores   com_ontologia := sem_gemini   sem_ontologia := sem_g1 (gpt)  ground_truth := sem_claude (SEM GT)

Uso: python scripts/assemble_eval.py <coleta.jsonl> <A|B|C|D> --out-dir <dir> [--ragas a.jsonl,b.jsonl] [--ids ...] [--require-ragas]
Gera também `selected_<modo>_<ts>.json` com os ids incluídos (segundo argumento do juiz é o evaluation_*.json).
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BRT = timezone(timedelta(hours=-3))

MODES = {
    "A": {"name": "A · COM vs SEM ontologia (+ GT)", "slots": {"com_ontologia": "com_g1", "sem_ontologia": "sem_g1", "ground_truth": None}},
    "B": {"name": "B · piso de ruído: SEM g2 vs SEM g1 (+ GT)", "slots": {"com_ontologia": "sem_g2", "sem_ontologia": "sem_g1", "ground_truth": None}},
    "C": {"name": "C · controle de contexto: COM vs H5 (+ GT)", "slots": {"com_ontologia": "com_g1", "sem_ontologia": "h5_g1", "ground_truth": None}},
    "D": {"name": "D · geradores gemini vs gpt vs claude (sem GT)", "slots": {"com_ontologia": "sem_gemini", "sem_ontologia": "sem_g1", "ground_truth": "sem_claude"}},
}
NEEDS_RAGAS = {"A", "B", "C"}


def load_collection(path):
    recs = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["question_id"]] = r
    return {q: r for q, r in recs.items() if r.get("status") == "ok"}


def load_ragas(paths):
    units = {}
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if "_params" in row:
                    continue
                if not row.get("errors"):
                    units[row["unit_id"]] = row
    return units


def merged_results(units, qid, arm, key):
    """results[avaliador][métrica] = contexto do braço + resposta; None se faltar alguma unidade."""
    ctx = units.get(f"{qid}|ctx|{arm}")
    ans = units.get(f"{qid}|ans|{key}")
    if ctx is None or ans is None:
        return None
    out = {}
    for row in (ctx, ans):
        for ev, metrics in row["results"].items():
            out.setdefault(ev, {}).update(metrics)
    return out


def build_item(rec, key, units, use_gt_text_from=None):
    res = rec["result"]
    ans = res["answers"][key]
    arm = ans["arm"]
    return {
        "question_id": rec["question_id"],
        "question": rec["question"],
        "ground_truth": rec["ground_truth"],
        "answer": ans["answer_eval"],
        "answer_key": key,
        "arm": arm,
        "contexts": [c["content"] for c in res["arms"][arm]["chunks"]],
        "ontology_expansion": res.get("ontology_expansion", []),
        "ontology_chunks_added": res["arms"][arm].get("ontology_chunks_added", 0),
        "results": merged_results(units, rec["question_id"], arm, key) or {},
        "evaluator_errors": [],
        "errors": [],
    }


def main(a):
    mode = MODES[a.mode]
    recs = load_collection(a.collected)
    units = load_ragas([p for p in a.ragas.split(",") if p]) if a.ragas else {}
    keys = {s: k for s, k in mode["slots"].items() if k}
    if a.ids:
        wanted = {int(x) for x in a.ids.split(",")}
        recs = {q: r for q, r in recs.items() if q in wanted}

    items_com, items_sem, skipped = [], [], {}
    for qid, rec in sorted(recs.items()):
        answers = rec["result"].get("answers", {})
        if any(k not in answers or (answers[k].get("error") or len(answers[k].get("answer_eval") or "") < 50) for k in keys.values()):
            skipped[qid] = "resposta ausente/curta"
            continue
        com = build_item(rec, mode["slots"]["com_ontologia"], units)
        sem = build_item(rec, mode["slots"]["sem_ontologia"], units)
        if a.mode in NEEDS_RAGAS and a.require_ragas and not (com["results"] and sem["results"]):
            skipped[qid] = "sem RAGAS completo"
            continue
        if mode["slots"]["ground_truth"]:  # D: o slot ground_truth recebe uma resposta de gerador
            gen = build_item(rec, mode["slots"]["ground_truth"], units)
            com["real_ground_truth"] = com["ground_truth"]
            com["ground_truth"] = gen["answer"]
        items_com.append(com)
        items_sem.append(sem)

    if not items_com:
        print("❌ Nenhuma pergunta elegível; nada gravado.")
        sys.exit(1)

    ts = datetime.now(BRT).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(BRT).isoformat(),
        "comparison": {"mode": a.mode, "name": mode["name"], "slots": mode["slots"],
                       "note": "ground_truth=null nos slots significa o gabarito real do dataset"},
        "run_config": {"collected": Path(a.collected).name, "ragas_files": [Path(p).name for p in a.ragas.split(",") if p] if a.ragas else [],
                       "require_ragas": a.require_ragas},
        "skipped": skipped,
        "conditions": [
            {"name": "com_ontologia", "items": items_com, "evaluated_count": len(items_com)},
            {"name": "sem_ontologia", "items": items_sem, "evaluated_count": len(items_sem)},
        ],
    }
    out = out_dir / f"evaluation_{a.mode}_{ts}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sel = out_dir / f"selected_{a.mode}_{ts}.json"
    sel.write_text(json.dumps({"metadata": {"mode": a.mode, "total_questions": len(items_com)},
                               "questions": [{"question_id": i["question_id"], "question": i["question"]} for i in items_com]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    with_r = sum(1 for i in items_com if i["results"] and items_sem[items_com.index(i)]["results"])
    print(f"✅ {mode['name']}: {len(items_com)} perguntas ({with_r} com RAGAS completo nos 2 slots), {len(skipped)} puladas {dict(list(skipped.items())[:5])}")
    print(f"   {out}\n   {sel}")
    print(f"   Juiz:  python scripts/llm_as_judge_test_local.py \"{sel}\" \"{out}\" 42")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("collected")
    ap.add_argument("mode", choices=sorted(MODES))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ragas", default="")
    ap.add_argument("--ids", default="")
    ap.add_argument("--require-ragas", action="store_true")
    main(ap.parse_args())
