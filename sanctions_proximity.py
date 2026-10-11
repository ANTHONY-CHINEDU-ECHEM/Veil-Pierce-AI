"""Sanctions proximity detection.

Screening a company name against a list finds almost nothing, because a
designated person rarely owns anything directly. The exposure sits one or
more steps away: the person controls an offshore entity, the entity controls
a UK company, and that company controls another. This detector starts from
every screened match and follows the direction of control downstream for a
bounded number of hops. Risk decays with distance and is scaled by the
confidence of the screening match, so a name only match can never score as
high as a match confirmed by date of birth.
"""

from __future__ import annotations

import numpy as np

from ..graph.algorithms import downstream_reach
from .context import DetectionContext


def detect_sanctions_proximity(ctx: DetectionContext) -> dict[str, np.ndarray]:
    """Add proximity features to the company frame and return the search state."""
    graph, cfg = ctx.graph, ctx.settings.detect
    match = graph.etype == "sanctions_match"
    sources = graph.dst[match]
    confidence = graph.edges["confidence"].to_numpy(dtype=np.float32)[match]
    dist, pred, origin = downstream_reach(graph, sources, confidence, cfg.sanctions_max_hops)
    node_conf = np.zeros(graph.n_nodes, dtype=np.float32)
    np.maximum.at(node_conf, sources, confidence)
    n = ctx.n_companies
    d = dist[:n]
    reached = d >= 0
    conf = np.where(reached, node_conf[np.where(origin[:n] >= 0, origin[:n], 0)], 0.0)
    risk = np.where(reached, conf * cfg.sanctions_hop_decay ** np.maximum(d - 1, 0), 0.0)
    ctx.cf["sanction_hops"] = np.where(reached, d, 0).astype(np.float32)
    ctx.cf["sanction_proximity"] = np.where(reached, 1.0 / (1.0 + np.maximum(d, 0)), 0.0).astype(np.float32)
    ctx.cf["sanction_confidence"] = conf.astype(np.float32)
    ctx.cf["score_sanctions"] = risk.astype(np.float32)
    return {"dist": dist, "pred": pred, "origin": origin, "confidence": node_conf}
