# utils/eval_utils.py


def recall_at_k(ground_truth, results, k) -> float:
    """
    Compute Recall@k for a single query.
    :param ground_truth: list of relevant photo_ids
    :param results: list of (photo_id, score), ranked descending
    :param k: cutoff
    :return: recall@k
    """
    if not ground_truth:
        return 1.0
    top_k_ids = [photo_id for photo_id, _ in results[:k]]
    hits = sum(1 for pid in top_k_ids if pid in ground_truth)
    return hits / len(ground_truth)


def average_precision(ground_truth, results) -> float:
    """
    Compute Average Precision (AP) for a single query.
    :param ground_truth: list of relevant photo_ids
    :param results: list of (photo_id, score), ranked descending
    :return: AP score
    """
    if not ground_truth:
        return 1.0
    gt_set = set(ground_truth)

    num_hits = 0
    precision_sum = 0.0

    for i, (photo_id, _) in enumerate(results):
        if photo_id in gt_set:
            num_hits += 1
            precision_at_i = num_hits / (i + 1)
            precision_sum += precision_at_i

    return precision_sum / len(gt_set)
