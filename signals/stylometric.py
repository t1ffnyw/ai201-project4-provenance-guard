import math
import re
import string

_PUNCTUATION = set(string.punctuation)
_SENTENCE_SPLIT = re.compile(r"[.!?]+")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _linear_map(value: float, low_in: float, high_in: float, low_out: float, high_out: float) -> float:
    if high_in == low_in:
        return low_out
    ratio = (value - low_in) / (high_in - low_in)
    return _clamp(low_out + ratio * (high_out - low_out))


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _split_sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    return parts if parts else [text.strip()]


def sentence_length_variance_score(text: str) -> float:
    """Low variance in sentence length -> higher AI-likeness."""
    sentences = _split_sentences(text)
    lengths = [len(_tokenize_words(sentence)) for sentence in sentences]
    lengths = [length for length in lengths if length > 0]
    if not lengths:
        return 0.5

    if len(lengths) == 1:
        return 0.7

    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.5

    variance = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    cv = math.sqrt(variance) / mean
    return _linear_map(cv, 0.0, 0.6, 1.0, 0.0)


def punctuation_density_score(text: str) -> float:
    """Distance from typical prose punctuation density -> higher AI-likeness."""
    if not text:
        return 0.5

    punct_count = sum(1 for char in text if char in _PUNCTUATION)
    density = punct_count / len(text)
    ideal = 0.03
    max_distance = 0.06
    distance = abs(density - ideal)
    return _linear_map(distance, 0.0, max_distance, 0.0, 1.0)


def stylometric_breakdown(text: str) -> dict[str, float]:
    if not text or not text.strip():
        raise ValueError("text must be non-empty")

    return {
        "sentence_length_variance": sentence_length_variance_score(text),
        "punctuation_density": punctuation_density_score(text),
    }


def stylometric_score(text: str) -> float:
    """Return 0-1 score: 0 = likely human, 1 = likely AI."""
    breakdown = stylometric_breakdown(text)
    scores = list(breakdown.values())
    return sum(scores) / len(scores)
