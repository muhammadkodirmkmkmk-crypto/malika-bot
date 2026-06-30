import requests
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from system_prompt import SYSTEM_PROMPT

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def ask_malika(history: list[dict], dynamic_addendum: str | None = None) -> str:
    """history — список {"role": "user"|"assistant", "content": str}.
    dynamic_addendum — короткая инструкция (например, фиксация языка),
    добавляется только к системному промпту этого запроса и никогда
    не попадает в историю диалога, чтобы модель не могла её процитировать."""
    system_text = SYSTEM_PROMPT
    if dynamic_addendum:
        system_text = f"{SYSTEM_PROMPT}\n\n[Текущая инструкция для этого ответа]\n{dynamic_addendum}"
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": 500,
            "system": system_text,
            "messages": history,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(parts).strip()
