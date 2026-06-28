import os
import sys
from pathlib import Path

from openai import OpenAI

from .asbai_prompt import ASBAI_EXTRACTION_INSTRUCTION
from .pdf_processor import load_pdf_full_text
from ..common import setup_logger, save_with_timestamp

DEFAULT_LONG_DOCUMENT_MODEL = "gpt-4o"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOOLS_ROOT = PROJECT_ROOT / "api" / "tools"
DEFAULT_PDF_PATH = TOOLS_ROOT / "data" / "raw" / "asbai" / "ALERGIA-PERGUNTAS-E-RESPOSTAS.pdf"
DEFAULT_OUTPUT_DIR = TOOLS_ROOT / "data" / "processed" / "asbai"


def _load_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY não configurada em variável de ambiente")
    return api_key


def analyze_asbai_pdf(
    pdf_path: Path | None = None,
    output_dir: Path | None = None,
    model: str | None = None
) -> dict[str, str | int]:
    logger = setup_logger("asbai_extract", DEFAULT_OUTPUT_DIR)

    selected_pdf = pdf_path or DEFAULT_PDF_PATH
    selected_output_dir = output_dir or DEFAULT_OUTPUT_DIR

    logger.info(f"Iniciando análise de {selected_pdf.name}")

    full_text, page_count = load_pdf_full_text(selected_pdf)

    selected_model = model or os.getenv("ASBAI_LONG_DOCUMENT_MODEL", DEFAULT_LONG_DOCUMENT_MODEL)
    api_key = _load_openai_api_key()

    logger.info(f"Enviando conteúdo para {selected_model}...")
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=selected_model,
        temperature=0,
        top_p=1,
        seed=42,
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um assistente clínico especializado em extração estruturada de protocolos. "
                    "Responda somente com a tabela em Markdown e o resumo final em 3 frases."
                ),
            },
            {
                "role": "user",
                "content": ASBAI_EXTRACTION_INSTRUCTION,
            },
            {
                "role": "user",
                "content": (
                    "Conteúdo integral do PDF para análise total (sem resumo, sem cortes):\n\n"
                    f"{full_text}"
                ),
            },
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("O modelo retornou uma resposta vazia.")

    logger.info("Resposta do modelo recebida")

    result = {
        "model": selected_model,
        "pdf_path": str(selected_pdf),
        "pages_processed": page_count,
        "characters_sent": len(full_text),
        "content": content,
    }

    output_path = save_with_timestamp(
        {"analysis": content, "metadata": result},
        selected_output_dir,
        "asbai_sinteses",
        "json"
    )

    md_path = selected_output_dir / output_path.name.replace(".json", ".md")
    md_path.write_text(content, encoding="utf-8")

    logger.info(f"✅ Análise salva em {output_path}")
    return result


if __name__ == "__main__":
    analyze_asbai_pdf()
