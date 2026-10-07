"""Checkpoint de execução: grava respostas coletadas e itens já avaliados, para retomar sem refazer (nem pagar de novo)."""

import json
import os
from pathlib import Path

VERSION = 1
CONDITIONS = ("com_ontologia", "sem_ontologia")


class CheckpointMismatch(Exception):
    pass


class Checkpoint:
    def __init__(self, path, params, data=None):
        self.path = Path(path)
        self.params = params
        self.data = data or {
            "version": VERSION,
            "params": params,
            "collected": {},
            "evaluated": {cond: {} for cond in CONDITIONS},
        }

    @classmethod
    def create(cls, path, params):
        cp = cls(path, params)
        cp.save()
        return cp

    @classmethod
    def resume(cls, path, params):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != VERSION:
            raise CheckpointMismatch(f"versão de checkpoint incompatível: {data.get('version')}")
        saved = data.get("params", {})
        diffs = [
            f"{key}: checkpoint={saved.get(key)!r} atual={params.get(key)!r}"
            for key in sorted(set(saved) | set(params))
            if saved.get(key) != params.get(key)
        ]
        if diffs:
            raise CheckpointMismatch("parâmetros diferentes do checkpoint (" + "; ".join(diffs) + ")")
        return cls(path, params, data)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def get_collected(self, question_id):
        entry = self.data["collected"].get(str(question_id))
        return (entry["com_ontologia"], entry["sem_ontologia"]) if entry else None

    def record_collected(self, question_id, item_com, item_sem):
        self.data["collected"][str(question_id)] = {"com_ontologia": item_com, "sem_ontologia": item_sem}
        self.save()

    def get_evaluated(self, condition, question_id):
        """Item avaliado sem erro total (itens com `errors` são refeitos na retomada)."""
        item = self.data["evaluated"][condition].get(str(question_id))
        return item if item is not None and not item.get("errors") else None

    def record_evaluated(self, condition, score_item):
        self.data["evaluated"][condition][str(score_item.get("question_id"))] = score_item
        self.save()

    def counts(self):
        return {
            "coletadas": len(self.data["collected"]),
            **{cond: sum(1 for it in items.values() if not it.get("errors")) for cond, items in self.data["evaluated"].items()},
        }
