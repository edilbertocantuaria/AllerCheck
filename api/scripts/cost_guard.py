"""Proteções contra gasto perdido: checagem prévia dos provedores e parada imediata em erro de crédito/chave."""

import asyncio
import os
import sys

FATAL_MARKERS = (
    "credit balance is too low",
    "insufficient_quota",
    "exceeded your current quota",
    "invalid_api_key",
    "incorrect api key",
    "invalid x-api-key",
    "authentication_error",
    "api key not valid",
    "api_key_invalid",
)

PREFLIGHT_PROMPT = "Responda apenas: ok"


def fatal_reason(message):
    """Marcador de erro fatal (crédito esgotado, chave inválida) contido na mensagem, ou None."""
    text = (message or "").lower()
    return next((marker for marker in FATAL_MARKERS if marker in text), None)


class AbortSwitch:
    def __init__(self):
        self.reason = None

    @property
    def tripped(self):
        return self.reason is not None

    def trigger(self, reason):
        if self.reason is None:
            self.reason = reason


ABORT = AbortSwitch()


async def _ping_gpt(model):
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PREFLIGHT_PROMPT}],
        max_tokens=5,
        temperature=0,
    )


async def _ping_gemini(model):
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    await asyncio.to_thread(
        genai.GenerativeModel(model).generate_content,
        PREFLIGHT_PROMPT,
        generation_config={"max_output_tokens": 5, "temperature": 0},
    )


async def _ping_claude(model):
    from anthropic import Anthropic

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=5,
        temperature=0,
        messages=[{"role": "user", "content": PREFLIGHT_PROMPT}],
    )


PINGS = {"gpt": _ping_gpt, "gemini": _ping_gemini, "claude": _ping_claude}


async def preflight(pairs):
    """Uma chamada mínima por (provedor, modelo). Retorna {"provedor:modelo": None se ok, texto do erro se falhou}."""
    import eval_config

    timeout = eval_config.preflight_timeout_seconds()

    async def run(provider, model):
        try:
            await asyncio.wait_for(PINGS[provider](model), timeout)
            return f"{provider}:{model}", None
        except Exception as e:
            return f"{provider}:{model}", f"{type(e).__name__}: {str(e)[:200]}"

    return dict(await asyncio.gather(*[run(provider, model) for provider, model in pairs]))


def preflight_or_exit(pairs=None):
    import eval_config

    eval_config.load_env()
    pairs = pairs or eval_config.preflight_models()
    results = asyncio.run(preflight(pairs))
    failed = {name: error for name, error in results.items() if error}
    for name in results:
        print(f"   {'✅' if name not in failed else '❌'} {name}" + (f": {failed[name]}" if name in failed else ""))
    if failed:
        print("\n❌ Checagem prévia falhou; nada foi gasto além de uma chamada mínima por provedor. Corrija chave/crédito e rode de novo.")
        sys.exit(1)


def estimate_ragas_cost(items, evaluators):
    """Estimativa em US$ de avaliar `items` itens com os avaliadores dados. Retorna (total, por_avaliador)."""
    import eval_config

    per_item = eval_config.cost_per_item_usd()
    by_evaluator = {ev: round(items * per_item[ev], 2) for ev in evaluators}
    return round(sum(by_evaluator.values()), 2), by_evaluator


def check_budget_or_exit(items, evaluators, label="RAGAS"):
    """Imprime a estimativa e aborta antes de gastar se passar de MAX_ESTIMATED_COST_USD."""
    import eval_config

    total, by_evaluator = estimate_ragas_cost(items, evaluators)
    limit = eval_config.max_estimated_cost_usd()
    detail = ", ".join(f"{ev} US$ {value:.2f}" for ev, value in by_evaluator.items())
    print(f"   💰 Estimativa {label}: até {items} itens → ~US$ {total:.2f} ({detail}); limite MAX_ESTIMATED_COST_USD = US$ {limit:.2f}")
    if total > limit:
        print(f"❌ Estimativa acima do limite. Nada foi gasto. Reduza as questões, tire um avaliador ou aumente MAX_ESTIMATED_COST_USD no .env.")
        sys.exit(1)
    return total
