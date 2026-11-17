def verify_answer(pred_answer: str, gold_answer: str) -> bool:
    return pred_answer.strip() == gold_answer.strip()
