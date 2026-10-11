"""Nominee director detection.

A nominee lends a name to companies that someone else runs. Volume alone
does not identify one: accountants, company secretaries and professional
directors also hold many appointments. What separates a nominee is that the
companies behind the appointments look disposable and that the nominee is
usually the only director on each of them. The score combines appointment
volume with those two ratios.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .context import DetectionContext, group_max, group_mean


def score_directors(person: np.ndarray, company: np.ndarray, shell_like: np.ndarray, n_directors: np.ndarray, min_companies: int, n_persons: int) -> pd.DataFrame:
    """Score every director from flat (person, company) appointment pairs.

    The function takes plain arrays so the same logic can be run on resolved
    persons and on exact name groups, which is how the benefit of entity
    resolution is measured.
    """
    pairs = np.unique(np.stack([person, company], axis=1), axis=0)
    p, c = pairs[:, 0], pairs[:, 1]
    count = np.bincount(p, minlength=n_persons)
    shell_ratio = group_mean(shell_like[c], p, n_persons)
    sole_ratio = group_mean((n_directors[c] == 1).astype(float), p, n_persons)
    floor = max(2, min_companies)
    volume = np.clip((np.log(np.maximum(count, 1)) - np.log(floor)) / (np.log(200) - np.log(floor)), 0, 1)
    score = np.clip(0.15 + 0.25 * volume + 0.45 * shell_ratio + 0.15 * sole_ratio, 0, 1)
    score = np.where(count >= min_companies, score, 0.0)
    return pd.DataFrame({"n_companies": count, "shell_ratio": shell_ratio, "sole_ratio": sole_ratio, "nominee_score": score})


def detect_nominees(ctx: DetectionContext) -> pd.DataFrame:
    """Add nominee features to the company frame and return the person table."""
    n = ctx.n_companies
    cf = ctx.cf
    n_directors = np.bincount(ctx.dir_company, minlength=n).astype(np.float32)
    persons = score_directors(
        ctx.dir_person, ctx.dir_company, cf["shell_like"].to_numpy(), n_directors, ctx.settings.detect.nominee_min_companies, ctx.graph.n_nodes
    )
    persons["overseas"] = ctx.person_overseas
    p, c = ctx.dir_person, ctx.dir_company
    cf["n_directors"] = n_directors
    cf["max_director_companies"] = np.log1p(group_max(persons["n_companies"].to_numpy()[p].astype(float), c, n)).astype(np.float32)
    busy = persons["n_companies"].to_numpy()[p] >= 5
    cf["director_shell_ratio"] = group_max(np.where(busy, persons["shell_ratio"].to_numpy()[p], 0.0), c, n).astype(np.float32)
    cf["director_sole_ratio"] = group_max(np.where(busy, persons["sole_ratio"].to_numpy()[p], 0.0), c, n).astype(np.float32)
    cf["director_overseas"] = group_mean(ctx.person_overseas[p], c, n).astype(np.float32)
    cf["score_nominee"] = group_max(persons["nominee_score"].to_numpy()[p], c, n).astype(np.float32)
    top = np.full(n, -1, dtype=np.int64)
    order = np.argsort(persons["nominee_score"].to_numpy()[p], kind="stable")
    top[c[order]] = p[order]
    cf["top_director_node"] = top
    persons = persons[persons["n_companies"] > 0].copy()
    persons.index.name = "node_id"
    return persons
