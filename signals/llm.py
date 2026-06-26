import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_MODEL = "llama-3.3-70b-versatile"
_SYSTEM_PROMPT = (
    "You assess whether text reads as human-written or AI-generated. "
    "Respond with only a single decimal number between 0 and 1 inclusive. "
    "Use the FULL range, not just the extremes:\n"
    "- 0.0-0.3: confidently human. This includes BOTH casual personal voice (irregular rhythm, "
    "lived detail, informal asides) AND formal expert/academic prose that is specific and "
    "substantive: precise domain terminology, concrete named mechanisms or trade-offs, and "
    "argued claims that demonstrate real subject-matter knowledge.\n"
    "- 0.4-0.6: mixed or ambiguous. Use this band when the text could be AI-generated but "
    "lightly edited, or human writing assisted by AI. Signs include a casual surface over a "
    "balanced/symmetrical structure ('on one hand... on the other'), generic hedged claims, "
    "vague appeals to evidence ('studies show') without specifics, or smooth but content-light "
    "prose.\n"
    "- 0.7-1.0: confidently AI (uniform cadence, template transitions like 'it is important to "
    "note' or 'furthermore', comprehensive-but-generic coverage, buzzwords without substance, "
    "little concrete detail).\n"
    "Tone alone is NOT a signal: a formal or academic register does not make text AI-generated, "
    "and a casual register does not make it human. Judge by specificity and substance, not "
    "polish. Dense, precise, knowledgeable writing should score LOW even when formal; vague, "
    "generic, buzzword-laden writing should score HIGH even when it sounds sophisticated."
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
