import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from .benchmark import get_config, run_benchmark
from ...ragas.cli.helpers import get_iso_timestamp
from ...evaluation.ragas.cli.helpers import get_iso_timestamp

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOOLS_ROOT = PROJECT_ROOT / "api" / "tools"
OUTPUT_DIR = TOOLS_ROOT / "evaluation" / "benchmarks" / "results"


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = get_config()

    print("=" * 70)
    print("  Ollama Benchmark")
    print("=" * 70)
    print()

    results = await run_benchmark(config)

    if results:
        timestamp = get_iso_timestamp().replace(":", "").replace("-", "")
        output_file = OUTPUT_DIR / f"{timestamp}_ollama_benchmark.json"

        output_data = {
            "timestamp": get_iso_timestamp(),
            "config": {
                "base_url": config["base_url"],
                "temperature": config["temperature"],
                "timeout": config["timeout"],
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
