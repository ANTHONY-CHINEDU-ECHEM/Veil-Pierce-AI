"""Burst incorporation and phoenix detection.

Two patterns are covered. A burst is a batch of companies created within
days of each other by the same director at the same small address and then
abandoned. A phoenix is a company that is dissolved and immediately reborn
under a near identical name with the same director at the same address,
leaving its obligations behind. Property developers also create batches of
companies on one day, so a batch only scores when its members look
abandoned.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from ..textnorm import company_core
from .context import DetectionContext


def detect_churn(ctx: DetectionContext) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add churn features to the company frame.

    Returns the batch membership table and the table of phoenix pairs.
    """
    cfg = ctx.settings.detect
    cf = ctx.cf
    n = ctx.n_companies
    pairs = pd.DataFrame({"p": ctx.dir_person, "c": ctx.dir_company}).drop_duplicates()
    pairs["a"] = ctx.address_node[pairs["c"].to_numpy()]
    pairs["inc"] = cf["inc_day"].to_numpy()[pairs["c"].to_numpy()]
    pairs = pairs.sort_values(["p", "a", "inc"], kind="stable").reset_index(drop=True)
    new_run = (pairs["p"].diff() != 0) | (pairs["a"].diff() != 0) | (pairs["inc"].diff() > 7)
    pairs["run"] = new_run.cumsum()
    pairs["run_size"] = pairs.groupby("run")["c"].transform("size")
    shell = cf["shell_like"].to_numpy()[pairs["c"].to_numpy()]
    run_shell = pd.Series(shell).groupby(pairs["run"].to_numpy()).transform("mean").to_numpy()
    pairs["run_shell"] = run_shell
    batch_size = np.zeros(n)
    batch_shell = np.zeros(n)
    order = np.argsort(pairs["run_size"].to_numpy(), kind="stable")
    c_sorted = pairs["c"].to_numpy()[order]
    batch_size[c_sorted] = pairs["run_size"].to_numpy()[order]
    batch_shell[c_sorted] = pairs["run_shell"].to_numpy()[order]
    small_address = cf["addr_n"].to_numpy() < cfg.factory_min_companies
    is_batch = (batch_size >= cfg.burst_min_batch) & small_address
    burst = np.where(is_batch, np.clip(0.15 + 0.1 * np.minimum(1, batch_size / 12) + 0.7 * batch_shell, 0, 1), 0.0)
    cf["batch_size"] = np.where(is_batch, batch_size, 0).astype(np.float32)
    cf["batch_shell_ratio"] = np.where(is_batch, batch_shell, 0).astype(np.float32)
    batches = pairs[pairs["run_size"] >= cfg.burst_min_batch][["run", "p", "a", "c", "run_size", "run_shell"]].copy()

    # Phoenix pairs: an old company dies and a lookalike appears at once.
    per_person = pairs.groupby("p")["c"].transform("size")
    small = pairs[(per_person >= 2) & (per_person <= 60)][["p", "c", "a"]]
    small = small.assign(diss=cf["diss_day"].to_numpy()[small["c"].to_numpy()], inc=cf["inc_day"].to_numpy()[small["c"].to_numpy()])
    old = small[small["diss"] >= 0]
    joined = old.merge(small, on=["p", "a"], suffixes=("_old", "_new"))
    gap = joined["inc_new"] - joined["diss_old"]
    joined = joined[(joined["c_old"] != joined["c_new"]) & (gap >= -30) & (gap <= cfg.phoenix_gap_days)]
    names = cf["company_name"].to_numpy()
    similarity = np.array(
        [
            max(fuzz.ratio(a, b), fuzz.token_set_ratio(a, b))
            for a, b in ((company_core(names[i]), company_core(names[j])) for i, j in zip(joined["c_old"], joined["c_new"]))
        ],
        dtype=np.float32,
    )
    joined = joined.assign(similarity=similarity, gap_days=gap.loc[joined.index].to_numpy())
    phoenix = joined[joined["similarity"] >= cfg.phoenix_name_similarity][["p", "a", "c_old", "c_new", "gap_days", "similarity"]].reset_index(drop=True)
    phoenix_flag = np.zeros(n)
    phoenix_flag[phoenix["c_old"].to_numpy()] = 1.0
    phoenix_flag[phoenix["c_new"].to_numpy()] = 1.0
    cf["phoenix_link"] = phoenix_flag.astype(np.float32)
    cf["score_phoenix_burst"] = np.maximum(burst, 0.85 * phoenix_flag).astype(np.float32)
    return batches, phoenix
