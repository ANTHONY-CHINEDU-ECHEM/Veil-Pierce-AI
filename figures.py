"""Charts and case pictures for the README and the docs.

Charts are drawn from the metrics dictionary alone, so they can be rebuilt
from reports/metrics.json without rerunning the pipeline. Case pictures are
drawn from the live graph and show real subgraphs found by the detectors.

Colours follow one fixed order for series and are never the only carrier of
meaning: every chart has direct value labels or a legend, and node pictures
use a different marker shape for every kind of node.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import ArrowStyle, FancyArrowPatch, FancyBboxPatch  # noqa: E402

from ..detect.base import TYPOLOGY_CODES, TYPOLOGY_TITLES  # noqa: E402
from ..detect.engine import TYPOLOGIES  # noqa: E402
from ..graph.algorithms import find_cycle, path_to_source, upstream_edges  # noqa: E402
from ..graph.store import OWNERSHIP_TYPES  # noqa: E402
from ..rag.typology import load_matrix  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3de"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]
NODE_STYLE = {
    "company": ("s", SERIES[0], "UK company"),
    "person": ("o", SERIES[1], "Person"),
    "offshore": ("D", SERIES[2], "Offshore entity"),
    "foreign": ("d", SERIES[3], "Foreign company"),
    "address": ("^", SERIES[4], "Address"),
    "leak_officer": ("p", SERIES[6], "Leak data officer"),
    "sanction": ("X", SERIES[7], "Sanctions list entry"),
}


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "text.color": INK,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_SOFT,
            "axes.titlesize": 12.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": INK_SOFT,
            "ytick.color": INK_SOFT,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "legend.frameon": False,
        }
    )


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _bar_labels(ax, bars, fmt="{:.2f}", horizontal=False) -> None:
    for bar in bars:
        value = bar.get_width() if horizontal else bar.get_height()
        if horizontal:
            ax.text(value + 0.01, bar.get_y() + bar.get_height() / 2, fmt.format(value), va="center", ha="left", fontsize=8.5, color=INK)
        else:
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.012, fmt.format(value), va="bottom", ha="center", fontsize=8.5, color=INK)


# ======================================================================= charts
def fig_architecture(out: Path) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(13.5, 5.6))
    ax.set_axis_off()
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)
    columns = [
        ("Public sources", ["Company register", "Officer appointments", "Control register", "Offshore leak data", "Sanctions lists"], SERIES[0]),
        ("Entity resolution", ["Persons by name and birth month", "Corporate controllers", "Addresses", "Sanctions screening"], SERIES[1]),
        ("Knowledge graph", ["Typed nodes and edges", "Control direction kept", "Sparse arrays", "Edge provenance"], SERIES[2]),
        ("Detectors", ["Nominee networks", "Address factories", "Circular ownership", "Sanctions proximity", "Offshore opacity", "Burst and phoenix"], SERIES[3]),
        ("Graph RAG", ["Graph retrieval to evidence", "Typology retrieval", "Narrator", "Citation verifier"], SERIES[6]),
        ("Outputs", ["Risk score and band", "Cited dossier", "Mitigation actions", "Service and CLI"], SERIES[7]),
    ]
    width, gap = 14.2, 2.6
    for index, (title, items, colour) in enumerate(columns):
        x = 1 + index * (width + gap)
        ax.add_patch(FancyBboxPatch((x, 4), width, 34, boxstyle="round,pad=0.3,rounding_size=1.2", linewidth=1.4, edgecolor=colour, facecolor="#ffffff"))
        ax.add_patch(FancyBboxPatch((x, 33.2), width, 4.8, boxstyle="round,pad=0.3,rounding_size=1.2", linewidth=0, facecolor=colour))
        ax.text(x + width / 2, 35.6, title, ha="center", va="center", fontsize=10.5, fontweight="bold", color="#ffffff")
        for row, item in enumerate(items):
            ax.text(x + width / 2, 29.6 - row * 4.9, "\n".join(textwrap.wrap(item, 21)), ha="center", va="center", fontsize=8.3, color=INK, linespacing=1.05)
        if index < len(columns) - 1:
            ax.add_patch(FancyArrowPatch((x + width + 0.5, 21), (x + width + gap - 0.5, 21), arrowstyle="simple", mutation_scale=14, color=INK_SOFT))
    ax.text(1, 41.5, "Veil Pierce AI: from raw filings to a cited dossier", fontsize=13.5, fontweight="bold", color=INK)
    ax.text(1, 1.2, "The language model sits only in the Graph RAG stage. It explains scores that the detectors computed and it cannot change them.", fontsize=9.2, color=INK_SOFT)
    return _save(fig, out / "architecture.png")


def fig_pr_curves(metrics: dict, out: Path) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    curves = metrics["detection"]["pr_curves"]
    comparison = metrics["detection"]["comparison"]
    for colour, (name, curve) in zip(SERIES, curves.items()):
        ax.plot(curve["recall"], curve["precision"], color=colour, linewidth=2, label=f"{name} (AP {comparison[name]['average_precision']:.2f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_xlim(0, 1.005)
    ax.set_ylim(0, 1.03)
    ax.set_title("Finding suspicious companies: full system against simple rules")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.13), ncol=2, fontsize=9)
    return _save(fig, out / "detection_pr_curves.png")


def fig_typology(metrics: dict, out: Path) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=(10, 4.8))
    per = metrics["detection"]["per_typology"]
    x = np.arange(len(TYPOLOGIES))
    w = 0.38
    p = ax.bar(x - w / 2 - 0.01, [per[t]["precision"] for t in TYPOLOGIES], w, color=SERIES[0], label="Precision")
    r = ax.bar(x + w / 2 + 0.01, [per[t]["recall"] for t in TYPOLOGIES], w, color=SERIES[1], label="Recall")
    _bar_labels(ax, p)
    _bar_labels(ax, r)
    ax.set_xticks(x)
    ax.set_xticklabels(["\n".join(textwrap.wrap(TYPOLOGY_TITLES[t], 18)) + f"\n(n = {per[t]['planted']:,})" for t in TYPOLOGIES], fontsize=8.8)
    ax.set_ylim(0, 1.14)
    ax.set_ylabel("Score against planted ground truth")
    ax.set_title("Detector precision and recall by typology")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="lower right", ncol=2, fontsize=9, bbox_to_anchor=(1.0, 1.0))
    return _save(fig, out / "typology_precision_recall.png")


def fig_resolution(metrics: dict, out: Path) -> Path:
    _style()
    rows = [r for r in metrics["resolution"]["nominee_recovery"]["per_person"] if r["kind"] == "nominee"]
    fig, ax = plt.subplots(figsize=(7.6, 5.6))
    true = np.array([r["true"] for r in rows])
    top = max(10, int(true.max() * 1.08)) if len(rows) else 10
    ax.plot([0, top], [0, top], color=INK_SOFT, linewidth=1, linestyle="dashed")
    ax.text(top * 0.72, top * 0.77, "all appointments seen", rotation=38, fontsize=8.5, color=INK_SOFT)
    ax.scatter(true, [r["exact"] for r in rows], s=46, color=SERIES[1], marker="s", edgecolor=SURFACE, linewidth=1, label="Largest group by exact name", zorder=3)
    ax.scatter(true, [r["resolved"] for r in rows], s=52, color=SERIES[0], marker="o", edgecolor=SURFACE, linewidth=1, label="After entity resolution", zorder=4)
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_xlabel("True number of director appointments held by the nominee")
    ax.set_ylabel("Appointments attributed to one identity")
    ax.set_title("Exact name counting hides nominee directors")
    ax.legend(loc="upper left", fontsize=9)
    return _save(fig, out / "nominee_resolution_uplift.png")


def fig_ablations(metrics: dict, out: Path) -> Path:
    _style()
    abl = metrics["ablations"]
    rows = [
        ("Nominee recall", "nominee", "recall"),
        ("Address factory recall", "address_factory", "recall"),
        ("Circular ownership recall", "circular", "recall"),
        ("Sanctions recall", "sanctions_direct_only", "recall"),
        ("Sanctions precision", "sanctions", "precision"),
        ("Opacity precision", "opaque", "precision"),
        ("Burst and phoenix precision", "phoenix_burst", "precision"),
    ]
    fig, ax = plt.subplots(figsize=(10.4, 5.6))
    y = np.arange(len(rows))[::-1]
    h = 0.38
    full = ax.barh(y + h / 2 + 0.01, [abl[k]["full"][m] for _, k, m in rows], h, color=SERIES[0], label="Full system")
    cut = ax.barh(y - h / 2 - 0.01, [abl[k]["ablated"][m] for _, k, m in rows], h, color=SERIES[1], label="Capability removed")
    _bar_labels(ax, full, horizontal=True)
    _bar_labels(ax, cut, horizontal=True)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{label}\nwithout {abl[k]['capability_removed']}" for label, k, _ in rows], fontsize=8.6)
    ax.set_xlim(0, 1.12)
    ax.set_title("What each capability buys: one removed at a time")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, fontsize=9)
    return _save(fig, out / "ablation_study.png")


def fig_sanctions(metrics: dict, out: Path) -> Path:
    _style()
    hops = metrics["screening"]["company_recall_by_hop"]
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    keys = sorted(hops, key=int)
    bars = ax.bar([f"{k} step{'s' if k != '1' else ''}\n(n = {hops[k]['companies']})" for k in keys], [hops[k]["recall"] for k in keys], color=SERIES[0], width=0.6)
    _bar_labels(ax, bars)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Share of exposed companies found")
    ax.set_xlabel("Control steps between the listed party and the company")
    ax.set_title("Sanctions exposure found at each distance from the listed party")
    ax.grid(axis="x", visible=False)
    return _save(fig, out / "sanctions_recall_by_hop.png")


def fig_retrieval(metrics: dict, out: Path) -> Path:
    _style()
    ret = metrics["retrieval"]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.6))
    ax = axes[0]
    modes = [("bm25", "BM25"), ("dense", "Dense (LSA)"), ("hybrid", "Hybrid fusion")]
    measures = [("mrr", "MRR"), ("hit_at_1", "Hit at 1"), ("hit_at_3", "Hit at 3")]
    x = np.arange(len(measures))
    w = 0.26
    for index, (mode, label) in enumerate(modes):
        bars = ax.bar(x + (index - 1) * (w + 0.015), [ret["typology_retrieval"][mode][m] for m, _ in measures], w, color=SERIES[index], label=label)
        _bar_labels(ax, bars)
    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label in measures])
    ax.set_ylim(0, 1.16)
    ax.set_title(f"Typology retrieval ({ret['typology_queries']} analyst questions)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, fontsize=8.6)
    ax = axes[1]
    order = [("exact", "Exact string"), ("word", "Whole words"), ("rrf", "Rank fusion of both"), ("blend", "Score blend of both"), ("char", "Character ngrams (default)")]
    bars = ax.barh([label for _, label in order][::-1], [ret["entity_lookup"][m]["hit_at_1"] for m, _ in order][::-1], color=SERIES[0], height=0.6)
    _bar_labels(ax, bars, horizontal=True)
    ax.set_xlim(0, 1.12)
    ax.set_title(f"Name lookup with typing noise, hit at 1 ({ret['entity_lookup_queries']:,} queries)")
    ax.grid(axis="y", visible=False)
    fig.tight_layout(w_pad=3)
    return _save(fig, out / "retrieval_quality.png")


def fig_verifier(metrics: dict, out: Path) -> Path:
    _style()
    fab = metrics["narrative"]["fabricated_claims"]
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    kinds = list(fab)[::-1]
    bars = ax.barh([f"{k} (n = {fab[k]['tested']:,})" for k in kinds], [fab[k]["detection_rate"] for k in kinds], color=SERIES[0], height=0.6)
    _bar_labels(ax, bars, fmt="{:.3f}", horizontal=True)
    ax.set_xlim(0, 1.14)
    ax.set_xlabel("Share of fabricated claims rejected")
    ax.set_title("Citation verifier against seven kinds of fabricated claim")
    ax.grid(axis="y", visible=False)
    return _save(fig, out / "verifier_fabrication_test.png")


def fig_label_budget(metrics: dict, out: Path) -> Path | None:
    _style()
    model = metrics.get("model") or {}
    if not model:
        return None
    rows = model["label_budget"]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    x = [r["share_of_positives_labelled"] for r in rows]
    y = [r["average_precision"] for r in rows]
    ax.plot(x, y, color=SERIES[0], linewidth=2, marker="o", markersize=7, label="Gradient boosted challenger")
    rule = model["rule_fusion_average_precision"]
    for xi, yi, row in zip(x, y, rows):
        above = yi >= rule
        ax.annotate(
            f"{yi:.3f}\n({row['labelled_positives']:,} cases)", (xi, yi), textcoords="offset points",
            xytext=(0, 9 if above else -11), ha="center", va="bottom" if above else "top", fontsize=8.3, color=INK,
        )
    ax.axhline(rule, color=SERIES[1], linewidth=2, linestyle="dashed", label=f"Rule fusion, no labels needed ({rule:.3f})")
    ax.set_xscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(round(100 * v))} percent" for v in x])
    ax.set_xlim(x[0] * 0.7, x[len(x) - 1] * 1.45)
    floor = max(0.0, np.floor((min(y + [rule]) - 0.04) * 20) / 20)
    ax.set_ylim(floor, 1.0 + 0.28 * (1.0 - floor))
    ax.set_yticks(np.linspace(floor, 1.0, 6))
    ax.set_xlabel("Share of suspicious companies with a confirmed label available for training")
    ax.set_ylabel("Average precision against all true labels" + (f"\n(axis starts at {floor:.2f})" if floor > 0 else ""))
    ax.set_title("How many confirmed cases the supervised model needs")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=9, ncol=2)
    return _save(fig, out / "label_budget.png")


def fig_hard_negatives(metrics: dict, out: Path) -> Path:
    _style()
    hard = metrics["detection"]["hard_negatives"]
    names = {
        "benign_agent": "Legitimate agent addresses",
        "professional_director": "Professional directors",
        "group_tree": "Ordinary group structures",
        "foreign_parent": "Listed foreign parents",
        "spv_batch": "Property vehicle batches",
        "namesake": "Namesakes of listed persons",
        "ordinary background": "Ordinary background",
    }
    keys = [k for k in names if k in hard]
    fig, ax = plt.subplots(figsize=(8.8, 4.4))
    bars = ax.barh([f"{names[k]} (n = {hard[k]['companies']:,})" for k in keys][::-1], [100 * hard[k]["alert_rate"] for k in keys][::-1], color=SERIES[0], height=0.6)
    _bar_labels(ax, bars, fmt="{:.2f}", horizontal=True)
    ax.set_xlabel("Percent of companies alerted")
    ax.set_xlim(0, max(1.0, 1.25 * max(100 * hard[k]["alert_rate"] for k in keys) + 0.3))
    ax.set_title("False alert rate on the lookalikes planted to fool each detector")
    ax.grid(axis="y", visible=False)
    return _save(fig, out / "hard_negative_alert_rates.png")


def fig_mitigation_heatmap(out: Path) -> Path:
    _style()
    matrix = load_matrix()
    fig, ax = plt.subplots(figsize=(9.2, 7.2))
    for likelihood in range(1, 6):
        for impact in range(1, 6):
            level = min(5, (likelihood * impact - 1) // 5)
            ax.add_patch(plt.Rectangle((likelihood - 0.5, impact - 0.5), 1, 1, facecolor=BLUE_RAMP[level], edgecolor=SURFACE, linewidth=2))
    offsets = {
        "nominee": (-0.25, 0.22), "opaque": (0.25, -0.22), "circular": (-0.25, -0.22),
        "sanctions": (0.2, 0.22), "phoenix_burst": (-0.25, 0.22), "address_factory": (0.25, -0.22),
    }
    for row in matrix["fraud_vectors"]:
        code = TYPOLOGY_CODES[row["typology"]]
        dx, dy = offsets.get(row["typology"], (0.0, 0.0))
        (l0, i0), (l1, i1) = row["inherent"], row["residual"]
        ax.annotate("", xy=(l1 + dx, i1 + dy), xytext=(l0 + dx, i0 + dy), arrowprops={"arrowstyle": "simple", "color": INK, "alpha": 0.55, "mutation_scale": 11})
        ax.scatter([l0 + dx], [i0 + dy], s=420, facecolor="#ffffff", edgecolor=INK, linewidth=1.6, zorder=3)
        ax.scatter([l1 + dx], [i1 + dy], s=420, facecolor=INK, edgecolor="#ffffff", linewidth=1.6, zorder=4)
        ax.text(l0 + dx, i0 + dy, code, ha="center", va="center", fontsize=7.6, fontweight="bold", color=INK, zorder=5)
        ax.text(l1 + dx, i1 + dy, code, ha="center", va="center", fontsize=7.6, fontweight="bold", color="#ffffff", zorder=5)
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xticklabels(["1\nrare", "2\nunlikely", "3\npossible", "4\nlikely", "5\nfrequent"])
    ax.set_yticklabels(["1 minor", "2 moderate", "3 serious", "4 major", "5 severe"])
    ax.set_xlabel("Likelihood")
    ax.set_ylabel("Impact")
    ax.grid(False)
    ax.set_title("Mitigation matrix: inherent risk (open) to residual risk (filled)")
    entries = [f"{TYPOLOGY_CODES[r['typology']]}  {r['vector']}" for r in matrix["fraud_vectors"]]
    lines = ["      ".join(entries[i: i + 3]) for i in range(0, len(entries), 3)]
    fig.text(0.5, 0.0, "\n".join(lines), ha="center", va="top", fontsize=8.4, color=INK_SOFT, linespacing=1.6)
    return _save(fig, out / "mitigation_matrix_heatmap.png")


def chart_figures(metrics: dict, out_dir: str | Path) -> list[Path]:
    """Draw every chart that needs only the metrics dictionary."""
    out = Path(out_dir)
    made = [
        fig_architecture(out), fig_pr_curves(metrics, out), fig_typology(metrics, out), fig_resolution(metrics, out),
        fig_ablations(metrics, out), fig_sanctions(metrics, out), fig_retrieval(metrics, out), fig_verifier(metrics, out),
        fig_hard_negatives(metrics, out), fig_mitigation_heatmap(out),
    ]
    budget = fig_label_budget(metrics, out)
    return made + ([budget] if budget else [])


# ================================================================ case pictures
def _wrap(label: str, width: int = 17) -> str:
    return "\n".join(textwrap.wrap(str(label).title() if str(label).isupper() else str(label), width)[:3])


def _draw(graph, edges: list[int], pos: dict[int, tuple[float, float]], title: str, note: str, path: Path, extra_labels: dict[int, str] | None = None, size=(11, 6.6)) -> Path:
    _style()
    fig, ax = plt.subplots(figsize=size)
    ax.set_axis_off()
    net = nx.DiGraph()
    for eid in edges:
        net.add_edge(int(graph.src[eid]), int(graph.dst[eid]), kind=graph.etype[eid])
    for node in pos:
        net.add_node(node)
    edge_colours = {"sanctions_match": SERIES[7], "registered_at": GRID, "officer_of": INK_SOFT}
    for u, v, data in net.edges(data=True):
        dashed = data["kind"] in ("leak_officer_of", "leak_shareholder_of", "sanctions_match")
        ax.annotate(
            "", xy=pos[v], xytext=pos[u],
            arrowprops={"arrowstyle": ArrowStyle.CurveFilledB(head_length=0.55, head_width=0.22), "mutation_scale": 13, "color": edge_colours.get(data["kind"], INK), "alpha": 0.8,
                        "linestyle": (0, (4, 3)) if dashed else "solid", "shrinkA": 15, "shrinkB": 15, "linewidth": 1.5},
        )
    kinds_seen = []
    for kind, (marker, colour, _) in NODE_STYLE.items():
        nodes = [n for n in net.nodes if graph.kind[n] == kind]
        if not nodes:
            continue
        kinds_seen.append(kind)
        ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes], s=520, marker=marker, color=colour, edgecolor=SURFACE, linewidth=2, zorder=3)
    for node in net.nodes:
        label = (extra_labels or {}).get(node) or _wrap(graph.label[node])
        ax.text(
            pos[node][0], pos[node][1] - 0.115, label, ha="center", va="top", fontsize=7.4, color=INK, zorder=4,
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.2, "alpha": 0.88},
        )
    handles = [plt.Line2D([0], [0], marker=NODE_STYLE[k][0], color="none", markerfacecolor=NODE_STYLE[k][1], markeredgecolor=SURFACE, markersize=11, label=NODE_STYLE[k][2]) for k in kinds_seen]
    handles.append(plt.Line2D([0], [0], color=INK, linewidth=1.6, label="Register record"))
    handles.append(plt.Line2D([0], [0], color=INK, linewidth=1.6, linestyle="dashed", label="Leak data or screening match"))
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 0.0), ncol=4, fontsize=8.4)
    xs, ys = [p[0] for p in pos.values()], [p[1] for p in pos.values()]
    ax.set_xlim(min(xs) - 0.35, max(xs) + 0.35)
    ax.set_ylim(min(ys) - 0.42, max(ys) + 0.3)
    wrapped = textwrap.wrap(note, int(size[0] * 13))
    ax.set_title(title, pad=16 + 13 * len(wrapped))
    ax.text(0.0, 1.015, "\n".join(wrapped), transform=ax.transAxes, fontsize=9, color=INK_SOFT, va="bottom", ha="left")
    return _save(fig, path)


def _ring_layout(nodes: list[int], radius: float = 1.0, centre=(0.0, 0.0), start: float = np.pi / 2) -> dict[int, tuple[float, float]]:
    return {n: (centre[0] + radius * np.cos(start - 2 * np.pi * i / len(nodes)), centre[1] + radius * np.sin(start - 2 * np.pi * i / len(nodes))) for i, n in enumerate(nodes)}


def case_figures(state, out_dir: str | Path) -> dict[str, dict]:
    """Draw one real example of each main typology from the current run."""
    out = Path(out_dir)
    graph, det = state.graph, state.detection
    cf = det.companies
    made: dict[str, dict] = {}

    # Circular ownership, preferring a loop that passes through an offshore entity.
    pool = cf[(cf["flag_circular"]) & (cf["cycle_offshore"] > 0) & (cf["cycle_size"].between(4, 6))]
    if pool.empty:
        pool = cf[cf["flag_circular"]]
    if len(pool):
        node = int(pool.index[0])
        loop = find_cycle(graph, node, det.component)
        members = [int(graph.src[e]) for e in loop]
        directors = []
        for member in members:
            if graph.kind[member] == "company":
                directors.extend(int(e) for e in graph.in_edges(member, ("officer_of",))[:1])
        people = list(dict.fromkeys(int(graph.src[e]) for e in directors))
        pos = _ring_layout(members, 1.0)
        pos.update({p: (0.0 + 0.32 * i, 0.0) for i, p in enumerate(people[:2])})
        directors = [e for e in directors if int(graph.src[e]) in pos]
        made["circular"] = {"company_number": cf["company_number"].iat[node], "links": len(loop)}
        _draw(
            graph, loop + directors, pos, "Example found: circular ownership through an offshore entity",
            f"A loop of {len(loop)} control links. Each arrow points from the controller to the controlled entity. No natural person owns anything on the loop.",
            out / "case_circular_ownership.png", size=(10.4, 7.6),
        )

    # Nominee hub.
    if len(det.persons) and det.persons["nominee_score"].max() > 0:
        person = int(det.persons["nominee_score"].idxmax())
        stats = det.persons.loc[person]
        edges = [int(e) for e in graph.out_edges(person, ("officer_of",))[:16]]
        companies = [int(graph.dst[e]) for e in edges]
        pos = _ring_layout(companies, 1.25)
        pos[person] = (0.0, 0.0)
        label = {person: f"{_wrap(graph.label[person])}\n{int(stats['n_companies'])} appointments"}
        made["nominee"] = {
            "company_number": cf["company_number"].iat[companies[0]], "person": graph.key[person],
            "appointments": int(stats["n_companies"]), "shell_ratio": float(stats["shell_ratio"]),
        }
        _draw(
            graph, edges, pos, "Example found: one resolved person fronting a network of companies",
            f"16 of {int(stats['n_companies'])} director appointments shown. {int(round(100 * stats['shell_ratio']))} percent of the companies are shell like and the person is the sole director of {int(round(100 * stats['sole_ratio']))} percent.",
            out / "case_nominee_network.png", extra_labels=label, size=(10.4, 8.2),
        )

    # Sanctions path, preferring the longest chains.
    pool = cf[cf["flag_sanctions"]].sort_values(["sanction_hops", "score_sanctions"], ascending=[False, False])
    if len(pool):
        node = int(pool.index[0])
        path = path_to_source(graph, node, det.reach["pred"])
        origin = int(det.reach["origin"][node])
        match_edges = graph.in_edges(origin, ("sanctions_match",))
        best = int(match_edges[np.argmax(graph.edges["confidence"].to_numpy()[match_edges])])
        chain = [int(graph.src[best]), origin] + [int(graph.dst[e]) for e in path]
        pos = {n: (i * 1.0, 0.18 * (1 if i % 2 else -1)) for i, n in enumerate(chain)}
        made["sanctions"] = {"company_number": cf["company_number"].iat[node], "hops": len(path), "match_score": float(graph.edges["confidence"].iat[best])}
        _draw(
            graph, [best] + [int(e) for e in path], pos, "Example found: sanctions exposure several control steps away",
            f"The company on the right is {len(path)} control steps downstream of a party that matches a list entry with score {graph.edges['confidence'].iat[best]:.2f}. Screening the company name alone finds nothing.",
            out / "case_sanctions_path.png", size=(12.6, 4.6),
        )

    # Address factory hub.
    if len(det.addresses) and det.addresses["factory_score"].max() > 0:
        address = int(det.addresses["factory_score"].idxmax())
        stats = det.addresses.loc[address]
        edges = [int(e) for e in graph.in_edges(address, ("registered_at",))[:14]]
        companies = [int(graph.src[e]) for e in edges]
        officer_edges, people = [], []
        for company in companies:
            for e in graph.in_edges(company, ("officer_of",))[:1]:
                officer_edges.append(int(e))
                people.append(int(graph.src[e]))
        pos = _ring_layout(companies, 1.0)
        angles: dict[int, list[float]] = {}
        for e in officer_edges:
            x, y = pos[int(graph.dst[e])]
            angles.setdefault(int(graph.src[e]), []).append(float(np.arctan2(y, x)))
        for person, values in angles.items():
            angle = float(np.arctan2(np.mean(np.sin(values)), np.mean(np.cos(values))))
            pos[person] = (1.75 * np.cos(angle), 1.75 * np.sin(angle))
        pos[address] = (0.0, 0.0)
        label = {address: f"{_wrap(graph.label[address], 22)}\n{int(stats['n_companies'])} companies"}
        made["address_factory"] = {
            "company_number": cf["company_number"].iat[companies[0]], "address": graph.label[address],
            "companies": int(stats["n_companies"]), "shell_ratio": float(stats["shell_ratio"]),
        }
        _draw(
            graph, edges + officer_edges, pos, "Example found: a mass registration address",
            f"14 of {int(stats['n_companies'])} companies at one resolved address, with a director of each. {int(round(100 * stats['shell_ratio']))} percent of all companies here are shell like and {int(round(100 * stats['overseas_ratio']))} percent of directors live overseas.",
            out / "case_address_factory.png", extra_labels=label, size=(11, 9),
        )

    # Opaque chain with a controller that only the leak data shows.
    pool = cf[(cf["flag_opaque"]) & (cf["hidden_controller_in_leak"] > 0) & (cf["chain_depth"] >= 2)]
    if pool.empty:
        pool = cf[cf["flag_opaque"] & (cf["hidden_controller_in_leak"] > 0)]
    if len(pool):
        node = int(pool.index[0])
        found = upstream_edges(graph, node, 4, OWNERSHIP_TYPES, limit=8)
        depth = {node: 0}
        for eid, d in found:
            depth.setdefault(int(graph.src[eid]), d)
        levels: dict[int, list[int]] = {}
        for n, d in depth.items():
            levels.setdefault(d, []).append(n)
        pos = {}
        for d, nodes in levels.items():
            for i, n in enumerate(nodes):
                pos[n] = ((i - (len(nodes) - 1) / 2) * 1.15, d * 0.8)
        made["opaque"] = {"company_number": cf["company_number"].iat[node], "chain_depth": int(cf["chain_depth"].iat[node])}
        _draw(
            graph, [e for e, _ in found], pos, "Example found: an offshore owner with a controller only the leak data names",
            "Solid arrows are records in the UK control register. Dashed arrows come from leak data. The register alone ends at the offshore entity.",
            out / "case_opaque_chain.png", size=(9.6, 7.4),
        )
    pool = cf[(cf["flag_phoenix_burst"]) & (cf["phoenix_link"] > 0)].sort_values("risk_rules", ascending=False)
    if len(pool):
        made["phoenix_burst"] = {"company_number": pool["company_number"].iat[0]}
    return made
