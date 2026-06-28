import asyncio
import sys
from pathlib import Path

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
    from datetime import datetime
    return datetime.now().isoformat()
