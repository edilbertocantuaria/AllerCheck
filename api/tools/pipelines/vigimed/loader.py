from pathlib import Path

import pandas as pd

ID_COL = "IDENTIFICACAO_NOTIFICACAO"

REACOES_COLS = [
    ID_COL,
    "REACAO_EVTO_ADVERSO_MEDDRA_LLT",
    "PT",
    "HLT",
    "HLGT",
    "SOC",
    "GRAVE",
    "GRAVIDADE",
    "DESFECHO",
]

MEDICAMENTOS_COLS = [
    ID_COL,
    "NOME_MEDICAMENTO_WHODRUG",
    "PRINCIPIOS_ATIVOS_WHODRUG",
    "ACAO_ADOTADA",
    "INDICACAO_MEDDRA",
    "INDICACAO_RELATADA_NOTIFICADOR_INICIAL",
]

NOTIFICACOES_COLS = [
    ID_COL,
    "REACAO_EVENTO_ADVERSO_MEDDRA",
    "GRAVE",
    "GRAVIDADE",
    "DESFECHO",
    "RELACAO_MEDICAMENTO_EVENTO",
]


def read_csv_with_encoding(path: Path, usecols: list[str]) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                path,
                sep=";",
                dtype=str,
                usecols=usecols,
                encoding=encoding,
                low_memory=False,
            )
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError("codec", b"", 0, 1, f"Não foi possível ler {path}")


def load_reacoes(path: Path) -> pd.DataFrame:
    return read_csv_with_encoding(path, REACOES_COLS)


def load_medicamentos(path: Path) -> pd.DataFrame:
    return read_csv_with_encoding(path, MEDICAMENTOS_COLS)


def load_notificacoes(path: Path) -> pd.DataFrame:
    return read_csv_with_encoding(path, NOTIFICACOES_COLS)
