def attribution_from_score(score: float) -> str:
    if score < 0.4:
        return "likely_human"
    if score <= 0.6:
        return "uncertain"
    return "likely_ai"


def label_from_attribution(attribution: str) -> str:
    labels = {
        "likely_human": "Likely Human",
        "uncertain": "Mixed/Uncertain",
        "likely_ai": "Likely AI",
    }
    return labels.get(attribution, "Mixed/Uncertain")
