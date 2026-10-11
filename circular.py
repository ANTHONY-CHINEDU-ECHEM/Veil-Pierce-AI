"""Circular ownership detection.

If company A is controlled by B, B by C and C by A, then no natural person
sits at the top of the declared structure. A loop of declared control is a
structural fact, not a statistical one: it is found exactly by computing the
strongly connected components of the ownership graph, including the edges
that pass through offshore entities named in leak data.
"""

from __future__ import annotations

import numpy as np

from ..graph.algorithms import ownership_cycles
from .context import DetectionContext


def detect_circular(ctx: DetectionContext) -> tuple[np.ndarray, np.ndarray]:
    """Add cycle features to the company frame and return the components."""
    component, sizes = ownership_cycles(ctx.graph)
    n = ctx.n_companies
    in_cycle = sizes[:n] > 1
    offshore = np.isin(ctx.graph.kind, ["offshore", "foreign"])
    has_offshore = np.zeros(component.max() + 1, dtype=bool)
    has_offshore[component[offshore & (sizes > 1)]] = True
    ctx.cf["in_cycle"] = in_cycle.astype(np.float32)
    ctx.cf["cycle_size"] = np.where(in_cycle, sizes[:n], 0).astype(np.float32)
    ctx.cf["cycle_offshore"] = (in_cycle & has_offshore[component[:n]]).astype(np.float32)
    ctx.cf["score_circular"] = np.where(in_cycle, 0.95, 0.0).astype(np.float32)
    return component, sizes
