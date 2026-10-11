"""Metric helpers used across the evaluation suite."""

from __future__ import annotations

import numpy as np
import pandas as pd


def prf(pred: np.ndarray, truth: np.ndarray) -> dict:
    """Precision, recall and F1 for boolean predictions."""
    pred = np.asarray(pred).astype(bool)
    truth = np.asarray(truth).astype(bool)
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def _pairs(values) -> int:
    counts = pd.Series(values).value_counts().to_numpy().astype(np.int64)
    return int((counts * (counts - 1) // 2).sum())


def pairwise_cluster_metrics(pred_ids, true_ids) -> dict:
    """Pairwise precision, recall and F1 of a clustering against truth."""
    pred_ids = pd.Series(np.asarray(pred_ids)).astype(str)
    true_ids = pd.Series(np.asarray(true_ids)).astype(str)
    both = _pairs(pred_ids + "|" + true_ids)
    predicted = _pairs(pred_ids)
    actual = _pairs(true_ids)
    precision = both / predicted if predicted else 1.0
    recall = both / actual if actual else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def precision_at_k(scores: np.ndarray, truth: np.ndarray, k: int) -> float:
    k = min(int(k), len(scores))
    top = np.argsort(-np.asarray(scores), kind="stable")[:k]
    return float(np.asarray(truth)[top].mean()) if k else 0.0


def recall_at_budget(scores: np.ndarray, truth: np.ndarray, share: float) -> float:
    """Share of all positives found when only the top share of companies is reviewed."""
    truth = np.asarray(truth).astype(bool)
    k = max(1, int(round(share * len(scores))))
    top = np.argsort(-np.asarray(scores), kind="stable")[:k]
    return float(truth[top].sum() / max(1, truth.sum()))


def rounded(obj, digits: int = 4):
    """Round every float in a nested structure and convert numpy scalars."""
    if isinstance(obj, dict):
        return {str(k): rounded(v, digits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rounded(v, digits) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return round(float(obj), digits)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj
