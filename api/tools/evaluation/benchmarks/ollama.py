import asyncio
import json
import sys
from pathlib import Path

# Carrega .env antes de qualquer import do projeto
try:
    from dotenv import load_dotenv
    _env = Path(__file__).resolve().parents[3] / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

from .benchmark import get_config, run_benchmark
from ..ragas.helpers import get_iso_timestamp

TOOLS_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = TOOLS_ROOT / "data" / "processed" / "evaluation"


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = get_config()

    print("=" * 70)
    print("  Ollama Benchmark")
    print("=" * 70)
    print()

    results = await run_benchmark(config)

    if results:
        timestamp = get_iso_timestamp().replace(":", "").replace("-", "")[:15]
        output_file = OUTPUT_DIR / f"{timestamp}_ollama_benchmark.json"

        output_data = {
            "timestamp": get_iso_timestamp(),
            "config": {
                "base_url":    config["base_url"],
                "temperature": config["temperature"],
                "timeout":     config["timeout"],
            },
            "results": results,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print()
        print(f"✅ Benchmark salvo em: {output_file}")
        return 0
    else:
        print("\n❌ Nenhum modelo foi testado")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))