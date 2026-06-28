from pathlib import Path

import fitz


def load_pdf_full_text(pdf_path: Path) -> tuple[str, int]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF não encontrado: {pdf_path}")

    with fitz.open(pdf_path) as document:
        if document.page_count == 0:
            raise ValueError(f"PDF vazio: {pdf_path}")

        print(f"[1/3] Lendo PDF integralmente: {pdf_path.name} ({document.page_count} páginas)", flush=True)
        pages_content: list[str] = []
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True)
            pages_content.append(f"\n\n--- PÁGINA {page_number} ---\n{text}")
            print(f"  - página {page_number}/{document.page_count} processada", flush=True)

        full_text = "".join(pages_content).strip()
        print("[1/3] Leitura do PDF concluída.", flush=True)
        return full_text, document.page_count
