"""Resolution of corporate controllers to registry, leak or foreign entities.

A corporate person with significant control is recorded as free text: a name,
sometimes a registration number, and a place of registration typed by the
filer. To follow an ownership chain the text has to be tied to a node. This
module resolves each corporate controller to, in order of preference, a UK
company, an offshore entity from the leak data, or a foreign company stub
that is created so the chain can still be drawn.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from ..config import ResolutionConfig
from ..logging_utils import get_logger
from ..textnorm import canonical_jurisdiction, company_core, norm_company_name

log = get_logger(__name__)
UK = "UNITED KINGDOM"


def _unique_lookup(keys: pd.Series, values: pd.Series) -> dict:
    """Map each key to its value, keeping only keys that occur exactly once."""
    frame = pd.DataFrame({"k": keys.to_numpy(), "v": values.to_numpy()})
    frame = frame[frame["k"] != ""]
    single = frame[~frame["k"].duplicated(keep=False)]
    return dict(zip(single["k"], single["v"]))


def _first_token_index(cores: pd.Series, values: pd.Series) -> dict[str, list[tuple[str, object]]]:
    """Index company cores by their first and by their last token.

    Two blocks are kept so that a typing slip in one end of a name still
    leaves the other end available for candidate lookup.
    """
    index: dict[str, list[tuple[str, object]]] = {}
    for core, value in zip(cores, values):
        if core:
            tokens = core.split(" ")
            index.setdefault("F|" + tokens[0], []).append((core, value))
            index.setdefault("L|" + tokens[len(tokens) - 1], []).append((core, value))
    return index


def _fuzzy(core: str, index: dict, threshold: float) -> tuple[object, float]:
    """Best fuzzy match of a company core inside its token blocks."""
    if not core:
        return None, 0.0
    tokens = core.split(" ")
    bucket = index.get("F|" + tokens[0], []) + index.get("L|" + tokens[len(tokens) - 1], [])
    if not bucket:
        return None, 0.0
    choices = [c for c, _ in bucket]
    found = process.extract(core, choices, scorer=fuzz.ratio, limit=3, score_cutoff=threshold)
    if not found:
        return None, 0.0
    top = found[0][1]
    winners = {bucket[item[2]][1] for item in found if item[1] == top}
    if len(winners) > 1:
        return None, 0.0
    return bucket[found[0][2]][1], float(top)


def resolve_corporates(
    pscs: pd.DataFrame,
    companies: pd.DataFrame,
    offshore_entities: pd.DataFrame,
    cfg: ResolutionConfig,
    aliases: dict[str, str],
) -> pd.DataFrame:
    """Resolve every corporate control record to a target node key.

    Returns one row per record with target_kind (company, offshore or
    foreign), target_key, the method that produced the link and its score.
    """
    corp = pscs[pscs["kind"] == "corporate"].copy()
    if corp.empty:
        return pd.DataFrame(columns=["psc_id", "target_kind", "target_key", "target_label", "jurisdiction", "method", "score"])
    comp_norm = companies["company_name"].map(norm_company_name)
    comp_core = companies["company_name"].map(company_core)
    numbers = companies["company_number"]
    number_to_core = dict(zip(numbers, comp_core))
    by_norm = _unique_lookup(comp_norm, numbers)
    by_core = _unique_lookup(comp_core, numbers)
    uk_index = _first_token_index(comp_core, numbers)

    off_core = offshore_entities["name"].map(company_core)
    off_jur = offshore_entities["jurisdiction"].map(lambda j: canonical_jurisdiction(j, aliases))
    off_by_jur = _unique_lookup(off_jur + "|" + off_core, offshore_entities["node_id"])
    off_by_core = _unique_lookup(off_core, offshore_entities["node_id"])
    off_index = _first_token_index(off_jur + " " + off_core, offshore_entities["node_id"])

    kinds, keys, labels, jurs, methods, scores = [], [], [], [], [], []
    for name, reg, country in zip(corp["name"], corp["registration_number"], corp["country_registered"]):
        jur = canonical_jurisdiction(country, aliases)
        norm = norm_company_name(name)
        core = company_core(name)
        kind, key, method, score = "", "", "", 0.0
        if jur in ("", UK):
            digits = "".join(ch for ch in str(reg) if ch.isalnum()).upper()
            candidate = digits.zfill(8) if digits else ""
            if candidate in number_to_core and fuzz.token_sort_ratio(core, number_to_core[candidate]) >= 70:
                kind, key, method, score = "company", candidate, "registration number", 100.0
            elif norm in by_norm:
                kind, key, method, score = "company", by_norm[norm], "exact name", 100.0
            elif core in by_core:
                kind, key, method, score = "company", by_core[core], "name without legal form", 98.0
            else:
                hit, hit_score = _fuzzy(core, uk_index, cfg.corporate_similarity)
                if hit is not None:
                    kind, key, method, score = "company", hit, "fuzzy name", hit_score
        if not kind and jur != UK:
            if jur and f"{jur}|{core}" in off_by_jur:
                kind, key, method, score = "offshore", str(off_by_jur[f"{jur}|{core}"]), "name and jurisdiction", 100.0
            elif not jur and core in off_by_core:
                kind, key, method, score = "offshore", str(off_by_core[core]), "name only", 90.0
            elif jur:
                hit, hit_score = _fuzzy(f"{jur} {core}", off_index, cfg.corporate_similarity)
                if hit is not None:
                    kind, key, method, score = "offshore", str(hit), "fuzzy name and jurisdiction", hit_score
        if not kind:
            kind, key, method, score = "foreign", f"{core}|{jur}", "unresolved stub", 0.0
        kinds.append(kind)
        keys.append(key)
        labels.append(norm)
        jurs.append(jur)
        methods.append(method)
        scores.append(score)
    out = pd.DataFrame(
        {
            "psc_id": corp["psc_id"].to_numpy(),
            "target_kind": kinds,
            "target_key": keys,
            "target_label": labels,
            "jurisdiction": jurs,
            "method": methods,
            "score": np.array(scores, dtype=np.float32),
        }
    )
    log.info("corporate resolution: %s", out["target_kind"].value_counts().to_dict())
    return out


def link_leak_companies(offshore_officers: pd.DataFrame, companies: pd.DataFrame, cfg: ResolutionConfig) -> pd.DataFrame:
    """Tie company officers named in the leak data to UK registry companies.

    This closes ownership loops that pass through an offshore entity whose
    shareholder is itself a UK company.
    """
    corp = offshore_officers[offshore_officers["kind"] == "company"]
    if corp.empty:
        return pd.DataFrame(columns=["node_id", "company_number", "method"])
    comp_norm = companies["company_name"].map(norm_company_name)
    comp_core = companies["company_name"].map(company_core)
    by_norm = _unique_lookup(comp_norm, companies["company_number"])
    by_core = _unique_lookup(comp_core, companies["company_number"])
    index = _first_token_index(comp_core, companies["company_number"])
    rows = []
    for node_id, name in zip(corp["node_id"], corp["name"]):
        norm, core = norm_company_name(name), company_core(name)
        if norm in by_norm:
            rows.append((node_id, by_norm[norm], "exact name"))
        elif core in by_core:
            rows.append((node_id, by_core[core], "name without legal form"))
        else:
            hit, _ = _fuzzy(core, index, cfg.corporate_similarity)
            if hit is not None:
                rows.append((node_id, hit, "fuzzy name"))
    return pd.DataFrame(rows, columns=["node_id", "company_number", "method"])
