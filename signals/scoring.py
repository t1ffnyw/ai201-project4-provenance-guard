W1 = 0.7
W2 = 0.3


def compute_final_score(llm_score: float, stylometric_score: float) -> float:
    final_score = W1 * llm_score + W2 * stylometric_score
    return max(0.0, min(1.0, final_score))
