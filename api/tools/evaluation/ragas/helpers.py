import asyncio
import json
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import anthropic
import click
import openai

ALL_METRICS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "context_entity_recall",
]

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_BRT = timezone(timedelta(hours=-3))


async def check_openai(api_key: str, model: str) -> bool:
    try:
        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=5,
            temperature=0,
        )
        return "ok" in (resp.choices[0].message.content or "").lower()
    except Exception as e:
        click.echo(f" ❌ {e}", err=True)
        return False


async def check_gemini(api_key: str, model: str) -> bool:
    try:
        client = openai.AsyncOpenAI(api_key=api_key, base_url=_GEMINI_BASE_URL)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=5,
            temperature=0,
        )
        return "ok" in (resp.choices[0].message.content or "").lower()
    except Exception as e:
        click.echo(f" ❌ {e}", err=True)
        return False


async def check_anthropic(api_key: str, model: str) -> bool:
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=5,
            messages=[{"role": "user", "content": "Reply with OK."}],
        )
        return "ok" in (resp.content[0].text or "").lower()
    except Exception as e:
        click.echo(f" ❌ {e}", err=True)
        return False


def step(step: str, tag: str, description: str) -> None:
    click.echo(f"[{step}] [{tag}] {description}...")


def abort(msg: str) -> None:
    click.echo(f"      [ERRO] {msg}\n", err=True)
    sys.exit(1)


def banner(title: str, width: int = 70) -> None:
    click.echo("\n" + "=" * width)
    click.echo(f"  {title}")
    click.echo("=" * width + "\n")


def get_iso_timestamp() -> str:
    return datetime.now(_BRT).isoformat(timespec="microseconds")


def load_xlsx_dataset(file_path: str, max_samples: int | None = None) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl é necessário. Instale com: pip install openpyxl")

    workbook = openpyxl.load_workbook(file_path)
    worksheet = workbook.active

    headers = [cell.value for cell in worksheet[1]]

    data = []
    for row in worksheet.iter_rows(min_row=2, values_only=True):
        row_dict = {headers[i]: row[i] for i in range(len(headers))}
        if any(v is not None for v in row_dict.values()):
            data.append(row_dict)

    if max_samples is not None and len(data) > max_samples:
        data = random.sample(data, max_samples)

    return data


def save_evaluation_dataset(data: list[dict[str, Any]], output_dir: str) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    file_path = output_path / f"dataset_{timestamp}.json"
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)


def save_evaluation_results(results: dict[str, Any], output_dir: str) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    file_path = output_path / f"ragas_evaluation_{timestamp}.json"
    payload = json.dumps(results, ensure_ascii=False, indent=2)
    file_path.write_text(payload, encoding="utf-8")
    (output_path / "ragas_evaluation_latest.json").write_text(payload, encoding="utf-8")
    return str(file_path)


def save_api_responses(responses: list[dict[str, Any]], output_dir: str) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(_BRT).strftime("%Y%m%d_%H%M%S")
    file_path = output_path / f"allercheck_answer_{timestamp}.json"
    file_path.write_text(json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path)
