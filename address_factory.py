"""Mass registration address detection.

Thousands of companies can legitimately share the address of a formation
agent or an accountant. A company factory looks different in three ways: the
companies registered there die young or never file accounts, their directors
live overseas, and they arrive in waves. The detector works on resolved
address nodes, so suites, floors and formatting differences do not split a
building into many small addresses.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .context import DetectionContext, group_mean


def score_addresses(address: np.ndarray, shell_like: np.ndarray, overseas: np.ndarray, inc_day: np.ndarray, min_companies: int, n_addresses: int) -> pd.DataFrame:
    """Score every address from flat per company arrays."""
    count = np.bincount(address, minlength=n_addresses)
    shell_ratio = group_mean(shell_like, address, n_addresses)
    overseas_ratio = group_mean(overseas, address, n_addresses)
    window = (inc_day // 14).astype(np.int64)
    pair = pd.DataFrame({"a": address, "w": window}).groupby(["a", "w"], sort=False).size()
    peak = pair.groupby(level=0).max()
    burst = np.zeros(n_addresses)
    burst[peak.index.to_numpy()] = peak.to_numpy()
    burst_share = np.divide(burst, count, out=np.zeros(n_addresses), where=count > 0)
    floor = max(2, min_companies)
    volume = np.clip((np.log(np.maximum(count, 1)) - np.log(floor)) / (np.log(800) - np.log(floor)), 0, 1)
    score = np.clip(0.05 + 0.15 * volume + 0.55 * shell_ratio + 0.25 * overseas_ratio, 0, 1)
    score = np.where(count >= min_companies, score, 0.0)
    return pd.DataFrame(
        {"n_companies": count, "shell_ratio": shell_ratio, "overseas_ratio": overseas_ratio, "burst_share": burst_share, "factory_score": score}
    )


def detect_address_factories(ctx: DetectionContext) -> pd.DataFrame:
    """Add address features to the company frame and return the address table."""
    cf = ctx.cf
    nodes, local = np.unique(ctx.address_node, return_inverse=True)
    table = score_addresses(
        local, cf["shell_like"].to_numpy(), cf["director_overseas"].to_numpy(), cf["inc_day"].to_numpy(),
        ctx.settings.detect.factory_min_companies, len(nodes),
    )
    n_dir = pd.DataFrame({"a": local[ctx.dir_company], "p": ctx.dir_person}).drop_duplicates().groupby("a").size()
    diversity = np.zeros(len(nodes))
    diversity[n_dir.index.to_numpy()] = n_dir.to_numpy()
    table["director_diversity"] = np.divide(diversity, table["n_companies"], out=np.zeros(len(nodes)), where=table["n_companies"] > 0)
    table.insert(0, "node_id", nodes)
    cf["address_node"] = ctx.address_node
    cf["addr_companies"] = np.log1p(table["n_companies"].to_numpy()[local]).astype(np.float32)
    cf["addr_n"] = table["n_companies"].to_numpy()[local]
    cf["addr_shell_ratio"] = table["shell_ratio"].to_numpy()[local].astype(np.float32)
    cf["addr_overseas_ratio"] = table["overseas_ratio"].to_numpy()[local].astype(np.float32)
    cf["addr_burst_share"] = table["burst_share"].to_numpy()[local].astype(np.float32)
    cf["addr_director_diversity"] = table["director_diversity"].to_numpy()[local].astype(np.float32)
    cf["score_address_factory"] = table["factory_score"].to_numpy()[local].astype(np.float32)
    return table.set_index("node_id")
