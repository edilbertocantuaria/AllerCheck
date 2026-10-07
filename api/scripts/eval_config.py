"""Configuração do pipeline de avaliação, lida do .env. Sem fallback: variável ausente aborta com mensagem clara."""

import os
import sys
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def load_env():
    """Carrega o .env da raiz do projeto (no container as variáveis já vêm do docker-compose)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_ENV_FILE)


_loaded = False


def require(name):
    global _loaded
    if not _loaded:
        _loaded = True
        load_env()
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        print(f"❌ Variável obrigatória ausente no .env: {name} (veja .env.example). Nada foi executado.", file=sys.stderr)
        sys.exit(1)
    return value.strip()


def require_float(name):
    raw = require(name)
    try:
        return float(raw)
    except ValueError:
        print(f"❌ {name} deve ser numérico (valor atual: {raw!r}).", file=sys.stderr)
        sys.exit(1)


def require_int(name):
    return int(require_float(name))


def ragas_models():
    """Modelos dos avaliadores RAGAS (mesmas variáveis que o evaluator.py usa)."""
    return {
        "gpt": require("OPENAI_LLM_MODEL"),
        "gemini": require("GEMINI_LLM_MODEL"),
        "claude": require("CLAUDE_MODEL"),
    }


def judge_models():
    return {
        "gpt": require("JUDGE_GPT_MODEL"),
        "gemini": require("JUDGE_GEMINI_MODEL"),
        "claude": require("JUDGE_CLAUDE_MODEL"),
    }


def judge_temperature():
    return require_float("JUDGE_TEMPERATURE")


def judge_max_tokens():
    return require_int("JUDGE_MAX_TOKENS")


def tie_epsilon():
    """Banda de empate por métrica na Definição A."""
    return {
        "faithfulness": require_float("TIE_EPSILON_FAITHFULNESS"),
        "answer_relevancy": require_float("TIE_EPSILON_ANSWER_RELEVANCY"),
        "context_recall": require_float("TIE_EPSILON_CONTEXT_RECALL"),
        "context_precision": require_float("TIE_EPSILON_CONTEXT_PRECISION"),
        "context_entity_recall": require_float("TIE_EPSILON_CONTEXT_ENTITY_RECALL"),
    }


def ragas_timeout_seconds():
    return require_int("RAGAS_TIMEOUT_SECONDS")


def ragas_collection_timeout_seconds():
    return require_int("RAGAS_COLLECTION_TIMEOUT_SECONDS")


def preflight_timeout_seconds():
    return require_int("PREFLIGHT_TIMEOUT_SECONDS")


def preflight_models():
    """Todos os (provedor, modelo) que a execução vai usar: avaliadores RAGAS e juízes, sem repetir."""
    pairs = []
    for models in (ragas_models(), judge_models()):
        for provider, model in models.items():
            if (provider, model) not in pairs:
                pairs.append((provider, model))
    return pairs


def cost_per_item_usd():
    """Custo estimado em US$ por item avaliado (5 métricas), por avaliador RAGAS."""
    return {
        "gpt": require_float("EST_COST_PER_ITEM_USD_GPT"),
        "gemini": require_float("EST_COST_PER_ITEM_USD_GEMINI"),
        "claude": require_float("EST_COST_PER_ITEM_USD_CLAUDE"),
    }


def max_estimated_cost_usd():
    return require_float("MAX_ESTIMATED_COST_USD")
