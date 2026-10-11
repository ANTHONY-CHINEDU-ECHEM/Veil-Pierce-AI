"""In memory knowledge graph built on numpy arrays and sparse matrices.

The graph holds several hundred thousand nodes and more than a million typed
edges, so it is stored as flat arrays with compressed row indexes instead of
Python objects. Node and edge attributes stay in pandas tables keyed by
integer identifiers, which keeps traversals vectorised and the whole graph
small enough to serialise in a single file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

NODE_KINDS = ("company", "person", "address", "offshore", "foreign", "leak_officer", "sanction")
EDGE_TYPES = ("officer_of", "controls", "registered_at", "leak_officer_of", "leak_shareholder_of", "sanctions_match")
OWNERSHIP_TYPES = ("controls", "leak_officer_of", "leak_shareholder_of")
CONTROL_TYPES = ("officer_of", "controls", "leak_officer_of", "leak_shareholder_of")
NATURAL_PERSON_KINDS = ("person", "leak_officer")


@dataclass
class KnowledgeGraph:
    """Typed property graph.

    nodes has one row per node (kind, key, label, jurisdiction, opacity).
    edges has one row per directed edge from src to dst. For control edges
    the direction is always controller to controlled.
    """

    nodes: pd.DataFrame
    edges: pd.DataFrame
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._index()

    def _index(self) -> None:
        n = len(self.nodes)
        self.n_nodes = n
        self.kind = self.nodes["kind"].to_numpy(dtype=object)
        self.key = self.nodes["key"].to_numpy(dtype=object)
        self.label = self.nodes["label"].to_numpy(dtype=object)
        self.key_to_id = dict(zip(self.key, range(n)))
        self.src = self.edges["src"].to_numpy(dtype=np.int64)
        self.dst = self.edges["dst"].to_numpy(dtype=np.int64)
        self.etype = self.edges["etype"].to_numpy(dtype=object)
        self.out_order = np.argsort(self.src, kind="stable")
        self.out_ptr = np.searchsorted(self.src[self.out_order], np.arange(n + 1))
        self.in_order = np.argsort(self.dst, kind="stable")
        self.in_ptr = np.searchsorted(self.dst[self.in_order], np.arange(n + 1))

    # ================================================================== lookup
    def node_id(self, key: str) -> int:
        return self.key_to_id[key]

    def has(self, key: str) -> bool:
        return key in self.key_to_id

    def ids_of_kind(self, kind: str) -> np.ndarray:
        return np.flatnonzero(self.kind == kind)

    def out_edges(self, node: int, etypes: tuple[str, ...] | None = None) -> np.ndarray:
        """Edge identifiers that leave a node, optionally filtered by type."""
        eids = self.out_order[self.out_ptr[node]: self.out_ptr[node + 1]]
        if etypes is None:
            return eids
        return eids[np.isin(self.etype[eids], etypes)]

    def in_edges(self, node: int, etypes: tuple[str, ...] | None = None) -> np.ndarray:
        """Edge identifiers that arrive at a node, optionally filtered by type."""
        eids = self.in_order[self.in_ptr[node]: self.in_ptr[node + 1]]
        if etypes is None:
            return eids
        return eids[np.isin(self.etype[eids], etypes)]

    def edge_mask(self, etypes: tuple[str, ...]) -> np.ndarray:
        return np.isin(self.etype, etypes)

    def matrix(self, etypes: tuple[str, ...]) -> csr_matrix:
        """Sparse adjacency matrix for the chosen edge types (src rows, dst columns)."""
        mask = self.edge_mask(etypes)
        data = np.ones(int(mask.sum()), dtype=np.int8)
        return csr_matrix((data, (self.src[mask], self.dst[mask])), shape=(self.n_nodes, self.n_nodes))

    def edge_row(self, eid: int) -> dict:
        row = self.edges.iloc[int(eid)]
        return row.to_dict()

    def describe(self) -> dict:
        return {
            "nodes": int(self.n_nodes),
            "edges": int(len(self.edges)),
            "nodes_by_kind": {k: int(v) for k, v in pd.Series(self.kind).value_counts().items()},
            "edges_by_type": {k: int(v) for k, v in pd.Series(self.etype).value_counts().items()},
        }

    # ============================================================= persistence
    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"nodes": self.nodes, "edges": self.edges, "meta": self.meta}, path, compress=3)

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeGraph":
        payload = joblib.load(path)
        return cls(payload["nodes"], payload["edges"], payload.get("meta", {}))
