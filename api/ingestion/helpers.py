import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader

API_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCE_PATH = "docs/pdf_files"
SOURCE_PATH = os.getenv("INGEST_SOURCE_PATH", DEFAULT_SOURCE_PATH)
EXTRACT_FOLDER = "docs/ingested"
INDEX_DIMENSION = 3072
INDEX_METRIC = "cosine"
INDEX_CLOUD = "aws"
INDEX_REGION = "us-east-1"
INGESTION_MANIFEST_FILE = API_ROOT / "logs" / "ingestion_manifest.json"
INGESTION_TEXT_LOG_PATTERN = "ingestion_%Y%m%d_%H%M%S.txt"
BRASILIA_TZ = timezone(timedelta(hours=-3))


def print_stage(step, total, message):
    print(f"\n[{step}/{total}] {message}")


def print_item_progress(prefix, current, total, item_name):
    print(f"{prefix} {current}/{total} - {item_name}")


def brasilia_now():
    return datetime.now(timezone.utc).astimezone(BRASILIA_TZ)


def format_brasilia_datetime(value):
    return value.strftime("%Y-%m-%d %H:%M:%S")


def resolve_source_path():
    source = Path((SOURCE_PATH or DEFAULT_SOURCE_PATH).strip())

    if not source.is_absolute():
        source = API_ROOT / source

    return source.resolve()


