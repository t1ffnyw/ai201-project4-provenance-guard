import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"
_SYSTEM_PROMPT = (
    "You assess whether text reads as human-written or AI-generated. "
    "Respond with only a single decimal number between 0 and 1 inclusive. "
    "0 means very likely human-written; 1 means very likely AI-generated."
)


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return Groq(api_key=api_key)


def _parse_score(raw: str) -> float:
    match = re.search(r"0(?:\.\d+)?|1(?:\.0+)?", raw.strip())
    if not match:
        raise ValueError(f"Could not parse score from model response: {raw!r}")
    score = float(match.group())
    return max(0.0, min(1.0, score))


def llm_classify(text: str) -> float:
    """Return 0-1 score: 0 = likely human, 1 = likely AI."""
    if not text or not text.strip():
        raise ValueError("text must be non-empty")

    client = _get_client()
    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
        max_tokens=16,
    )
    raw = response.choices[0].message.content or ""
    return _parse_score(raw)
