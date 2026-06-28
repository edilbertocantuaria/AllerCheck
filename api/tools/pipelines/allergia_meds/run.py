import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pandas as pd
from ..common import setup_logger, save_with_timestamp


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOOLS_ROOT = PROJECT_ROOT / "api" / "tools"
RAW_DIR = TOOLS_ROOT / "data" / "raw" / "allergia_meds"
OUTPUT_DIR = TOOLS_ROOT / "data" / "processed" / "allergia_meds"


def sanitize_allergia_medicamentos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(how="all")

    df = df.drop_duplicates()

    df.columns = df.columns.str.strip()

    return df


def main():
    logger = setup_logger("allergia_meds", OUTPUT_DIR)

    try:
        logger.info("Iniciando pipeline Allergia Medicamentos")

        input_files = list(RAW_DIR.glob("alergia_medicamentos*.xlsx"))
        if not input_files:
            raise FileNotFoundError(f"Nenhum arquivo Excel encontrado em {RAW_DIR}")

        input_file = input_files[0]
        logger.info(f"Carregando: {input_file.name}")

        df = pd.read_excel(input_file)
        logger.info(f"  Linhas originais: {len(df)}")
        logger.info(f"  Colunas: {len(df.columns)}")

        logger.info("Sanitizando dados...")
        df = sanitize_allergia_medicamentos(df)
        logger.info(f"  Após sanitização: {len(df)} linhas")

        logger.info("Salvando resultado...")
        output_path = save_with_timestamp(
            df,
            OUTPUT_DIR,
            "alergia_medicamentos",
            "xlsx"
        )

        logger.info(f"✅ Pipeline Allergia Medicamentos concluído!")
        logger.info(f"   Arquivo: {output_path}")
        return 0

    except Exception as e:
        logger.error(f"Erro no pipeline: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
