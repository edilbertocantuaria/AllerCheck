import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from .extract import analyze_asbai_pdf


def main():
    try:
        result = analyze_asbai_pdf()
        print(f"\n✅ Pipeline ASBAI completado!")
        print(f"   Modelo: {result['model']}")
        print(f"   Páginas: {result['pages_processed']}")
        return 0
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
