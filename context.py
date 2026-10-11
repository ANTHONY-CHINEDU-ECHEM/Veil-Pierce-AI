"""Shared company level context computed once and reused by every detector."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Settings
from ..data.synth import Registry
from ..graph.build import ResolutionBundle
from ..graph.store import KnowledgeGraph
from .base import UK_RESIDENCE

HEALTHY_ACCOUNTS = {"SMALL", "FULL", "GROUP", "TOTAL EXEMPTION FULL", "UNAUDITED ABRIDGED", "MEDIUM"}


@dataclass
class DetectionContext:
    """Company frame plus the director and address relations as flat arrays.

    Company nodes are the first rows of the node table in registry order, so
    the row position of a company equals its node identifier.
    """

    graph: KnowledgeGraph
    settings: Settings
    cf: pd.DataFrame
    dir_person: np.ndarray
    dir_company: np.ndarray
    person_overseas: np.ndarray
    address_node: np.ndarray
    snapshot: pd.Timestamp
    n_companies: int


def build_context(registry: Registry, graph: KnowledgeGraph, bundle: ResolutionBundle, settings: Settings) -> DetectionContext:
    companies = registry.companies
    n = len(companies)
    snapshot_text = registry.meta.get("snapshot_date") or settings.synth.snapshot_date
    snapshot = pd.to_datetime(snapshot_text, format="%Y/%m/%d")
    inc = companies["incorporation_date"]
    diss = companies["dissolution_date"]
    end = diss.fillna(snapshot)
    age = (end - inc).dt.days.fillna(0).clip(lower=0).to_numpy()
    dissolved = diss.notna().to_numpy()
    accounts = companies["accounts_category"].fillna("").str.upper().to_numpy(dtype=object)
    short_life = dissolved & (age < settings.detect.short_life_days)
    no_accounts = accounts == "NO ACCOUNTS FILED"
    dormant = accounts == "DORMANT"
    cf = pd.DataFrame(
        {
            "company_number": companies["company_number"].to_numpy(dtype=object),
            "company_name": companies["company_name"].to_numpy(dtype=object),
            "age_days": age.astype(np.float32),
            "dissolved": dissolved.astype(np.float32),
            "short_life": short_life.astype(np.float32),
            "no_accounts": no_accounts.astype(np.float32),
            "dormant": dormant.astype(np.float32),
            "accounts_overdue": companies["accounts_overdue"].to_numpy(dtype=np.float32),
            "shell_like": (short_life | dormant | (no_accounts & (age >= 640))).astype(np.float32),
            "healthy_accounts": np.isin(accounts, list(HEALTHY_ACCOUNTS)).astype(np.float32),
        }
    )
    cf["inc_day"] = (inc - pd.Timestamp(1990, 1, 1)).dt.days.fillna(0).to_numpy()
    cf["diss_day"] = np.where(dissolved, (diss - pd.Timestamp(1990, 1, 1)).dt.days.fillna(0), -1)

    director = (graph.etype == "officer_of") & (graph.edges["text"].to_numpy(dtype=object) == "director")
    dir_person, dir_company = graph.src[director], graph.dst[director]

    person_overseas = np.zeros(graph.n_nodes, dtype=np.float32)
    clusters = bundle.persons.clusters
    person_nodes = np.array([graph.key_to_id[f"P:{c}"] for c in clusters["cluster_id"]], dtype=np.int64)
    residence = clusters["residence"].fillna("").str.upper().to_numpy(dtype=object)
    person_overseas[person_nodes] = (~np.isin(residence, list(UK_RESIDENCE))).astype(np.float32)

    reg = graph.etype == "registered_at"
    address_node = np.full(n, -1, dtype=np.int64)
    address_node[graph.src[reg]] = graph.dst[reg]
    return DetectionContext(graph, settings, cf, dir_person, dir_company, person_overseas, address_node, snapshot, n)


def group_mean(values: np.ndarray, groups: np.ndarray, size: int) -> np.ndarray:
    """Mean of values per integer group, zero for empty groups."""
    total = np.bincount(groups, weights=values, minlength=size)
    count = np.bincount(groups, minlength=size)
    return np.divide(total, count, out=np.zeros(size, dtype=np.float64), where=count > 0)


def group_max(values: np.ndarray, groups: np.ndarray, size: int) -> np.ndarray:
    """Maximum of values per integer group, zero for empty groups."""
    out = np.zeros(size, dtype=np.float64)
    np.maximum.at(out, groups, values)
    return out
