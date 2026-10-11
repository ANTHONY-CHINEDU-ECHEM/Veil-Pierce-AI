"""Opaque offshore ownership detection.

A company is opaque when its declared chain of control never arrives at a
natural person. That alone is not suspicious: a subsidiary of a listed
foreign group is opaque in the register too. The score therefore weighs how
secretive the jurisdictions above the company are, how deep the chain runs
and whether the company itself files real accounts. Leak data is used as a
second lens: when the leak names a person behind an offshore owner that the
register leaves blank, the finding records that a hidden controller exists.
"""

from __future__ import annotations

import numpy as np

from ..graph.algorithms import ownership_profile
from .context import DetectionContext


def detect_opacity(ctx: DetectionContext) -> dict[str, np.ndarray]:
    """Add ownership chain features to the company frame."""
    graph, cfg = ctx.graph, ctx.settings.detect
    profile = ownership_profile(graph, cfg.control_max_depth)
    n = ctx.n_companies
    cf = ctx.cf
    unreachable = cfg.control_max_depth + 1
    declared = profile["declared_depth"][:n]
    leak = profile["leak_depth"][:n]
    chain = profile["chain_depth"][:n]
    upstream = profile["upstream_opacity"][:n]
    no_person = declared >= unreachable
    controls = graph.etype == "controls"
    is_person = graph.kind[graph.src] == "person"
    n_ind = np.bincount(graph.dst[controls & is_person], minlength=graph.n_nodes)[:n]
    n_corp = np.bincount(graph.dst[controls & ~is_person], minlength=graph.n_nodes)[:n]
    cf["psc_individuals"] = n_ind.astype(np.float32)
    cf["psc_corporates"] = n_corp.astype(np.float32)
    cf["no_declared_controller"] = ((n_ind + n_corp) == 0).astype(np.float32)
    cf["declared_depth"] = np.minimum(declared, unreachable).astype(np.float32)
    cf["no_person_in_chain"] = (no_person & (chain >= 1)).astype(np.float32)
    cf["chain_depth"] = chain.astype(np.float32)
    cf["upstream_opacity"] = upstream.astype(np.float32)
    cf["hidden_controller_in_leak"] = (no_person & (leak < unreachable)).astype(np.float32)
    healthy = cf["healthy_accounts"].to_numpy()
    score = 0.1 + 0.75 * upstream + 0.1 * (chain >= 2) + 0.1 * cf["shell_like"].to_numpy() - 0.3 * healthy * (1.0 - upstream)
    cf["score_opaque"] = np.where(no_person & (chain >= 1), np.clip(score, 0, 1), 0.0).astype(np.float32)
    return profile
