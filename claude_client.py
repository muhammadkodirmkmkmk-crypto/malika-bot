import requests
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from system_prompt import SYSTEM_PROMPT

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def ask_malika(history: list[dict]) -> str:
    """history — список {"role": "user"|"assistant", "content": str},
    может включать служебные сообщения role="user" с пометкой [SYSTEM NOTE]
    (например, посчитанный системой ежемесячный платёж)."""
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
            "system": SYSTEM_PROMPT,
            "messages": history,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(parts).strip()
