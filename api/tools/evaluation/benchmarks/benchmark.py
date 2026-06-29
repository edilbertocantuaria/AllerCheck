import asyncio
import os
import time
from pathlib import Path

import requests


try:
    from dotenv import load_dotenv
    _env = Path(__file__).resolve().parents[3] / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass


# def get_config() -> dict:
#     return {
#         "base_url":     os.environ.get("SLM_BASE_URL", "http://localhost:11434"),
#         "models":       [m.strip() for m in os.environ.get("BENCHMARK_MODELS", "mistral").split(",") if m.strip()],
#         "timeout":      int(os.environ.get("BENCHMARK_TIMEOUT", "240")),
#         "temperature":  float(os.environ.get("BENCHMARK_TEMPERATURE", "0.2")),
#         "test_question": os.environ.get(
#             "BENCHMARK_QUESTION",
#             "Qual é o medicamento paracetamol e para que serve?"
#         ),
#         "test_context": os.environ.get(
#             "BENCHMARK_CONTEXT",
#             "O paracetamol é um medicamento analgésico e antipirético amplamente utilizado, "
#             "pertencente à classe dos analgésicos não-opioides.",
#         ),
#     }

def get_config() -> dict:
    try:
        from dotenv import load_dotenv
        _env = Path(__file__).resolve().parents[3] / ".env"
        if _env.exists():
            load_dotenv(_env)
    except ImportError:
        pass

    return {
        "base_url":      os.environ.get("SLM_BASE_URL", "http://localhost:11434"),
        "models":        [m.strip() for m in os.environ.get("BENCHMARK_MODELS", "qwen2.5:7b,mistral:latest,neural-chat:latest,phi:latest,qwen3.5:4b").split(",") if m.strip()],
        "timeout":       int(os.environ.get("BENCHMARK_TIMEOUT", "240")),
        "temperature":   float(os.environ.get("BENCHMARK_TEMPERATURE", "0.2")),
        "test_question": os.environ.get("BENCHMARK_QUESTION", "Qual é o medicamento paracetamol e para que serve?"),
        "test_context":  os.environ.get(
            "BENCHMARK_CONTEXT",
            "O paracetamol é um medicamento analgésico e antipirético amplamente utilizado, "
            "pertencente à classe dos analgésicos não-opioides.",
        ),
    }

def list_models(base_url: str) -> list[str]:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


async def test_model(model: str, config: dict) -> dict:
    prompt = f"Contexto:\n{config['test_context']}\n\nPergunta: {config['test_question']}\n\nResposta:"
    start  = time.perf_counter()

    try:
        r = requests.post(
            f"{config['base_url']}/api/generate",
            json={
                "model":       model,
                "prompt":      prompt,
                "stream":      False,
                "temperature": config["temperature"],
            },
            timeout=config["timeout"],
        )
        elapsed = (time.perf_counter() - start) * 1000

        if r.status_code != 200:
            return {"model": model, "status": "error", "latency_ms": elapsed, "error": f"HTTP {r.status_code}"}

        answer = r.json().get("response", "").strip()
        return {
            "model":          model,
            "status":         "ok",
            "latency_ms":     round(elapsed, 2),
            "tokens_input":   len(prompt) // 4,
            "tokens_output":  len(answer) // 4,
            "answer":         answer,
            "answer_preview": answer[:120] + "..." if len(answer) > 120 else answer,
            "error":          None,
        }

    except requests.Timeout:
        elapsed = (time.perf_counter() - start) * 1000
        return {"model": model, "status": "timeout", "latency_ms": elapsed, "error": f"Timeout após {config['timeout']}s"}
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return {"model": model, "status": "error", "latency_ms": elapsed, "error": str(e)}


async def run_benchmark(config: dict) -> list[dict]:
    print(f"URL Ollama        : {config['base_url']}")
    print(f"Timeout por modelo: {config['timeout']}s")
    print(f"Modelos a testar  : {config['models']}\n")

    try:
        requests.get(f"{config['base_url']}/api/tags", timeout=5)
    except Exception as e:
        print(f"Ollama indisponível: {e}")
        return []

    available = list_models(config["base_url"])
    print(f"Modelos instalados: {available}\n")

    results = []
    for model in config["models"]:
        print(f"Testando {model}...")
        result = await test_model(model, config)
        results.append(result)

        if result["status"] == "ok":
            print(f"  ✅ OK ({result['latency_ms']:.0f}ms)")
        elif result["status"] == "timeout":
            print(f"  ⏱️  TIMEOUT ({result['latency_ms']:.0f}ms)")
        else:
            print(f"  ❌ ERRO ({result['error']})")

    return results