def prepare_documents_source():
    source_path = resolve_source_path()
    force_extract = os.getenv("INGEST_FORCE_EXTRACT", "false").strip().lower() in {"1", "true", "yes"}

    if source_path.is_dir():
        return {
            "kind": "directory",
            "source_path": str(source_path),
            "root_folder": source_path,
            "pdf_paths": discover_pdf_paths(source_path),
        }

    if source_path.suffix.lower() == ".pdf":
        if not source_path.exists():
            raise FileNotFoundError(f"PDF file not found: {source_path}")

        return {
            "kind": "pdf",
            "source_path": str(source_path),
            "root_folder": source_path.parent,
            "pdf_paths": [source_path],
        }

    if source_path.suffix.lower() == ".zip":
        extract_path = Path(EXTRACT_FOLDER)

        if not extract_path.is_absolute():
            extract_path = API_ROOT / extract_path

        extract_path = extract_path.resolve()

        if extract_path.exists() and any(extract_path.iterdir()) and not force_extract:
            return {
                "kind": "zip",
                "source_path": str(source_path),
                "root_folder": extract_path,
                "pdf_paths": discover_pdf_paths(extract_path),
            }

        if force_extract and extract_path.exists():
            shutil.rmtree(extract_path)

        if not source_path.exists():
            raise FileNotFoundError(f"ZIP file not found: {source_path}")

        extract_path.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(source_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

        return {
            "kind": "zip",
            "source_path": str(source_path),
            "root_folder": extract_path,
            "pdf_paths": discover_pdf_paths(extract_path),
        }

    raise ValueError(
        "INGEST_SOURCE_PATH must point to a PDF file, ZIP file, or folder containing PDFs"
    )


def discover_pdf_paths(folder):
    return sorted(
        [path for path in Path(folder).rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"]
    )


def normalize_path(path_value):
    return str(Path(path_value).resolve()).lower()


def to_posix_relative(path_value, root_folder):
    return str(Path(path_value).resolve().relative_to(Path(root_folder).resolve())).replace("\\", "/")


def file_sha256(file_path):
    digest = hashlib.sha256()

    with Path(file_path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def load_previous_manifest():
    if not INGESTION_MANIFEST_FILE.exists():
        return {}

    with INGESTION_MANIFEST_FILE.open("r", encoding="utf-8") as handle:
        data = json.load(handle) or {}

    return data.get("files", {})


def save_manifest(files_manifest):
    INGESTION_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    now_brasilia = brasilia_now()

    payload = {
        "updated_at": format_brasilia_datetime(now_brasilia),
        "files": files_manifest,
    }

    with INGESTION_MANIFEST_FILE.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_current_manifest(pdf_paths, extracted_folder):
    manifest = {}
    total_files = len(pdf_paths)

    if total_files:
        print(f"[MANIFEST] Calculando hash de {total_files} arquivo(s)...")

    for index, path in enumerate(pdf_paths, start=1):
        resolved_path = Path(path).resolve()
        source_file = to_posix_relative(resolved_path, extracted_folder)
        print_item_progress("[MANIFEST]", index, total_files, source_file)
        stat = resolved_path.stat()
        manifest[source_file] = {
            "source_path": str(resolved_path),
            "sha256": file_sha256(resolved_path),
            "size": stat.st_size,
            "modified_at": int(stat.st_mtime),
        }

    return manifest


def detect_manifest_changes(previous_manifest, current_manifest):
    previous_files = set(previous_manifest.keys())
    current_files = set(current_manifest.keys())

    new_files = current_files - previous_files
    removed_files = previous_files - current_files
    intersection = previous_files & current_files

    updated_files = {
        source_file
        for source_file in intersection
        if previous_manifest[source_file].get("sha256") != current_manifest[source_file].get("sha256")
    }

    unchanged_files = intersection - updated_files

    return {
        "new": sorted(new_files),
        "updated": sorted(updated_files),
        "removed": sorted(removed_files),
        "unchanged": sorted(unchanged_files),
    }


def delete_vectors_for_files(index, source_files):
    total_files = len(source_files)

    for position, source_file in enumerate(source_files, start=1):
        print_item_progress("[PINECONE-DELETE]", position, total_files, source_file)
        try:
            index.delete(filter={"source_file": {"$eq": source_file}})
        except Exception as exc:
            if "Namespace not found" in str(exc):
                print("[PINECONE-DELETE] Namespace not found; skipping remaining deletions")
                break

            raise


def build_fallback_source_title(file_path):
    source_stem = Path(file_path).stem.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", source_stem).strip().title()


def build_source_title(file_path):
    normalized_stem = Path(file_path).stem.strip()
    normalized_stem = normalized_stem.replace("_", " ").replace("-", " ")
    normalized_stem = re.sub(r"\s+", " ", normalized_stem).strip()

    if not normalized_stem:
        return build_fallback_source_title(file_path)

    words = normalized_stem.split()
    acronyms = {"ASBAI", "ANVISA", "RAG", "CSV", "PDF", "LLT", "HLT", "HLGT", "SOC", "MEDDRA"}
    connectors = {"da", "do", "de", "das", "dos", "e", "em", "no", "na"}

    title_words = []
    for index, word in enumerate(words):
        clean = re.sub(r"[^A-Za-z0-9À-ÿ]", "", word).upper()
        if clean in acronyms:
            title_words.append(clean)
        elif word.lower() in connectors and index > 0:
            title_words.append(word.lower())
        else:
            title_words.append(word.capitalize())

    return " ".join(title_words)


def load_documents(pdf_paths, root_folder):
    documents = []
    failed_files = []
    file_statuses = {}

    total_files = len(pdf_paths)

    if total_files:
        print(f"[LOAD] Carregando {total_files} arquivo(s) para processamento...")

    for file_position, file_path in enumerate(pdf_paths, start=1):
        file_label = to_posix_relative(file_path, root_folder)
        print_item_progress("[LOAD]", file_position, total_files, file_label)

        try:
            loader = PyMuPDFLoader(str(file_path))
            pages = loader.load()
        except Exception as exc:
            failed_files.append(
                {
                    "source": build_source_title(file_path),
                    "source_file": to_posix_relative(file_path, root_folder),
                    "source_path": str(Path(file_path).resolve()),
                    "reason": str(exc),
                }
            )
            continue

        source = build_source_title(file_path)
        source_file = to_posix_relative(file_path, root_folder)
        source_path = str(Path(file_path).resolve())
        had_extractable_text = False

        for doc in pages:
            text = (doc.page_content or "").strip()

            if text:
                had_extractable_text = True
                doc.page_content = " ".join(text.split())
                doc.metadata["source"] = source
                doc.metadata["source_file"] = source_file
                doc.metadata["source_path"] = source_path
                documents.append(doc)

        file_statuses[source_file] = {
            "source": source,
            "source_path": source_path,
            "had_extractable_text": had_extractable_text,
        }

    return documents, failed_files, file_statuses


def summarize_pinecone_namespaces(index_stats):
    namespaces = index_stats.get("namespaces", {}) or {}

    return [
        {
            "namespace": namespace if namespace else "default",
            "vector_count": data.get("vector_count", 0),
        }
        for namespace, data in sorted(namespaces.items(), key=lambda item: item[0])
    ]


def build_ingestion_audit(
    pdf_paths,
    documents,
    chunks,
    failed_files,
    vector_count,
    root_folder,
    source_info,
    changes,
    pinecone_before,
    pinecone_after,
    files_to_process,
    files_to_delete,
    index_name,
    effective_manifest,
):
    discovered_files = [to_posix_relative(path, root_folder) for path in pdf_paths]
    expected_files = {normalize_path(path) for path in pdf_paths}

    used_files = sorted(
        source_file
        for source_file, metadata in effective_manifest.items()
        if metadata.get("had_extractable_text")
    )

    used_sources = sorted(
        {
            metadata.get("source", "unknown")
            for metadata in effective_manifest.values()
            if metadata.get("had_extractable_text") and metadata.get("source")
        }
    )

    used_file_paths = {
        normalize_path(metadata["source_path"])
        for metadata in effective_manifest.values()
        if metadata.get("had_extractable_text") and metadata.get("source_path")
    }

    failed_file_paths = {
        normalize_path(item["source_path"])
        for item in failed_files
        if item.get("source_path")
    }

    chunk_file_paths = [chunk.metadata.get("source_path", "unknown") for chunk in chunks]
    loaded_chunks = {
        normalize_path(source_path)
        for source_path in chunk_file_paths
        if source_path != "unknown"
    } or used_file_paths

    skipped_no_text_files = sorted(
        discovered_file
        for discovered_file in discovered_files
        if effective_manifest.get(discovered_file, {}).get("had_extractable_text") is False
        and normalize_path(Path(root_folder) / discovered_file) not in failed_file_paths
    )
    not_reprocessed_files = sorted(
        source_file
        for source_file in changes["unchanged"]
        if effective_manifest.get(source_file, {}).get("had_extractable_text") is True
    )

    missing_in_documents = sorted(
        to_posix_relative(path, root_folder)
        for path in pdf_paths
        if normalize_path(path) not in used_file_paths
    )
    missing_in_chunks = sorted(
        to_posix_relative(path, root_folder)
        for path in pdf_paths
        if normalize_path(path) not in loaded_chunks
    )
    docs_without_chunks = sorted(
        source
        for source in used_files
        if normalize_path(Path(root_folder) / source) not in loaded_chunks
    )

    chunks_per_file = Counter(chunk.metadata.get("source_file", "unknown") for chunk in chunks)

    return {
        "timestamp": format_brasilia_datetime(brasilia_now()),
        "source": {
            "kind": source_info["kind"],
            "path": source_info["source_path"],
        },
        "extracted_folder": str(Path(root_folder).resolve()),
        "index": {
            "name": index_name,
            "dimension": INDEX_DIMENSION,
            "metric": INDEX_METRIC,
            "cloud": INDEX_CLOUD,
            "region": INDEX_REGION,
            "total_vector_count": vector_count,
        },
        "pinecone_audit": {
            "before": {
                "total_vector_count": pinecone_before.get("total_vector_count", 0),
                "index_fullness": pinecone_before.get("index_fullness", 0),
                "namespaces": summarize_pinecone_namespaces(pinecone_before),
            },
            "after": {
                "total_vector_count": pinecone_after.get("total_vector_count", 0),
                "index_fullness": pinecone_after.get("index_fullness", 0),
                "namespaces": summarize_pinecone_namespaces(pinecone_after),
            },
            "delta_total_vectors": pinecone_after.get("total_vector_count", 0)
            - pinecone_before.get("total_vector_count", 0),
            "operations": {
                "files_deleted": len(files_to_delete),
                "files_reindexed": len(files_to_process),
                "chunks_upserted": len(chunks),
            },
        },
        "counts": {
            "expected_pdfs": len(expected_files),
            "pdfs_loaded_into_documents": len(used_file_paths),
            "pdfs_present_in_chunks": len(loaded_chunks),
            "total_pages_in_documents": len(documents),
            "total_chunks": len(chunks),
            "files_skipped_no_text": len(skipped_no_text_files),
            "files_with_loader_errors": len(failed_files),
            "files_not_reprocessed": len(not_reprocessed_files),
            "missing_in_documents": len(missing_in_documents),
            "missing_in_chunks": len(missing_in_chunks),
            "loaded_without_chunks": len(docs_without_chunks),
            "new_files": len(changes["new"]),
            "updated_files": len(changes["updated"]),
            "removed_files": len(changes["removed"]),
            "unchanged_files": len(changes["unchanged"]),
        },
        "files": {
            "discovered": discovered_files,
            "used": used_files,
            "used_sources": used_sources,
            "not_reprocessed": not_reprocessed_files,
            "skipped_no_text": skipped_no_text_files,
            "missing_in_documents": missing_in_documents,
            "missing_in_chunks": missing_in_chunks,
            "loaded_without_chunks": docs_without_chunks,
            "failed": failed_files,
            "changes": changes,
        },
        "chunks_per_file": [
            {"source_file": source, "chunk_count": count}
            for source, count in chunks_per_file.most_common()
        ],
    }


def print_audit_summary(audit_report):
    counts = audit_report["counts"]
    source = audit_report.get("source", {})
    source_kind = source.get("kind")
    source_path = source.get("path", "")

    if source_kind == "zip":
        source_header = f"ZIP source: {source_path}"
    elif source_kind == "pdf":
        source_header = f"PDF source: {source_path}"
    else:
        source_header = f"Documents source: {source_path}"

    lines = [
        source_header,
        f"Documents folder: {audit_report['extracted_folder']}",
        f"PDF files discovered: {counts['expected_pdfs']}",
        "\n\n=== COUNTS ===",
        f"Expected PDFs (source): {counts['expected_pdfs']}",
        f"PDFs loaded into documents: {counts['pdfs_loaded_into_documents']}",
        f"PDFs present in chunks: {counts['pdfs_present_in_chunks']}",
        f"\nTotal pages in documents: {counts['total_pages_in_documents']}",
        f"Total chunks: {counts['total_chunks']}",
        f"\nFiles skipped (no extractable text): {counts['files_skipped_no_text']}",
        f"Files with loader errors: {counts['files_with_loader_errors']}",
        f"Files not reprocessed in this run: {counts['files_not_reprocessed']}",
        f"\nNew files: {counts['new_files']}",
        f"Updated files: {counts['updated_files']}",
        f"Removed files: {counts['removed_files']}",
        f"Unchanged files: {counts['unchanged_files']}",
        f"Total vectors in Pinecone: {audit_report['index']['total_vector_count']}",
    ]

    changes = audit_report["files"].get("changes", {})

    lines.append("\n=== FILE CHANGES ===")

    lines.append("\nNew files:")
    if changes.get("new"):
        for source_file in changes["new"]:
            lines.append(f"- {source_file}")
    else:
        lines.append("- none")

    lines.append("\nUpdated files:")
    if changes.get("updated"):
        for source_file in changes["updated"]:
            lines.append(f"- {source_file}")
    else:
        lines.append("- none")

    lines.append("\nRemoved files:")
    if changes.get("removed"):
        for source_file in changes["removed"]:
            lines.append(f"- {source_file}")
    else:
        lines.append("- none")

    lines.append("\nUnchanged files:")
    if changes.get("unchanged"):
        for source_file in changes["unchanged"]:
            lines.append(f"- {source_file}")
    else:
        lines.append("- none")

    pinecone_audit = audit_report.get("pinecone_audit", {})
    pinecone_before = pinecone_audit.get("before", {})
    pinecone_after = pinecone_audit.get("after", {})
    pinecone_ops = pinecone_audit.get("operations", {})

    lines.append("\n=== PINECONE AUDIT ===")
    lines.append(f"Vectors before: {pinecone_before.get('total_vector_count', 0)}")
    lines.append(f"Vectors after: {pinecone_after.get('total_vector_count', 0)}")
    lines.append(f"Vector delta: {pinecone_audit.get('delta_total_vectors', 0)}")
    lines.append(f"Files deleted from index: {pinecone_ops.get('files_deleted', 0)}")
    lines.append(f"Files reindexed: {pinecone_ops.get('files_reindexed', 0)}")
    lines.append(f"Chunks upserted: {pinecone_ops.get('chunks_upserted', 0)}")

    lines.append("\nNamespaces before:")
    for item in pinecone_before.get("namespaces", []):
        lines.append(f"- {item['namespace']}: {item['vector_count']}")

    lines.append("\nNamespaces after:")
    for item in pinecone_after.get("namespaces", []):
        lines.append(f"- {item['namespace']}: {item['vector_count']}")

    lines.append("\n=== FILES USED ===")
    for source_file in audit_report["files"]["used"]:
        lines.append(f"- {source_file}")

    if audit_report["files"].get("not_reprocessed"):
        lines.append("\n=== FILES NOT REPROCESSED IN THIS RUN ===")
        for source in audit_report["files"]["not_reprocessed"]:
            lines.append(f"- {source}")

    if audit_report["files"]["skipped_no_text"]:
        lines.append("\n=== FILES SKIPPED (NO EXTRACTABLE TEXT) ===")
        for source in audit_report["files"]["skipped_no_text"]:
            lines.append(f"- {source}")

    if audit_report["files"]["failed"]:
        lines.append("\n=== LOADER FAILURES ===")
        for item in audit_report["files"]["failed"][:10]:
            lines.append(f"- {item['source_file']} -> {item['reason']}")

    lines.append("\n=== CHUNKS PER FILE ===")
    for item in audit_report["chunks_per_file"]:
        lines.append(f"{item['chunk_count']} - {item['source_file']}")

    for line in lines:
        print(line)

    return "\n".join(lines)


def save_text_audit_log(audit_text):
    logs_dir = API_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    now_brasilia = brasilia_now()

    log_path = logs_dir / now_brasilia.strftime(INGESTION_TEXT_LOG_PATTERN)
    header = f"Log gerado em: {format_brasilia_datetime(now_brasilia)} (America/Sao_Paulo, UTC-03:00)"

    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(header + "\n\n")
        handle.write(audit_text + "\n")

    return log_path
