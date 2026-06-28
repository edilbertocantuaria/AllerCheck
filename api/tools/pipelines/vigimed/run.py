import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ..common import setup_logger, save_with_timestamp
from .loader import load_reacoes, load_medicamentos, load_notificacoes
from .transform import filter_allergy_reactions, standardize_columns, merge_datasets

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOOLS_ROOT = PROJECT_ROOT / "api" / "tools"
RAW_DIR = TOOLS_ROOT / "data" / "raw" / "vigimed"
OUTPUT_DIR = TOOLS_ROOT / "data" / "processed" / "vigimed"


def main():
    logger = setup_logger("vigimed_etl", OUTPUT_DIR)

    try:
        logger.info("Iniciando pipeline VigiMed")

        logger.info("Carregando dados VigiMed...")
        reacoes = load_reacoes(RAW_DIR / "VigiMed_Reacoes.csv")
        medicamentos = load_medicamentos(RAW_DIR / "VigiMed_Medicamentos.csv")
        notificacoes = load_notificacoes(RAW_DIR / "VigiMed_Notificacoes.csv")

        logger.info(f"  Reações: {len(reacoes)} registros")
        logger.info(f"  Medicamentos: {len(medicamentos)} registros")
        logger.info(f"  Notificações: {len(notificacoes)} registros")

        logger.info("Filtrando reações de alergia...")
        reacoes = filter_allergy_reactions(reacoes)
        logger.info(f"  Após filtro: {len(reacoes)} registros")

        logger.info("Padronizando nomes de colunas...")
        reacoes, notificacoes = standardize_columns(reacoes, notificacoes)

        logger.info("Mesclando datasets...")
        base_rag = merge_datasets(reacoes, medicamentos, notificacoes)
        logger.info(f"  Base final: {len(base_rag)} registros com {len(base_rag.columns)} colunas")

        logger.info("Salvando resultado...")
        output_path = save_with_timestamp(
            base_rag,
            OUTPUT_DIR,
            "base_rag_alergia",
            "csv"
        )

        logger.info(f"✅ Pipeline VigiMed concluído!")
        logger.info(f"   Arquivo: {output_path}")
        return 0

    except Exception as e:
        logger.error(f"Erro no pipeline: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
