import numpy as np
import pandas as pd

from veilpierce.graph.algorithms import downstream_reach, find_cycle, ownership_cycles, ownership_profile, path_to_source, upstream_edges
from veilpierce.graph.store import KnowledgeGraph


def make_graph():
    """Small hand built graph.

    Persons P0 and P1, companies C0 to C5, offshore entity O0.
    P0 controls C0, C0 controls C1 (a clean chain with a person on top).
    C2 controls C3, C3 controls O0 through leak data, O0 controls C2 (a loop).
    P1 is an officer of C4 and C4 controls C5.
    """
    kinds = ["person", "person", "company", "company", "company", "company", "company", "company", "offshore"]
    keys = ["P:0", "P:1", "C:0", "C:1", "C:2", "C:3", "C:4", "C:5", "O:0"]
    nodes = pd.DataFrame({"kind": kinds, "key": keys, "label": keys, "jurisdiction": [""] * 8 + ["SEYCHELLES"], "opacity": [0.0] * 8 + [0.9]})
    rows = [
        (0, 2, "controls"), (2, 3, "controls"),
        (4, 5, "controls"), (5, 8, "leak_officer_of"), (8, 4, "controls"),
        (1, 6, "officer_of"), (6, 7, "controls"),
    ]
    edges = pd.DataFrame(rows, columns=["src", "dst", "etype"])
    edges["text"] = ""
    edges["band"] = 0.875
    edges["date"] = pd.NaT
    edges["record"] = ""
    edges["confidence"] = 1.0
    return KnowledgeGraph(nodes, edges)


def test_cycles_are_found_only_where_they_exist():
    graph = make_graph()
    component, sizes = ownership_cycles(graph)
    looped = {graph.key[i] for i in np.flatnonzero(sizes > 1)}
    assert looped == {"C:2", "C:3", "O:0"}
    loop = find_cycle(graph, graph.node_id("C:2"), component)
    assert len(loop) == 3
    assert [graph.key[graph.src[e]] for e in loop] == ["C:2", "C:3", "O:0"]
    assert find_cycle(graph, graph.node_id("C:0"), component) == []


def test_downstream_reach_follows_control_direction_and_counts_hops():
    graph = make_graph()
    dist, pred, origin = downstream_reach(graph, np.array([graph.node_id("P:1")]), np.array([0.9]), max_hops=4)
    assert dist[graph.node_id("C:4")] == 1
    assert dist[graph.node_id("C:5")] == 2
    assert dist[graph.node_id("C:0")] == -1
    assert origin[graph.node_id("C:5")] == graph.node_id("P:1")
    path = path_to_source(graph, graph.node_id("C:5"), pred)
    assert [graph.key[graph.dst[e]] for e in path] == ["C:4", "C:5"]
    limited, _, _ = downstream_reach(graph, np.array([graph.node_id("P:1")]), np.array([0.9]), max_hops=1)
    assert limited[graph.node_id("C:5")] == -1


def test_reach_never_travels_upstream():
    graph = make_graph()
    dist, _, _ = downstream_reach(graph, np.array([graph.node_id("C:1")]), np.array([1.0]), max_hops=4)
    assert dist[graph.node_id("C:0")] == -1 and dist[graph.node_id("P:0")] == -1


def test_ownership_profile_separates_clean_chains_from_opaque_ones():
    graph = make_graph()
    profile = ownership_profile(graph, max_depth=6)
    declared = profile["declared_depth"]
    assert declared[graph.node_id("C:0")] == 1
    assert declared[graph.node_id("C:1")] == 2
    assert declared[graph.node_id("C:2")] == 7
    assert declared[graph.node_id("C:5")] == 7
    assert profile["upstream_opacity"][graph.node_id("C:2")] == np.float32(0.9)
    assert profile["upstream_opacity"][graph.node_id("C:1")] == 0.0
    assert profile["chain_depth"][graph.node_id("C:1")] == 1


def test_upstream_walk_and_persistence(tmp_path):
    graph = make_graph()
    found = upstream_edges(graph, graph.node_id("C:1"), max_depth=5)
    assert [(graph.key[graph.src[e]], depth) for e, depth in found] == [("C:0", 1), ("P:0", 2)]
    graph.save(tmp_path / "graph.joblib")
    loaded = KnowledgeGraph.load(tmp_path / "graph.joblib")
    assert loaded.describe() == graph.describe()
    assert list(loaded.out_edges(loaded.node_id("C:2"))) == list(graph.out_edges(graph.node_id("C:2")))
