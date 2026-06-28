import re
from pathlib import Path
from typing import Any

import httpx

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from .utils import get_iso_timestamp


def _strip_citation_flag(text: str) -> str:
    return re.sub(
        r'^\[CITATION_REQUIRED:\s*(true|false)\]\s*\n?',
        '',
        text.strip(),
        flags=re.IGNORECASE,
    ).strip()


_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')


def _sanitize(text: str) -> str:
    return _CONTROL_CHARS_RE.sub('', text).strip()


def _parse_answer(raw: str) -> str:
    text = _strip_citation_flag(raw)
    fonte_match = re.search(r'\n\nFonte:\n', text, flags=re.IGNORECASE)
    if fonte_match:
        text = text[:fonte_match.start()].strip()
    return _sanitize(text)


async def _collect_chunks(
    client: httpx.AsyncClient,
    api_base_url: str,
    payload: dict,
    headers: dict,
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> list[str]:
    import asyncio

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(
                f"{api_base_url}/evaluate/chunks",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            chunks = [c["content"] for c in data.get("chunks", [])]
            total = data.get("total_chunks", 0)
            if chunks:
                print(f"    [OK] {total} chunk(s) recuperado(s)")
            else:
                print("    [AVISO] Nenhum chunk recuperado")
            return chunks

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print("    [AVISO] /evaluate/chunks não encontrado (404)")
                return []
            if attempt == max_retries:
                print(f"    [ERRO] HTTP {e.response.status_code} após {max_retries} tentativas")
                raise
            wait = backoff_base ** attempt
            print(f"    [RETRY] HTTP {e.response.status_code} — tentativa {attempt}/{max_retries}, aguardando {wait:.0f}s...")
            await asyncio.sleep(wait)

        except Exception as e:
            if attempt == max_retries:
                print(f"    [ERRO] Falha ao recuperar chunks após {max_retries} tentativas: {e}")
                raise
            wait = backoff_base ** attempt
            print(f"    [RETRY] {type(e).__name__} — tentativa {attempt}/{max_retries}, aguardando {wait:.0f}s...")
            await asyncio.sleep(wait)

    return []


_MIN_ANSWER_LENGTH = 50


async def _collect_chat(
    client: httpx.AsyncClient,
    api_base_url: str,
    payload: dict,
    headers: dict,
) -> str | None:
    chunks: list[str] = []
    async with client.stream("POST", f"{api_base_url}/chat", json=payload, headers=headers) as resp:
        resp.raise_for_status()
        async for chunk in resp.aiter_text():
            chunks.append(chunk)
    answer = _parse_answer("".join(chunks))
    if len(answer) < _MIN_ANSWER_LENGTH:
        print(f"    [AVISO] Resposta suspeita após sanitização ({len(answer)} chars) — descartando item.")
        return None
    return answer


async def collect_api_responses(
    questions: list[dict[str, Any]],
    api_base_url: str = "http://localhost:8000",
    jwt_token: str | None = None,
    timeout: int = 30,
    use_hyde: bool = True,
) -> list[dict[str, Any]]:
    results = []
    headers = {"Authorization": f"Bearer {jwt_token}"} if jwt_token else {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for idx, item in enumerate(questions, 1):
            question = item.get("question", "")
            ground_truth = item.get("answer", "")

            if not question:
                print(f"[AVISO] Pergunta {idx} vazia, pulando...")
                continue

            print(f"[COLLECT] Coletando resposta {idx}/{len(questions)}: {question[:50]}... (use_hyde={use_hyde})")

            payload = {"conversation_id": None, "question": question, "history": [], "use_hyde": use_hyde}

            try:
                detailed_resp = await client.post(
                    f"{api_base_url}/evaluate/detailed",
                    json=payload,
                    headers=headers,
                )
                detailed_data = detailed_resp.json() if detailed_resp.status_code == 200 else {}
                
                contexts = [c.get("content") for c in detailed_data.get("chunks", [])] if detailed_data.get("chunks") else []
                clean_answer = await _collect_chat(client, api_base_url, payload, headers)

                results.append({
                    "question_id":         idx,
                    "question":            question,
                    "question_rewrite":    detailed_data.get("question_rewrite"),
                    "hyde_reformulation":  detailed_data.get("hyde_reformulation"),
                    "answer":              clean_answer,
                    "ground_truth":        ground_truth,
                    "contexts":            contexts,
                    "collected_at":        get_iso_timestamp(),
                })
                print(f"[OK] Resposta {idx} coletada com sucesso")

            except httpx.HTTPError as e:
                print(f"[ERRO] Erro HTTP na pergunta {idx}: {e}")
                results.append({
                    "question_id":  idx,
                    "question":     question,
                    "answer":       None,
                    "ground_truth": ground_truth,
                    "contexts":     [],
                    "error":        str(e),
                    "collected_at": get_iso_timestamp(),
                })
            except Exception as e:
                print(f"[ERRO] Erro inesperado na pergunta {idx}: {e}")
                results.append({
                    "question_id":  idx,
                    "question":     question,
                    "answer":       None,
                    "ground_truth": ground_truth,
                    "contexts":     [],
                    "error":        str(e),
                    "collected_at": get_iso_timestamp(),
                })

    return results