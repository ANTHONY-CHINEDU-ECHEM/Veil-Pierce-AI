"""Person entity resolution across officer appointments and control records.

A nominee who fronts hundreds of companies rarely appears under one spelling.
Middle names are dropped, initials are used, letters are transposed. Counting
appointments by exact name therefore undercounts the very people the system
most needs to find. This module links records that refer to the same natural
person, using the month and year of birth that both registers publish as a
strong blocking key and fuzzy name comparison inside each block.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from rapidfuzz.distance import JaroWinkler
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from ..config import ResolutionConfig
from ..logging_utils import get_logger
from ..textnorm import parse_person_name, translit_key

log = get_logger(__name__)


@dataclass
class PersonResolution:
    """Result of person resolution.

    records holds one row per source record with its resolved cluster and the
    cluster it would have received from exact string matching. clusters holds
    one row per resolved person.
    """

    records: pd.DataFrame
    clusters: pd.DataFrame


def _names_compatible(a: tuple, b: tuple, cfg: ResolutionConfig) -> bool:
    """Decide whether two name keys with the same birth month are one person."""
    sur_a, first_a, rest_a = a
    sur_b, first_b, rest_b = b
    if sur_a != sur_b and JaroWinkler.similarity(sur_a, sur_b) < cfg.surname_similarity:
        return False
    if first_a != first_b:
        if not first_a or not first_b:
            return False
        if len(first_a) == 1 or len(first_b) == 1:
            if first_a[0] != first_b[0]:
                return False
        elif JaroWinkler.similarity(first_a, first_b) < cfg.forename_similarity:
            return False
        elif sur_a != sur_b:
            return False
    if rest_a and rest_b and rest_a[0] != rest_b[0]:
        return False
    return True


def _block_pairs(keys: list[tuple], block: np.ndarray, cfg: ResolutionConfig) -> tuple[list[int], list[int], int]:
    """Compare all key pairs inside every block and return the linked pairs."""
    order = np.argsort(block, kind="stable")
    sorted_block = block[order]
    cuts = np.flatnonzero(np.diff(sorted_block)) + 1
    starts = np.concatenate([[0], cuts])
    ends = np.concatenate([cuts, [len(order)]])
    sizes = ends - starts
    left: list[int] = []
    right: list[int] = []
    skipped = 0
    for start, end, size in zip(starts[sizes > 1], ends[sizes > 1], sizes[sizes > 1]):
        if size > cfg.max_block_size:
            skipped += 1
            continue
        members = order[start:end]
        for i in range(size):
            key_i = keys[members[i]]
            for j in range(i + 1, size):
                if _names_compatible(key_i, keys[members[j]], cfg):
                    left.append(int(members[i]))
                    right.append(int(members[j]))
    return left, right, skipped


def resolve_persons(officers: pd.DataFrame, pscs: pd.DataFrame, cfg: ResolutionConfig) -> PersonResolution:
    """Cluster officer and individual control records into natural persons."""
    off = officers[officers["officer_kind"] == "person"]
    ind = pscs[pscs["kind"] == "individual"]
    records = pd.DataFrame(
        {
            "source": np.concatenate([np.full(len(off), "officer", dtype=object), np.full(len(ind), "psc", dtype=object)]),
            "record_id": np.concatenate([off["appointment_id"].to_numpy(), ind["psc_id"].to_numpy()]),
            "company_number": np.concatenate([off["company_number"].to_numpy(dtype=object), ind["company_number"].to_numpy(dtype=object)]),
            "raw_name": np.concatenate([off["officer_name"].to_numpy(dtype=object), ind["name"].to_numpy(dtype=object)]),
            "dob_year": np.concatenate([off["dob_year"].to_numpy(), ind["dob_year"].to_numpy()]).astype(np.int32),
            "dob_month": np.concatenate([off["dob_month"].to_numpy(), ind["dob_month"].to_numpy()]).astype(np.int32),
            "residence": np.concatenate([off["country_of_residence"].to_numpy(dtype=object), ind["country_of_residence"].to_numpy(dtype=object)]),
        }
    )
    unique_names = pd.unique(records["raw_name"])
    parsed = {name: parse_person_name(name) for name in unique_names}
    parts = records["raw_name"].map(parsed)
    records["surname"] = [p[0] for p in parts]
    records["first"] = [p[1] for p in parts]
    records["rest"] = [p[2] for p in parts]

    records["exact_id"] = records.groupby(["raw_name", "dob_year", "dob_month"], sort=False).ngroup()
    key_cols = ["surname", "first", "rest", "dob_year", "dob_month"]
    records["uid"] = records.groupby(key_cols, sort=False).ngroup()
    uniq = records.drop_duplicates("uid").sort_values("uid")
    keys = list(zip(uniq["surname"], uniq["first"], uniq["rest"]))
    n = len(uniq)
    has_dob = (uniq["dob_year"].to_numpy() > 0)
    ym = uniq["dob_year"].to_numpy().astype(np.int64) * 13 + uniq["dob_month"].to_numpy()

    sur_key = pd.factorize(pd.Series([translit_key(s) for s in uniq["surname"]]))[0]
    first_key = pd.factorize(pd.Series([translit_key(f) + "|" + s[:1] for f, s in zip(uniq["first"], uniq["surname"])]))[0]
    lone = np.arange(n) + 10_000_000
    block_a = np.where(has_dob, ym * 4_000_000 + sur_key, (-1) * lone)
    block_b = np.where(has_dob, ym * 4_000_000 + first_key, (-1) * lone)
    left_a, right_a, skip_a = _block_pairs(keys, block_a, cfg)
    left_b, right_b, skip_b = _block_pairs(keys, block_b, cfg)
    left = np.array(left_a + left_b, dtype=np.int64)
    right = np.array(right_a + right_b, dtype=np.int64)
    graph = coo_matrix((np.ones(len(left), dtype=np.int8), (left, right)), shape=(n, n))
    _, component = connected_components(graph, directed=False)
    records["cluster_id"] = component[records["uid"].to_numpy()]
    if skip_a or skip_b:
        log.warning("person resolution skipped %d oversized blocks", skip_a + skip_b)

    records["full_norm"] = (records["first"] + " " + records["rest"]).str.strip() + " " + records["surname"]
    counts = records.groupby(["cluster_id", "full_norm"], sort=False).size().rename("n").reset_index()
    counts["tokens"] = counts["full_norm"].str.count(" ")
    counts = counts.sort_values(["cluster_id", "n", "tokens"], ascending=[True, False, False])
    best = counts.drop_duplicates("cluster_id")
    top = counts[counts.groupby("cluster_id").cumcount() < 6]
    multi = top[top.duplicated("cluster_id", keep=False)]
    joined = multi.groupby("cluster_id", sort=False)["full_norm"].agg("|".join)
    grouped = records.groupby("cluster_id", sort=True)
    clusters = pd.DataFrame(
        {
            "cluster_id": grouped["cluster_id"].first(),
            "dob_year": grouped["dob_year"].max(),
            "dob_month": grouped["dob_month"].first(),
            "n_records": grouped.size(),
            "n_variants": grouped["uid"].nunique(),
            "residence": grouped["residence"].first(),
        }
    ).reset_index(drop=True)
    clusters = clusters.merge(best[["cluster_id", "full_norm"]].rename(columns={"full_norm": "label"}), on="cluster_id")
    clusters["variants"] = clusters["cluster_id"].map(joined).fillna(clusters["label"])
    records = records.drop(columns=["full_norm"])
    log.info("person resolution: %d records, %d exact names, %d resolved persons", len(records), records["exact_id"].nunique(), len(clusters))
    return PersonResolution(records=records, clusters=clusters)
