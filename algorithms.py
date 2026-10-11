"""Graph algorithms used by the detectors and by graph retrieval.

All bulk algorithms are vectorised over the edge arrays. Path extraction for
a single entity (used when a dossier is written) walks the compressed
indexes directly, which is fast because one neighbourhood is small.
"""

from __future__ import annotations

from collections import deque

import numpy as np
from scipy.sparse.csgraph import connected_components

from .store import CONTROL_TYPES, NATURAL_PERSON_KINDS, OWNERSHIP_TYPES, KnowledgeGraph


def ownership_cycles(graph: KnowledgeGraph) -> tuple[np.ndarray, np.ndarray]:
    """Find groups of entities that own each other in a loop.

    Returns the strongly connected component of every node in the ownership
    graph and the size of that component. A size above one means the node sits
    on at least one ownership cycle.
    """
    matrix = graph.matrix(OWNERSHIP_TYPES)
    _, component = connected_components(matrix, directed=True, connection="strong")
    sizes = np.bincount(component)[component]
    return component, sizes


def find_cycle(graph: KnowledgeGraph, node: int, component: np.ndarray, max_length: int = 12) -> list[int]:
    """Return the edge identifiers of one shortest ownership cycle through node."""
    target_component = component[node]
    parent: dict[int, int] = {}
    queue = deque([(node, 0)])
    seen = {node}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_length:
            continue
        for eid in graph.out_edges(current, OWNERSHIP_TYPES):
            nxt = int(graph.dst[eid])
            if component[nxt] != target_component:
                continue
            if nxt == node:
                path = [int(eid)]
                walk = current
                while walk != node:
                    back = parent[walk]
                    path.append(back)
                    walk = int(graph.src[back])
                return path[::-1]
            if nxt not in seen:
                seen.add(nxt)
                parent[nxt] = int(eid)
                queue.append((nxt, depth + 1))
    return []


def downstream_reach(
    graph: KnowledgeGraph,
    sources: np.ndarray,
    confidence: np.ndarray,
    max_hops: int,
    etypes: tuple[str, ...] = CONTROL_TYPES,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Breadth first search that follows the direction of control.

    Starting from the source nodes, each step moves from a controller to the
    entities it controls. Returns for every node the hop distance (zero for a
    source, minus one when unreachable), the edge used to reach it and the
    source node it descends from. When several sources reach a node at the
    same distance, the source with the highest confidence wins.
    """
    n = graph.n_nodes
    dist = np.full(n, -1, dtype=np.int16)
    pred = np.full(n, -1, dtype=np.int64)
    origin = np.full(n, -1, dtype=np.int64)
    if len(sources) == 0:
        return dist, pred, origin
    conf = np.zeros(n, dtype=np.float32)
    order = np.argsort(-np.asarray(confidence), kind="stable")
    sources = np.asarray(sources)[order]
    conf_sorted = np.asarray(confidence, dtype=np.float32)[order]
    first = np.unique(sources, return_index=True)[1]
    sources, conf_sorted = sources[np.sort(first)], conf_sorted[np.sort(first)]
    dist[sources] = 0
    origin[sources] = sources
    conf[sources] = conf_sorted
    allowed = graph.edge_mask(etypes)
    frontier = sources
    for hop in range(1, max_hops + 1):
        if len(frontier) == 0:
            break
        frontier = frontier[np.argsort(-conf[frontier], kind="stable")]
        starts, ends = graph.out_ptr[frontier], graph.out_ptr[frontier + 1]
        counts = ends - starts
        if counts.sum() == 0:
            break
        offsets = np.repeat(starts, counts) + (np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts))
        eids = graph.out_order[offsets]
        eids = eids[allowed[eids]]
        targets = graph.dst[eids]
        fresh = dist[targets] == -1
        eids, targets = eids[fresh], targets[fresh]
        uniq, first_pos = np.unique(targets, return_index=True)
        dist[uniq] = hop
        pred[uniq] = eids[first_pos]
        origin[uniq] = origin[graph.src[eids[first_pos]]]
        conf[uniq] = conf[origin[uniq]]
        frontier = uniq
    return dist, pred, origin


def path_to_source(graph: KnowledgeGraph, node: int, pred: np.ndarray) -> list[int]:
    """Edge identifiers from the originating source down to node."""
    path = []
    current = node
    guard = 0
    while pred[current] != -1 and guard < 32:
        eid = int(pred[current])
        path.append(eid)
        current = int(graph.src[eid])
        guard += 1
    return path[::-1]


def ownership_profile(graph: KnowledgeGraph, max_depth: int) -> dict[str, np.ndarray]:
    """Summarise the ownership chain above every node.

    declared_depth is the number of ownership steps from a node up to the
    nearest natural person using registry control records only. leak_depth
    allows leak data edges as well. chain_depth is the longest chain of
    corporate owners above the node and upstream_opacity is the highest
    jurisdiction opacity weight found anywhere above it. Depth values equal
    to max_depth plus one mean no natural person was reached.
    """
    n = graph.n_nodes
    is_person = np.isin(graph.kind, NATURAL_PERSON_KINDS)
    weights = graph.nodes["opacity"].to_numpy(dtype=np.float32)
    unreachable = max_depth + 1
    out: dict[str, np.ndarray] = {}
    for name, etypes in (("declared_depth", ("controls",)), ("leak_depth", OWNERSHIP_TYPES)):
        mask = graph.edge_mask(etypes)
        src, dst = graph.src[mask], graph.dst[mask]
        depth = np.full(n, unreachable, dtype=np.int16)
        depth[is_person] = 0
        for _ in range(max_depth):
            candidate = np.minimum(depth[src] + 1, unreachable).astype(np.int16)
            before = depth.copy()
            np.minimum.at(depth, dst, candidate)
            if np.array_equal(before, depth):
                break
        out[name] = depth
    mask = graph.edge_mask(OWNERSHIP_TYPES) & ~is_person[graph.src]
    src, dst = graph.src[mask], graph.dst[mask]
    chain = np.zeros(n, dtype=np.int16)
    upstream = np.zeros(n, dtype=np.float32)
    for _ in range(max_depth):
        np.maximum.at(chain, dst, np.minimum(chain[src] + 1, max_depth).astype(np.int16))
        np.maximum.at(upstream, dst, np.maximum(upstream[src], weights[src]))
    out["chain_depth"] = chain
    out["upstream_opacity"] = upstream
    return out


def upstream_edges(graph: KnowledgeGraph, node: int, max_depth: int, etypes: tuple[str, ...] = OWNERSHIP_TYPES, limit: int = 60) -> list[tuple[int, int]]:
    """Walk up the ownership chain from node and return (edge, depth) pairs."""
    found: list[tuple[int, int]] = []
    seen_nodes = {node}
    seen_edges: set[int] = set()
    queue = deque([(node, 1)])
    while queue and len(found) < limit:
        current, depth = queue.popleft()
        if depth > max_depth:
            continue
        for eid in graph.in_edges(current, etypes):
            eid = int(eid)
            if eid in seen_edges:
                continue
            seen_edges.add(eid)
            found.append((eid, depth))
            parent = int(graph.src[eid])
            if parent not in seen_nodes:
                seen_nodes.add(parent)
                queue.append((parent, depth + 1))
    return found
