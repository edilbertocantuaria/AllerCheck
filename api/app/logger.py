import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("logs/rag_logs.jsonl")
INGESTION_AUDIT_LOG_FILE = Path("logs/ingestion_audit.jsonl")
INGESTION_AUDIT_LATEST_FILE = Path("logs/ingestion_audit_latest.json")

def log_query(question, sources, answer):

    LOG_FILE.parent.mkdir(exist_ok=True)

    record = {
        "timestamp": str(datetime.now()),
        "question": question,
        "sources": sources,
        "answer": answer
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def log_ingestion_audit(report):

    INGESTION_AUDIT_LOG_FILE.parent.mkdir(exist_ok=True)

    with open(INGESTION_AUDIT_LOG_FILE, "a", encoding="utf-8") as history_file:
        history_file.write(json.dumps(report, ensure_ascii=False) + "\n")

    with open(INGESTION_AUDIT_LATEST_FILE, "w", encoding="utf-8") as latest_file:
        json.dump(report, latest_file, ensure_ascii=False, indent=2)
