from enum import StrEnum
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "templates"


class PromptKey(StrEnum):
    QUESTION_INIT      = "question_init.md"
    QUESTION_REWRITE   = "question_rewrite.md"
    QUESTION_TITLE     = "question_title.md"
    CLASSIFY_RISK      = "classify_risk.md"
    SAFETY_GATE        = "safety_gate.md"
    GROUNDING_CHECK    = "grounding_check.md"
    EMERGENCY_RESPONSE = "emergency_response.md"
    HYDE_PROMPT        = "hyde_prompt.md"
    RERANK_PROMPT      = "rerank_prompt.md"


def get_prompt(key: PromptKey) -> str:
    prompt_path = PROMPTS_DIR / key.value
    return prompt_path.read_text(encoding="utf-8").strip() + "\n"