"""Supervised challenger model and the simple baselines it is compared with.

The rule fusion score needs no labels, which matters because a real registry
has none. Where an institution does hold confirmed outcomes from past
investigations, a supervised model can learn interactions that hand written
rules miss. This module trains a gradient boosted classifier on the raw
features (never on the typology scores) with grouped cross validation, so
companies that share an address never straddle the train and test folds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import GroupKFold

from ..config import ModelConfig
from ..logging_utils import get_logger
from .engine import MODEL_FEATURES

log = get_logger(__name__)


@dataclass
class RiskModelResult:
    """Out of fold probabilities, the final model and feature importance."""

    oof: np.ndarray
    model: HistGradientBoostingClassifier
    importance: pd.DataFrame


def _new_model(cfg: ModelConfig) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=cfg.learning_rate,
        max_iter=cfg.max_iter,
        max_leaf_nodes=cfg.max_leaf_nodes,
        l2_regularization=cfg.l2_regularization,
        random_state=cfg.seed,
    )


def train_risk_model(cf: pd.DataFrame, labels: np.ndarray, groups: np.ndarray, cfg: ModelConfig) -> RiskModelResult:
    """Grouped cross validation followed by a final fit on all data."""
    x = cf[MODEL_FEATURES].to_numpy(dtype=np.float32)
    y = np.asarray(labels).astype(int)
    oof = np.zeros(len(y), dtype=np.float32)
    for fold, (train, test) in enumerate(GroupKFold(n_splits=cfg.n_folds).split(x, y, groups)):
        model = _new_model(cfg)
        model.fit(x[train], y[train])
        oof[test] = model.predict_proba(x[test])[:, 1]
        log.info("risk model fold %d done", fold + 1)
    final = _new_model(cfg)
    final.fit(x, y)
    rng = np.random.default_rng(cfg.seed)
    sample = rng.choice(len(y), size=min(len(y), 20_000), replace=False)
    perm = permutation_importance(final, x[sample], y[sample], scoring="average_precision", n_repeats=3, random_state=cfg.seed)
    importance = pd.DataFrame({"feature": MODEL_FEATURES, "importance": perm.importances_mean}).sort_values("importance", ascending=False).reset_index(drop=True)
    return RiskModelResult(oof, final, importance)


def baseline_scores(cf: pd.DataFrame) -> dict[str, np.ndarray]:
    """Scores for the naive approaches an institution might start from."""
    direct_list_hit = ((cf["sanction_hops"] <= 1) & (cf["sanction_confidence"] >= 0.86)).to_numpy(dtype=float)
    return {
        "Direct name screening only": direct_list_hit * cf["sanction_confidence"].to_numpy(),
        "Address density rule": cf["addr_companies"].to_numpy() / max(1e-9, float(cf["addr_companies"].max())),
        "Appointment count rule": cf["max_director_companies"].to_numpy() / max(1e-9, float(cf["max_director_companies"].max())),
    }
