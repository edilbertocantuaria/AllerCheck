import json
from pathlib import Path

import click


def filter_ragas_output(input_file: Path, output_file: Path) -> None:
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    filtered = {
        "generated_at": data["generated_at"],
        "sample_count": data["sample_count"],
        "models": data["models"],
        "evaluators": data["evaluators"],
        "seed": data.get("seed"),
        "metrics": data.get("metrics", {}),
        "summary": data.get("summary", {}),
        "scores": [
            {
                "question_id": score["question_id"],
                "results": score.get("results", {}),
                "errors": score.get("errors", []),
            }
            for score in data.get("scores", [])
        ],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    click.echo(f"✓ Filtered {len(filtered['scores'])} scores")
    click.echo(f"✓ Saved to {output_file}")


@click.command()
@click.option("--input", required=True, type=click.Path(exists=True), help="Input JSON file")
@click.option("--output", required=True, type=click.Path(), help="Output JSON file")
def main(input: str, output: str) -> None:
    filter_ragas_output(Path(input), Path(output))


if __name__ == "__main__":
    main()
