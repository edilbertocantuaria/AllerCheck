import sys
import time
import os
from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Pinecone as PineconeVectorStore
from pinecone import ServerlessSpec

API_ROOT = Path(__file__).resolve().parents[1]

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import pinecone_client, INDEX_NAME
from app.logger import log_ingestion_audit
from ingestion.helpers import (
    INDEX_CLOUD,
    INDEX_DIMENSION,
    INDEX_METRIC,
    INDEX_REGION,
    build_current_manifest,
    build_ingestion_audit,
    delete_vectors_for_files,
    detect_manifest_changes,
    load_documents,
    load_previous_manifest,
    prepare_documents_source,
    print_audit_summary,
    print_stage,
    save_manifest,
    save_text_audit_log,
)


def recreate_index(index_name):
    indexes = pinecone_client.list_indexes().names()

    if index_name in indexes:
        pinecone_client.delete_index(index_name)

        while index_name in pinecone_client.list_indexes().names():
            time.sleep(1)

    pinecone_client.create_index(
        name=index_name,
        dimension=INDEX_DIMENSION,
        metric=INDEX_METRIC,
        spec=ServerlessSpec(
            cloud=INDEX_CLOUD,
            region=INDEX_REGION,
        ),
    )

    index = pinecone_client.Index(index_name)

    for _ in range(60):
        try:
            index.describe_index_stats()
            return index
        except Exception:
            time.sleep(2)

    raise TimeoutError(f"Index {index_name} was not ready after creation")


def get_or_create_index(index_name):
    indexes = pinecone_client.list_indexes().names()

    if index_name not in indexes:
        pinecone_client.create_index(
            name=index_name,
            dimension=INDEX_DIMENSION,
            metric=INDEX_METRIC,
            spec=ServerlessSpec(
                cloud=INDEX_CLOUD,
                region=INDEX_REGION,
            ),
        )

    index = pinecone_client.Index(index_name)

    for _ in range(60):
        try:
            index.describe_index_stats()
            return index
        except Exception:
            time.sleep(2)

    raise TimeoutError(f"Index {index_name} was not ready")


def ingest():
    total_steps = 11
    stage = 1

    print_stage(stage, total_steps, "Preparando origem dos documentos")
    source_info = prepare_documents_source()
    path = source_info["root_folder"]
    pdf_paths = source_info["pdf_paths"]
    print(
        f"[SOURCE] kind={source_info['kind']} | path={source_info['source_path']} | "
        f"pdfs={len(pdf_paths)}"
    )
    stage += 1

    print_stage(stage, total_steps, "Validando arquivos PDF da origem")
    print(f"[DISCOVERY] {len(pdf_paths)} PDF(s) encontrado(s)")
    stage += 1

    print_stage(stage, total_steps, "Lendo manifesto anterior")
    previous_manifest = load_previous_manifest()
    print(f"[MANIFEST] {len(previous_manifest)} item(ns) no manifesto anterior")
    stage += 1

    print_stage(stage, total_steps, "Calculando manifesto atual")
    current_manifest = build_current_manifest(pdf_paths, path)
    stage += 1

    print_stage(stage, total_steps, "Identificando delta de mudanças")
    changes = detect_manifest_changes(previous_manifest, current_manifest)
    print(
        "[CHANGES] "
        f"new={len(changes['new'])}, "
        f"updated={len(changes['updated'])}, "
        f"removed={len(changes['removed'])}, "
        f"unchanged={len(changes['unchanged'])}"
    )
    stage += 1

    print_stage(stage, total_steps, "Conectando ao Pinecone")
    force_recreate = os.getenv("INGEST_FORCE_RECREATE_INDEX", "false").strip().lower() in {"1", "true", "yes"}
    index = recreate_index(INDEX_NAME) if force_recreate else get_or_create_index(INDEX_NAME)
    before_stats = index.describe_index_stats()
    stage += 1

    print_stage(stage, total_steps, "Removendo vetores de arquivos atualizados/removidos")
    files_to_delete = sorted(set(changes["updated"] + changes["removed"]))

    if files_to_delete:
        delete_vectors_for_files(index, files_to_delete)
    else:
        print("[PINECONE-DELETE] Nenhum arquivo para remover")
    stage += 1

    print_stage(stage, total_steps, "Carregando documentos alterados")
    files_to_process = sorted(set(changes["new"] + changes["updated"]))
    processing_paths = [Path(path) / source_file for source_file in files_to_process]
    print(f"[PROCESS] {len(processing_paths)} arquivo(s) para ingestão")

    documents, failed_files, file_statuses = load_documents(processing_paths, path)
    print(f"[LOAD] Páginas válidas carregadas: {len(documents)}")
    stage += 1

    print_stage(stage, total_steps, "Gerando chunks")
    chunk_size = int(os.getenv("CHUNK_SIZE", "550"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "110"))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    chunks = splitter.split_documents(documents)
    print(f"[CHUNKS] Total de chunks gerados: {len(chunks)}")
    stage += 1

    print_stage(stage, total_steps, "Enviando chunks para Pinecone")
    if chunks:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

        PineconeVectorStore.from_documents(
            chunks,
            embeddings,
            index_name=INDEX_NAME,
        )
    else:
        print("[UPSERT] Nenhum chunk para enviar")
    stage += 1

    print_stage(stage, total_steps, "Atualizando manifesto e gerando auditoria")
    next_manifest = {
        source_file: metadata
        for source_file, metadata in previous_manifest.items()
        if source_file not in changes["removed"]
    }

    for source_file, status in file_statuses.items():
        if source_file in current_manifest:
            next_manifest[source_file] = {
                **current_manifest[source_file],
                **status,
            }

    for source_file in changes["unchanged"]:
        if source_file in current_manifest:
            next_manifest[source_file] = {
                **previous_manifest.get(source_file, {}),
                **current_manifest[source_file],
            }

    save_manifest(next_manifest)

    after_stats = index.describe_index_stats()
    vector_count = after_stats.get("total_vector_count", 0)

    audit_report = build_ingestion_audit(
        pdf_paths=pdf_paths,
        documents=documents,
        chunks=chunks,
        failed_files=failed_files,
        vector_count=vector_count,
        root_folder=path,
        source_info=source_info,
        changes=changes,
        pinecone_before=before_stats,
        pinecone_after=after_stats,
        files_to_process=files_to_process,
        files_to_delete=files_to_delete,
        index_name=INDEX_NAME,
        effective_manifest=next_manifest,
    )

    log_ingestion_audit(audit_report)
    summary_text = print_audit_summary(audit_report)
    text_log_path = save_text_audit_log(summary_text)

    stage += 1
    print_stage(stage, total_steps, "Finalizado")
    print("Indexação concluída")
    print("Auditoria salva em logs/ingestion_audit_latest.json e logs/ingestion_audit.jsonl")
    print(f"Resumo em texto salvo em: {text_log_path}")


if __name__ == "__main__":
    ingest()
