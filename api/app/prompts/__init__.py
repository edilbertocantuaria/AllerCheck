from app.prompts.registry import PromptKey, get_prompt

QUESTION_INIT      = get_prompt(PromptKey.QUESTION_INIT)
QUESTION_REWRITE   = get_prompt(PromptKey.QUESTION_REWRITE)
QUESTION_TITLE     = get_prompt(PromptKey.QUESTION_TITLE)
CLASSIFY_RISK      = get_prompt(PromptKey.CLASSIFY_RISK)
SAFETY_GATE        = get_prompt(PromptKey.SAFETY_GATE)
GROUNDING_CHECK    = get_prompt(PromptKey.GROUNDING_CHECK)
EMERGENCY_RESPONSE = get_prompt(PromptKey.EMERGENCY_RESPONSE)

__all__ = [
    "PromptKey",
    "get_prompt",
    "QUESTION_INIT",
    "QUESTION_REWRITE",
    "QUESTION_TITLE",
    "CLASSIFY_RISK",
    "SAFETY_GATE",
    "GROUNDING_CHECK",
    "EMERGENCY_RESPONSE",
]