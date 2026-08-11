#!/usr/bin/env python3
"""
Teste isolado para Q20 - diagnosticar erro específico
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Carregar .env
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

os.chdir(str(Path(__file__).parent))

from tools.evaluation.ragas.helpers import load_xlsx_dataset


async def test_q20_only():
    """Testa apenas Q20 com ambas as condições"""
    import httpx
    import click

    # Carregar dataset e pegar apenas Q20
    questions = load_xlsx_dataset(
        "tools/data/raw/evaluation/filtred_alergia_medicamentos.xlsx",
        max_samples=30
    )

    # Q20 é o índice 19 (0-indexed)
    q20 = questions[19]

    print("="*100)
    print(f"TESTANDO Q20")
    print("="*100)
    print(f"Pergunta: {q20.get('question')}\n")

    async with httpx.AsyncClient(timeout=30) as client:
        # Teste COM ONTOLOGIA
        print("\n" + "="*100)
        print("COM ONTOLOGIA")
        print("="*100)
        payload_com = {
            "conversation_id": None,
            "question": q20.get("question"),
            "history": [],
            "use_hyde": False,
            "use_ontology": True
        }

        try:
            print(f"[1] POST /evaluate/detailed...")
            detailed_resp = await client.post(
                "http://localhost:8000/evaluate/detailed",
                json=payload_com,
            )
            print(f"    Status: {detailed_resp.status_code}")
            if detailed_resp.status_code == 200:
                detailed_data = detailed_resp.json()
                print(f"    Contextos: {len(detailed_data.get('chunks', []))} recuperados")
                print(f"    Ontologia: {detailed_data.get('ontology_expansion', [])}\n")
            else:
                print(f"    Erro: {detailed_resp.text}\n")

            print(f"[2] POST /chat (stream)...")
            async with client.stream("POST", "http://localhost:8000/chat", json=payload_com) as resp:
                resp.raise_for_status()
                chunks = []
                async for chunk in resp.aiter_text():
                    chunks.append(chunk)
                answer = "".join(chunks)
                print(f"    Status: {resp.status_code}")
                print(f"    Resposta length: {len(answer)}")
                print(f"    Resposta: {answer[:150]}...\n")
                print(f"✅ COM ONTOLOGIA: SUCCESS\n")

        except httpx.TimeoutException as e:
            print(f"❌ COM ONTOLOGIA: TIMEOUT")
            print(f"   {type(e).__name__}: {e}\n")
        except httpx.HTTPStatusError as e:
            print(f"❌ COM ONTOLOGIA: HTTP {e.response.status_code}")
            print(f"   {e.response.reason_phrase}")
            print(f"   Body: {e.response.text}\n")
        except httpx.HTTPError as e:
            print(f"❌ COM ONTOLOGIA: HTTP ERROR")
            print(f"   {type(e).__name__}: {e}\n")
        except Exception as e:
            print(f"❌ COM ONTOLOGIA: ERRO INESPERADO")
            print(f"   {type(e).__name__}: {e}\n")

        # Teste SEM ONTOLOGIA
        print("="*100)
        print("SEM ONTOLOGIA")
        print("="*100)
        payload_sem = {
            "conversation_id": None,
            "question": q20.get("question"),
            "history": [],
            "use_hyde": False,
            "use_ontology": False
        }

        try:
            print(f"[1] POST /evaluate/detailed...")
            detailed_resp = await client.post(
                "http://localhost:8000/evaluate/detailed",
                json=payload_sem,
            )
            print(f"    Status: {detailed_resp.status_code}")
            if detailed_resp.status_code == 200:
                detailed_data = detailed_resp.json()
                print(f"    Contextos: {len(detailed_data.get('chunks', []))} recuperados")
                print(f"    Ontologia: {detailed_data.get('ontology_expansion', [])}\n")
            else:
                print(f"    Erro: {detailed_resp.text}\n")

            print(f"[2] POST /chat (stream)...")
            async with client.stream("POST", "http://localhost:8000/chat", json=payload_sem) as resp:
                resp.raise_for_status()
                chunks = []
                async for chunk in resp.aiter_text():
                    chunks.append(chunk)
                answer = "".join(chunks)
                print(f"    Status: {resp.status_code}")
                print(f"    Resposta length: {len(answer)}")
                print(f"    Resposta: {answer[:150]}...\n")
                print(f"✅ SEM ONTOLOGIA: SUCCESS\n")

        except httpx.TimeoutException as e:
            print(f"❌ SEM ONTOLOGIA: TIMEOUT")
            print(f"   {type(e).__name__}: {e}\n")
        except httpx.HTTPStatusError as e:
            print(f"❌ SEM ONTOLOGIA: HTTP {e.response.status_code}")
            print(f"   {e.response.reason_phrase}")
            print(f"   Body: {e.response.text}\n")
        except httpx.HTTPError as e:
            print(f"❌ SEM ONTOLOGIA: HTTP ERROR")
            print(f"   {type(e).__name__}: {e}\n")
        except Exception as e:
            print(f"❌ SEM ONTOLOGIA: ERRO INESPERADO")
            print(f"   {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    print("\n🔍 Diagnosticando Q20 com captura detalhada de erros...\n")
    try:
        asyncio.run(test_q20_only())
    except Exception as e:
        print(f"Erro fatal: {e}")
        import traceback
        traceback.print_exc()
