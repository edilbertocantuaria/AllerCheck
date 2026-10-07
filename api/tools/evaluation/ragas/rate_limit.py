"""Limitador de taxa por provedor para chamadas de LLM (RPM + concorrência + 429 com backoff).

Por que existe: o RAGAS e o juiz disparam muitas chamadas pequenas em paralelo. Sem controle, uma conta
recém-recarregada bate no limite de requisições por minuto, recebe 429 e a rodada falha (ou gasta
retentativas à toa). Aqui TODAS as chamadas HTTP de um provedor passam por um único limitador:

  - RPM: espaça as chamadas (intervalo mínimo = 60/RPM), sem rajadas.
  - Concorrência: no máximo N chamadas em voo por provedor.
  - 429/529/5xx: espera `retry-after` (ou backoff exponencial com jitter), reduz o ritmo e tenta de novo,
    até RATE_MAX_ATTEMPTS. Depois disso o erro sobe (e o cost_guard decide se aborta).

Uso: `limiter = get_limiter("anthropic"); wrap_openai_client(client, limiter)` ANTES de montar o
llm_factory/instructor (que guardam a referência do `create` já embrulhado).

Todas as configurações vêm do .env (sem valor padrão no código), como o resto da avaliação.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

PROVIDERS = ("openai", "gemini", "anthropic")


def _req(name: str) -> str:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        print(f"❌ Variável obrigatória ausente no .env: {name}")
        sys.exit(1)
    return v.strip()


def _req_int(name: str) -> int:
    try:
        v = int(_req(name))
    except ValueError:
        print(f"❌ {name} precisa ser inteiro (valor: {os.environ.get(name)!r})")
        sys.exit(1)
    if v <= 0:
        print(f"❌ {name} precisa ser > 0")
        sys.exit(1)
    return v


def _req_float(name: str) -> float:
    try:
        v = float(_req(name))
    except ValueError:
        print(f"❌ {name} precisa ser numérico (valor: {os.environ.get(name)!r})")
        sys.exit(1)
    if v <= 0:
        print(f"❌ {name} precisa ser > 0")
        sys.exit(1)
    return v


@dataclass
class LimiterStats:
    calls: int = 0
    retries: int = 0
    rate_limited: int = 0
    waited_s: float = 0.0
    failures: int = 0


class ProviderLimiter:
    def __init__(
        self,
        name: str,
        rpm: int,
        concurrency: int,
        max_attempts: int,
        backoff_base_s: float,
        backoff_max_s: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.name = name
        self.base_interval = 60.0 / rpm
        self.interval = self.base_interval
        self.concurrency = concurrency
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self._clock = clock
        self._sleep = sleep
        self._sem: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None
        self._next_slot = 0.0
        self._penalty_until = 0.0
        self._ok_streak = 0
        self.stats = LimiterStats()

    # os primitivos asyncio são criados sob demanda (dentro do loop em uso)
    def _prims(self) -> tuple[asyncio.Semaphore, asyncio.Lock]:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.concurrency)
            self._lock = asyncio.Lock()
        return self._sem, self._lock  # type: ignore[return-value]

    async def _pace(self) -> None:
        _, lock = self._prims()
        async with lock:
            now = self._clock()
            start = max(now, self._next_slot, self._penalty_until)
            self._next_slot = start + self.interval
            wait = start - now
        if wait > 0:
            self.stats.waited_s += wait
            await self._sleep(wait)

    @asynccontextmanager
    async def slot(self):
        sem, _ = self._prims()
        async with sem:
            await self._pace()
            self.stats.calls += 1
            yield

    def on_rate_limited(self, retry_after: float | None) -> float:
        """Registra um 429: pausa todos os chamadores e reduz o ritmo (até 4x mais lento)."""
        self.stats.rate_limited += 1
        self._ok_streak = 0
        pause = retry_after if retry_after is not None else self.backoff_base_s
        pause = min(max(pause, 0.5), self.backoff_max_s)
        self._penalty_until = max(self._penalty_until, self._clock() + pause)
        self.interval = min(self.interval * 1.5, self.base_interval * 4)
        return pause

    def on_success(self) -> None:
        """Depois de uma sequência de sucessos, volta gradualmente ao ritmo configurado."""
        self._ok_streak += 1
        if self._ok_streak >= 20 and self.interval > self.base_interval:
            self.interval = max(self.base_interval, self.interval / 1.25)
            self._ok_streak = 0

    def backoff(self, attempt: int) -> float:
        wait = min(self.backoff_base_s * (2 ** (attempt - 1)), self.backoff_max_s)
        return wait * (0.75 + random.random() * 0.5)

    def summary(self) -> str:
        s = self.stats
        return (
            f"{self.name}: {s.calls} chamadas, {s.rate_limited} limitadas (429), {s.retries} retentativas, "
            f"{s.failures} falhas, {s.waited_s:.0f}s esperando ritmo (RPM efetivo ≤ {60.0 / self.interval:.0f})"
        )


_LIMITERS: dict[str, ProviderLimiter] = {}


def get_limiter(provider: str) -> ProviderLimiter:
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider}")
    if provider not in _LIMITERS:
        tag = provider.upper()
        _LIMITERS[provider] = ProviderLimiter(
            provider,
            rpm=_req_int(f"RATE_RPM_{tag}"),
            concurrency=_req_int(f"RATE_CONC_{tag}"),
            max_attempts=_req_int("RATE_MAX_ATTEMPTS"),
            backoff_base_s=_req_float("RATE_BACKOFF_BASE_S"),
            backoff_max_s=_req_float("RATE_BACKOFF_MAX_S"),
        )
    return _LIMITERS[provider]


def reset_limiters() -> None:
    _LIMITERS.clear()


def all_summaries() -> list[str]:
    return [lim.summary() for lim in _LIMITERS.values()]


# ── classificação de erros ─────────────────────────────────────────────────────

def _status(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(exc, "response", None)
    v = getattr(resp, "status_code", None)
    return v if isinstance(v, int) else None


def retry_after_seconds(exc: BaseException) -> float | None:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers:
        for key in ("retry-after", "Retry-After"):
            try:
                v = headers.get(key)
            except Exception:
                v = None
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
    return None


# Erros que NÃO se resolvem esperando (crédito acabou, chave inválida). Importante: a OpenAI devolve
# "insufficient_quota" como HTTP 429, então a checagem de fatal vem ANTES da de rate limit.
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


def is_fatal(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in FATAL_MARKERS)


def is_rate_limit(exc: BaseException) -> bool:
    if is_fatal(exc):
        return False
    st = _status(exc)
    if st == 429:
        return True
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        "ratelimit" in name
        or "resourceexhausted" in name
        or "rate limit" in text
        or "rate_limit" in text
        or "too many requests" in text
        or "resource_exhausted" in text
    )


def is_transient(exc: BaseException) -> bool:
    """429, 5xx, 529 (overloaded) e quedas de conexão/timeout valem retentativa; 4xx de pedido e erros fatais, não."""
    if is_fatal(exc):
        return False
    if is_rate_limit(exc):
        return True
    st = _status(exc)
    if st is not None:
        return st >= 500
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "overloaded", "apiconnection"))


async def call_with_limits(limiter: ProviderLimiter, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Uma chamada paga, passando por RPM/concorrência, com retentativa para erros transitórios."""
    attempt = 0
    while True:
        attempt += 1
        try:
            async with limiter.slot():
                result = await fn(*args, **kwargs)
            limiter.on_success()
            return result
        except Exception as exc:
            if not is_transient(exc) or attempt >= limiter.max_attempts:
                limiter.stats.failures += 1
                raise
            limiter.stats.retries += 1
            if is_rate_limit(exc):
                wait = limiter.on_rate_limited(retry_after_seconds(exc))
            else:
                wait = limiter.backoff(attempt)
            await limiter._sleep(wait)


# ── embrulho dos clientes ──────────────────────────────────────────────────────

def _wrap_method(owner: Any, attr: str, limiter: ProviderLimiter) -> None:
    original = getattr(owner, attr)
    if getattr(original, "_rate_limited", False):
        return

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        return await call_with_limits(limiter, original, *args, **kwargs)

    wrapped._rate_limited = True  # type: ignore[attr-defined]
    setattr(owner, attr, wrapped)


def wrap_openai_client(client: Any, limiter: ProviderLimiter) -> Any:
    """AsyncOpenAI (também o cliente Gemini via endpoint compatível): chat.completions.create."""
    _wrap_method(client.chat.completions, "create", limiter)
    return client


def wrap_anthropic_client(client: Any, limiter: ProviderLimiter) -> Any:
    """anthropic.AsyncAnthropic: messages.create."""
    _wrap_method(client.messages, "create", limiter)
    return client
