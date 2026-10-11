"""Sanctions screening with transliteration aware matching.

Screening answers one question for every person and entity in the graph: is
this a designated party under another spelling? The matcher works in two
steps. Candidate pairs are produced by a shared token index built on
transliteration keys, so MUHAMMAD and MOHAMED meet in the same bucket. Each
candidate is then scored on its normalised name and adjusted by the date of
birth evidence. A name that matches without any date of birth to confirm it
is capped at review level and can never become an automatic match, and it is
only raised at all when the full names are nearly identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from ..config import ResolutionConfig
from ..logging_utils import get_logger
from ..textnorm import LEGAL_FORM_TOKENS, name_tokens, norm_company_name, translit_key

log = get_logger(__name__)
STRICT_NAME_SIMILARITY = 0.93
TOKEN_SIMILARITY = 0.8
MATCH_COLUMNS = ["entity_id", "node_key", "score", "name_score", "dob_status", "matched_name", "candidate_name", "decision"]


def _alias_table(sanctions: pd.DataFrame, schema: str) -> pd.DataFrame:
    subset = sanctions[sanctions["schema"] == schema]
    rows = []
    for entity_id, name, aliases, year, month in zip(subset["entity_id"], subset["name"], subset["aliases"], subset["birth_year"], subset["birth_month"]):
        for text in [name] + [a.strip() for a in str(aliases).split(";") if a.strip()]:
            rows.append((entity_id, text, int(year), int(month)))
    return pd.DataFrame(rows, columns=["entity_id", "alias", "birth_year", "birth_month"])


def _token_frame(names: pd.Series, drop: set[str]) -> tuple[pd.DataFrame, list[str]]:
    """Explode names into transliteration keys and return normalised names."""
    normalised = []
    idx, keys = [], []
    for position, name in enumerate(names):
        tokens = [t for t in name_tokens(name) if t not in drop]
        normalised.append(" ".join(tokens))
        for key in {translit_key(t) for t in tokens if len(t) > 1}:
            if key:
                idx.append(position)
                keys.append(key)
    return pd.DataFrame({"idx": idx, "key": keys}), normalised


def _tokens_align(a: str, b: str) -> bool:
    """Every token of the shorter name must have a counterpart in the longer.

    Whole string similarity can be high for two people who share forenames
    but have different surnames. Requiring a counterpart for each token stops
    that. An initial counts as a counterpart of a token that starts with it.
    """
    short, long = sorted((a.split(), b.split()), key=len)
    remaining = list(long)
    for token in short:
        best, best_score = None, 0.0
        for other in remaining:
            if len(token) == 1 or len(other) == 1:
                score = 1.0 if token[0] == other[0] else 0.0
            elif translit_key(token) == translit_key(other):
                score = 1.0
            else:
                score = JaroWinkler.similarity(token, other)
            if score > best_score:
                best, best_score = other, score
        if best is None or best_score < TOKEN_SIMILARITY:
            return False
        remaining.remove(best)
    return True


def _ordered_similarity(a: str, b: str) -> float:
    """Similarity that tolerates surname first order but not arbitrary shuffles.

    Lists often print the surname first. Rotating the tokens covers that case
    without treating two people whose forenames are swapped as the same name.
    """
    tokens = b.split()
    best = fuzz.ratio(a, b)
    if len(tokens) > 1:
        best = max(best, fuzz.ratio(a, " ".join(tokens[1:] + tokens[:1])), fuzz.ratio(a, " ".join(tokens[-1:] + tokens[:-1])))
    return best / 100.0


def _candidate_pairs(left: pd.DataFrame, right: pd.DataFrame, left_sizes: np.ndarray, right_sizes: np.ndarray) -> pd.DataFrame:
    merged = left.merge(right, on="key", suffixes=("_a", "_b"))
    pairs = merged.groupby(["idx_a", "idx_b"], sort=False).size().rename("shared").reset_index()
    needed = np.minimum(2, np.minimum(left_sizes[pairs["idx_a"].to_numpy()], right_sizes[pairs["idx_b"].to_numpy()]))
    return pairs[pairs["shared"].to_numpy() >= np.maximum(needed, 1)]


def screen_persons(sanctions: pd.DataFrame, candidates: pd.DataFrame, cfg: ResolutionConfig) -> pd.DataFrame:
    """Screen person candidates against listed persons.

    candidates needs node_key, name, dob_year and dob_month. A dob_year of
    zero means the source carries no date of birth for that candidate.
    """
    aliases = _alias_table(sanctions, "Person")
    if aliases.empty or candidates.empty:
        return pd.DataFrame(columns=MATCH_COLUMNS)
    cand = candidates.reset_index(drop=True)
    left, cand_norm = _token_frame(cand["name"], set())
    right, alias_norm = _token_frame(aliases["alias"], set())
    left_sizes = np.array([len(n.split()) for n in cand_norm])
    right_sizes = np.array([len(n.split()) for n in alias_norm])
    pairs = _candidate_pairs(left, right, left_sizes, right_sizes)
    c_year = cand["dob_year"].to_numpy()
    c_month = cand["dob_month"].to_numpy()
    a_year = aliases["birth_year"].to_numpy()
    a_month = aliases["birth_month"].to_numpy()
    rows = []
    for ia, ib in zip(pairs["idx_a"].to_numpy(), pairs["idx_b"].to_numpy()):
        a, b = cand_norm[ia], alias_norm[ib]
        if not _tokens_align(a, b):
            continue
        same_shape = left_sizes[ia] == right_sizes[ib]
        sort_score = _ordered_similarity(a, b)
        name_score = sort_score if same_shape else 0.5 * sort_score + 0.5 * fuzz.token_set_ratio(a, b) / 100.0
        if name_score < cfg.sanctions_review_threshold:
            continue
        cy, cm, ay, am = int(c_year[ia]), int(c_month[ia]), int(a_year[ib]), int(a_month[ib])
        year_ok = cy > 0 and cy == ay
        month_ok = year_ok and am > 0 and cm == am
        if not same_shape:
            # One side lacks a middle name, so only a full birth date can support it.
            if not month_ok:
                continue
            status, score = "birth year and month agree, name shorter on one side", min(name_score, cfg.name_only_cap)
        elif cy == 0:
            if sort_score < STRICT_NAME_SIMILARITY:
                continue
            status, score = "no date of birth on source", min(name_score, cfg.name_only_cap)
        elif ay == 0:
            if sort_score < STRICT_NAME_SIMILARITY:
                continue
            status, score = "no date of birth on list", min(name_score, cfg.name_only_cap)
        elif month_ok:
            status, score = "birth year and month agree", min(1.0, name_score + 0.04)
        elif year_ok and (am == 0 or cm == 0):
            status, score = "birth year agrees", name_score
        elif year_ok and sort_score >= STRICT_NAME_SIMILARITY:
            status, score = "birth year agrees but month differs", name_score * 0.85
        else:
            continue
        if score < cfg.sanctions_review_threshold:
            continue
        rows.append((aliases["entity_id"].iat[ib], cand["node_key"].iat[ia], round(score, 4), round(name_score, 4), status, aliases["alias"].iat[ib], cand["name"].iat[ia]))
    return _finalise(rows, cfg)


def screen_entities(sanctions: pd.DataFrame, candidates: pd.DataFrame, cfg: ResolutionConfig) -> pd.DataFrame:
    """Screen companies and other legal entities against listed entities."""
    aliases = _alias_table(sanctions, "Company")
    if aliases.empty or candidates.empty:
        return pd.DataFrame(columns=MATCH_COLUMNS)
    cand = candidates.reset_index(drop=True)
    left, cand_norm = _token_frame(cand["name"].map(norm_company_name), LEGAL_FORM_TOKENS)
    right, alias_norm = _token_frame(aliases["alias"].map(norm_company_name), LEGAL_FORM_TOKENS)
    left_sizes = np.array([len(n.split()) for n in cand_norm])
    right_sizes = np.array([len(n.split()) for n in alias_norm])
    pairs = _candidate_pairs(left, right, left_sizes, right_sizes)
    rows = []
    for ia, ib in zip(pairs["idx_a"].to_numpy(), pairs["idx_b"].to_numpy()):
        if not _tokens_align(cand_norm[ia], alias_norm[ib]):
            continue
        score = fuzz.token_sort_ratio(cand_norm[ia], alias_norm[ib]) / 100.0
        if score < STRICT_NAME_SIMILARITY:
            continue
        rows.append((aliases["entity_id"].iat[ib], cand["node_key"].iat[ia], round(score, 4), round(score, 4), "entity name comparison", aliases["alias"].iat[ib], cand["name"].iat[ia]))
    return _finalise(rows, cfg)


def _finalise(rows: list[tuple], cfg: ResolutionConfig) -> pd.DataFrame:
    out = pd.DataFrame(rows, columns=MATCH_COLUMNS[:-1])
    if out.empty:
        out["decision"] = []
        return out
    out = out.sort_values("score", ascending=False).drop_duplicates(["entity_id", "node_key"]).reset_index(drop=True)
    out["decision"] = np.where(out["score"] >= cfg.sanctions_threshold, "match", "review")
    return out
