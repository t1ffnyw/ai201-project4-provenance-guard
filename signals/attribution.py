def attribution_from_llm_score(llm_score: float) -> str:
    if llm_score < 0.4:
        return "likely_human"
    if llm_score <= 0.6:
        return "uncertain"
    return "likely_ai"


def label_from_attribution(attribution: str) -> str:
    labels = {
        "likely_human": "Likely Human",
        "uncertain": "Mixed/Uncertain",
        "likely_ai": "Likely AI",
    }
    return labels.get(attribution, "Mixed/Uncertain")
