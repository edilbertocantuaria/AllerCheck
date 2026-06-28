import pandas as pd

from .loader import ID_COL


def filter_allergy_reactions(reacoes: pd.DataFrame) -> pd.DataFrame:
    mask = reacoes["REACAO_EVTO_ADVERSO_MEDDRA_LLT"].fillna("").str.contains(
        r"alergia|alérgica", case=False, regex=True
    )
    return reacoes.loc[mask].copy()


def standardize_columns(reacoes: pd.DataFrame, notificacoes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    reacoes = reacoes.rename(
        columns={
            "GRAVE": "GRAVE_REACOES",
            "GRAVIDADE": "GRAVIDADE_REACOES",
            "DESFECHO": "DESFECHO_REACOES",
        }
    )
    notificacoes = notificacoes.rename(
        columns={
            "GRAVE": "GRAVE_NOTIFICACOES",
            "GRAVIDADE": "GRAVIDADE_NOTIFICACOES",
            "DESFECHO": "DESFECHO_NOTIFICACOES",
        }
    )
    return reacoes, notificacoes


def merge_datasets(reacoes: pd.DataFrame, medicamentos: pd.DataFrame, notificacoes: pd.DataFrame) -> pd.DataFrame:
    base = reacoes.merge(medicamentos, on=ID_COL, how="inner")
    base = base.merge(notificacoes, on=ID_COL, how="inner")
    return base
