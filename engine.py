"""Runs every detector and fuses the typology scores into one risk score."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Settings
from ..data.synth import Registry
from ..graph.build import ResolutionBundle
from ..graph.store import KnowledgeGraph
from ..logging_utils import get_logger
from ..rag.guard import looks_like_injection
from .address_factory import detect_address_factories
from .base import FLAG_THRESHOLDS, FUSION_WEIGHTS, RISK_BANDS
from .churn import detect_churn
from .circular import detect_circular
from .context import build_context
from .nominee import detect_nominees
from .opacity import detect_opacity
from .sanctions_proximity import detect_sanctions_proximity

log = get_logger(__name__)

MODEL_FEATURES = [
    "age_days", "dissolved", "short_life", "no_accounts", "dormant", "accounts_overdue", "shell_like", "healthy_accounts",
    "n_directors", "max_director_companies", "director_shell_ratio", "director_sole_ratio", "director_overseas",
    "addr_companies", "addr_shell_ratio", "addr_overseas_ratio", "addr_burst_share", "addr_director_diversity",
    "psc_individuals", "psc_corporates", "no_declared_controller", "declared_depth", "no_person_in_chain", "chain_depth",
    "upstream_opacity", "hidden_controller_in_leak", "in_cycle", "cycle_size", "cycle_offshore",
    "sanction_proximity", "sanction_confidence", "batch_size", "batch_shell_ratio", "phoenix_link",
]
TYPOLOGIES = list(FUSION_WEIGHTS)


@dataclass
class DetectionResult:
    """Everything the detectors produced, kept so findings can be explained."""

    companies: pd.DataFrame
    persons: pd.DataFrame
    addresses: pd.DataFrame
    component: np.ndarray
    component_size: np.ndarray
    reach: dict
    profile: dict
    batches: pd.DataFrame
    phoenix: pd.DataFrame

    def row(self, company_number: str) -> pd.Series:
        hit = self.companies.index[self.companies["company_number"] == company_number]
        if len(hit) == 0:
            raise KeyError(f"unknown company number: {company_number}")
        return self.companies.loc[hit[0]]


def fuse_scores(cf: pd.DataFrame) -> np.ndarray:
    """Noisy OR fusion: independent typologies reinforce each other."""
    survive = np.ones(len(cf), dtype=np.float64)
    for typology, weight in FUSION_WEIGHTS.items():
        survive *= 1.0 - weight * cf[f"score_{typology}"].to_numpy(dtype=np.float64)
    return 1.0 - survive


def band_of(scores: np.ndarray) -> np.ndarray:
    out = np.full(len(scores), "Low", dtype=object)
    for floor, name in reversed(RISK_BANDS):
        out[scores >= floor] = name
    return out


def run_detection(registry: Registry, graph: KnowledgeGraph, bundle: ResolutionBundle, settings: Settings) -> DetectionResult:
    """Compute features, typology scores, flags and the fused risk score."""
    ctx = build_context(registry, graph, bundle, settings)
    persons = detect_nominees(ctx)
    addresses = detect_address_factories(ctx)
    component, sizes = detect_circular(ctx)
    reach = detect_sanctions_proximity(ctx)
    profile = detect_opacity(ctx)
    batches, phoenix = detect_churn(ctx)
    cf = ctx.cf
    for typology in TYPOLOGIES:
        cf[f"flag_{typology}"] = cf[f"score_{typology}"] >= FLAG_THRESHOLDS[typology]
    cf["n_flags"] = cf[[f"flag_{t}" for t in TYPOLOGIES]].sum(axis=1)
    cf["risk_rules"] = fuse_scores(cf).astype(np.float32)
    cf["risk_band"] = band_of(cf["risk_rules"].to_numpy())
    cf["name_injection"] = [looks_like_injection(name) for name in cf["company_name"]]
    cf["node_id"] = np.arange(len(cf))
    log.info(
        "detection: flags %s, bands %s",
        {t: int(cf[f"flag_{t}"].sum()) for t in TYPOLOGIES},
        cf["risk_band"].value_counts().to_dict(),
    )
    return DetectionResult(cf, persons, addresses, component, sizes, reach, profile, batches, phoenix)
