"""Pure scoring utilities for sampled-key DIP partitioning."""
from collections import Counter
from math import log2


def evaluate_partition(outputs):
    """Score the output classes of a DIP over sampled feasible keys.

    Each item in outputs is a hashable output vector, e.g. (False, True).
    """
    if not outputs:
        raise ValueError("Cannot score an empty set of output vectors")

    counts = Counter(outputs)
    n = len(outputs)
    entropy = -sum((count / n) * log2(count / n) for count in counts.values())
    largest_class = max(counts.values())
    return {
        "entropy": entropy,
        "num_classes": len(counts),
        "largest_class": largest_class,
        "worst_case_eliminated": n - largest_class,
    }


def calculate_entropy(outputs):
    """Backward-compatible entropy helper."""
    return evaluate_partition(outputs)["entropy"]


def select_best_dip(candidate_results):
    """Select the candidate with maximum entropy and smallest largest class."""
    best_dip = None
    best_metrics = None
    for dip, outputs in candidate_results.items():
        metrics = evaluate_partition(outputs)
        if best_metrics is None or (
            metrics["entropy"], -metrics["largest_class"]
        ) > (
            best_metrics["entropy"], -best_metrics["largest_class"]
        ):
            best_dip, best_metrics = dip, metrics
    return best_dip, best_metrics


def rank_candidates(candidate_outputs):
    """Backward-compatible sorted DIP scoring report."""
    results = [
        {"candidate": dip, **evaluate_partition(outputs)}
        for dip, outputs in candidate_outputs.items()
    ]
    return sorted(results, key=lambda x: (-x["entropy"], x["largest_class"]))
