"""Generates the knowledge documents from the packaged knowledge files.

The mitigation matrix and the typology library live in JSON so that code can
use them. This module renders them as Markdown so that people can read them,
which keeps the documentation and the behaviour of the system in step.
"""

from __future__ import annotations

from pathlib import Path

from .detect.base import TYPOLOGY_CODES, TYPOLOGY_TITLES
from .rag.report import html_table
from .rag.typology import load_cards, load_matrix


def score(pair: list[int]) -> str:
    return f"{pair[0]} x {pair[1]} = {pair[0] * pair[1]}"


def mitigation_tables() -> dict[str, str]:
    """The three tables of the mitigation matrix as HTML."""
    matrix = load_matrix()
    vectors = matrix["fraud_vectors"]
    detect = html_table(
        ["Code", "Fraud vector", "How it works", "Graph signal", "Detection logic"],
        [[TYPOLOGY_CODES[r["typology"]], r["vector"], r["how_it_works"], r["graph_signal"], r["detection"]] for r in vectors],
    )
    control = html_table(
        ["Code", "Preventive control", "Detective control", "Corrective action", "Owner", "Regulatory anchor", "KPI", "Inherent risk", "Residual risk"],
        [
            [TYPOLOGY_CODES[r["typology"]], r["preventive"], r["detective"], r["corrective"], r["owner"], r["anchor"], r["kpi"], score(r["inherent"]), score(r["residual"])]
            for r in vectors
        ],
    )
    system = html_table(
        ["System risk", "Impact", "Mitigation", "Implemented in", "Tested by", "Inherent risk", "Residual risk"],
        [[r["risk"], r["impact"], r["mitigation"], r["implemented_in"], r["test"], score(r["inherent"]), score(r["residual"])] for r in matrix["system_risks"]],
    )
    return {"detect": detect, "control": control, "system": system, "note": matrix["note"]}


def mitigation_markdown() -> str:
    tables = mitigation_tables()
    return "\n".join(
        [
            "# Mitigation matrix",
            "",
            "This document is generated from veilpierce/knowledge/mitigation_matrix.json by the command veilpierce docs. Edit the JSON file, not this page.",
            "",
            tables["note"] + " Risk is written as likelihood x impact.",
            "",
            "![Mitigation matrix heatmap](figures/mitigation_matrix_heatmap.png)",
            "",
            "## Part one: fraud vectors and how each is detected",
            "",
            tables["detect"],
            "",
            "## Part two: controls, ownership and residual risk",
            "",
            tables["control"],
            "",
            "## Part three: risks of the language model and retrieval system itself",
            "",
            tables["system"],
            "",
        ]
    )


def typology_markdown() -> str:
    lines = [
        "# Typology library",
        "",
        "This document is generated from veilpierce/knowledge/typologies.json by the command veilpierce docs. The cards are summaries written for this project. They paraphrase public guidance, they are not quotations and they are not legal advice. The reading references name the documents a reviewer should consult for the authoritative text.",
        "",
    ]
    for card in load_cards():
        area = TYPOLOGY_TITLES.get(card.typology, "General guidance")
        lines += [f"## {card.id} {card.title}", "", f"Area: {area}", "", card.summary, "", "Indicators", ""]
        lines += [f"* {item}" for item in card.indicators]
        lines += ["", f"Why it matters: {card.why}", "", "Reviewer actions", ""]
        lines += [f"* {item}" for item in card.actions]
        lines += ["", "Reading references: " + "; ".join(card.sources), ""]
    return "\n".join(lines)


def write_docs(directory: str | Path, metrics: dict | None = None) -> list[Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    out = []
    pages = [("mitigation_matrix.md", mitigation_markdown()), ("typology_library.md", typology_markdown())]
    if metrics and "detection" in metrics:
        pages.append(("results.md", results_markdown(metrics)))
    for name, text in pages:
        path = root / name
        path.write_text(text, encoding="utf8")
        out.append(path)
    return out


def _f(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def results_markdown(metrics: dict) -> str:
    """Full results of a benchmark run as a Markdown document."""
    data, det, res = metrics["dataset"], metrics["detection"], metrics["resolution"]
    scr, abl, ret, nar = metrics["screening"], metrics["ablations"], metrics["retrieval"], metrics["narrative"]
    model = metrics.get("model") or {}
    run = metrics.get("runtime_seconds", {})
    lines = [
        "# Benchmark results",
        "",
        "This document is generated from reports/metrics.json by the commands veilpierce benchmark and veilpierce docs. Every figure is measured against the ground truth of a synthetic registry and describes recovery of planted structure, not performance on a live register.",
        "",
        f"Seed {data['seed']}, data snapshot {data['snapshot_date']}, configuration fingerprint {metrics.get('config_fingerprint', '')}.",
        "",
        "## Dataset and graph",
        "",
        html_table(["Table", "Rows"], [[k.replace("_", " "), f"{v:,}"] for k, v in data["tables"].items()] + [["total", f"{data['total_records']:,}"]]),
        "",
        html_table(["Node kind", "Nodes"], [[k.replace("_", " "), f"{v:,}"] for k, v in data["graph"]["nodes_by_kind"].items()] + [["total", f"{data['graph']['nodes']:,}"]]),
        "",
        html_table(["Edge type", "Edges"], [[k.replace("_", " "), f"{v:,}"] for k, v in data["graph"]["edges_by_type"].items()] + [["total", f"{data['graph']['edges']:,}"]]),
        "",
        html_table(
            ["Planted typology", "Companies"],
            [[TYPOLOGY_TITLES[t], f"{data['label_counts'][t]:,}"] for t in TYPOLOGY_TITLES]
            + [["any typology", f"{data['label_counts']['suspicious']:,}"], ["two or more typologies", f"{data['companies_with_two_or_more_typologies']:,}"]],
        ),
        "",
        html_table(["Benign lookalike", "Companies"], [[k.replace("_", " "), f"{v:,}"] for k, v in data["hard_negatives"].items()]),
        "",
        "## Entity resolution",
        "",
        html_table(
            ["Method", "Pairwise precision", "Pairwise recall", "F1", "Identities produced"],
            [
                ["Exact name and birth month", _f(res["persons"]["exact_matching"]["precision"]), _f(res["persons"]["exact_matching"]["recall"]), _f(res["persons"]["exact_matching"]["f1"]), f"{res['persons']['exact_name_groups']:,}"],
                ["Entity resolution", _f(res["persons"]["entity_resolution"]["precision"]), _f(res["persons"]["entity_resolution"]["recall"]), _f(res["persons"]["entity_resolution"]["f1"]), f"{res['persons']['resolved_persons']:,}"],
            ],
        ),
        "",
        f"The registry holds {res['persons']['records']:,} person records for {res['persons']['true_persons']:,} true persons.",
        "",
        html_table(
            ["Corporate controller resolved by", "Records", "Accuracy"],
            [[k, f"{v['records']:,}", _f(v["accuracy"])] for k, v in res["corporates"]["by_method"].items()] + [["all methods", f"{res['corporates']['records']:,}", _f(res["corporates"]["accuracy"], 4)]],
        ),
        "",
        html_table(
            ["Address measure", "Value"],
            [
                ["Planted shared addresses", str(res["addresses"]["planted_addresses"])],
                ["Mean spellings of one address in the raw data", _f(res["addresses"]["mean_raw_spellings_per_address"], 1)],
                ["Share of companies gathered under the largest raw spelling", _f(res["addresses"]["mean_share_recovered_raw"])],
                ["Share of companies gathered after address resolution", _f(res["addresses"]["mean_share_recovered_resolved"])],
                ["UK companies named as shareholders in leak data and tied back to the register", f"{res['leak_company_links']['recovered']} of {res['leak_company_links']['planted']}"],
            ],
        ),
        "",
        "## Sanctions screening",
        "",
        html_table(
            ["How the listed party appears", "Parties", "Found", "Found as match", "Found as review"],
            [[k.replace("_", " "), str(v["parties"]), _f(v["found"]), _f(v["found_as_match"]), _f(v["found_as_review"])] for k, v in scr["by_link_kind"].items()],
        ),
        "",
        html_table(["Alert tier", "Alerts", "True", "Precision"], [[k, str(v["alerts"]), str(v["true"]), _f(v["precision"])] for k, v in scr["alerts"].items()]),
        "",
        html_table(["Control steps from the listed party", "Exposed companies", "Recall"], [[k, str(v["companies"]), _f(v["recall"])] for k, v in scr["company_recall_by_hop"].items()]),
        "",
        "## Detection by typology",
        "",
        html_table(
            ["Typology", "Planted", "Flagged", "True positives", "False positives", "False negatives", "Precision", "Recall", "F1"],
            [
                [TYPOLOGY_TITLES[t], f"{v['planted']:,}", f"{v['flagged']:,}", f"{v['tp']:,}", f"{v['fp']:,}", f"{v['fn']:,}", _f(v["precision"]), _f(v["recall"]), _f(v["f1"])]
                for t, v in det["per_typology"].items()
            ],
        ),
        "",
        "## Systems compared on the label any planted typology",
        "",
        html_table(
            ["System", "Average precision", "ROC AUC", "Precision at 100", "Precision at 1,000", "Recall at 1 percent budget", "Recall at 5 percent budget", "Recall at 10 percent budget"],
            [
                [k, _f(v["average_precision"]), _f(v["roc_auc"]), _f(v["precision_at_100"], 2), _f(v["precision_at_1000"]), _f(v["recall_at_1_percent_budget"]), _f(v["recall_at_5_percent_budget"]), _f(v["recall_at_10_percent_budget"])]
                for k, v in det["comparison"].items()
            ],
        ),
        "",
        f"At the alert threshold of {det['alert_threshold']:.2f} the rule fusion raises {det['fused_at_threshold']['alerts']:,} alerts with precision {_f(det['fused_at_threshold']['precision'])} and recall {_f(det['fused_at_threshold']['recall'])}.",
        "",
        html_table(["Risk band", "Companies", "Share that is truly planted"], [[band, f"{det['risk_bands'][band]:,}", _f(det["band_precision"][band])] for band in ("Critical", "High", "Medium", "Low") if band in det["risk_bands"]]),
        "",
        html_table(["Population", "Companies", "Alert rate", "Mean risk score"], [[k.replace("_", " "), f"{v['companies']:,}", _f(v["alert_rate"], 4), _f(v["mean_risk"])] for k, v in det["hard_negatives"].items()]),
        "",
        "## Ablations",
        "",
        html_table(
            ["Typology", "Capability removed", "Precision full", "Recall full", "Precision without", "Recall without"],
            [
                [k.replace("_", " "), v["capability_removed"], _f(v["full"]["precision"]), _f(v["full"]["recall"]), _f(v["ablated"]["precision"]), _f(v["ablated"]["recall"])]
                for k, v in abl.items()
            ],
        ),
        "",
        "## Retrieval",
        "",
        html_table(["Typology retrieval", "MRR", "Hit at 1", "Hit at 3"], [[k, _f(v["mrr"]), _f(v["hit_at_1"]), _f(v["hit_at_3"])] for k, v in ret["typology_retrieval"].items()]),
        "",
        f"{ret['typology_queries']} analyst questions over {ret['typology_library_cards']} cards.",
        "",
        html_table(["Name lookup channel", "Hit at 1", "Hit at 5"], [[k, _f(v["hit_at_1"]), _f(v["hit_at_5"])] for k, v in ret["entity_lookup"].items()]),
        "",
        f"{ret['entity_lookup_queries']:,} noisy queries against an index of {ret['entity_index_size']:,} names.",
        "",
        "## Narrative verification",
        "",
        html_table(
            ["Measure", "Value"],
            [
                ["Narrator", nar["narrator"]],
                ["Dossiers written", f"{nar['dossiers']:,}"],
                ["Claims checked", f"{nar['claims']:,}"],
                ["Claims supported by cited evidence", f"{nar['claims_supported']:,}"],
                ["Mean evidence items per dossier", _f(nar["mean_evidence_items"], 1)],
                ["Fabricated claims tested", f"{nar['fabricated_claims_tested']:,}"],
                ["Fabricated claims rejected", f"{nar['fabricated_claims_caught']:,}"],
                ["Hostile names planted and detected", f"{nar['injection_guard']['detected']} of {nar['injection_guard']['planted_hostile_names']}"],
                ["False alarms on ordinary names", f"{nar['injection_guard']['false_alarms']} of {nar['injection_guard']['benign_names']:,}"],
                ["Prompts or narratives that contained the hostile text", f"{nar['injection_guard']['prompts_or_narratives_containing_the_hostile_text']} of {nar['injection_guard']['prompts_built_for_hostile_names']}"],
            ],
        ),
        "",
        html_table(["Kind of fabricated claim", "Tested", "Rejected", "Rate"], [[k, f"{v['tested']:,}", f"{v['caught']:,}", _f(v["detection_rate"])] for k, v in nar["fabricated_claims"].items()]),
        "",
    ]
    if model:
        lines += [
            "## Supervised challenger",
            "",
            f"Out of fold average precision {_f(model['average_precision'], 4)}, ROC AUC {_f(model['roc_auc'], 4)}, Brier score {_f(model['brier'], 4)} over {model['folds']} grouped folds and {model['features']} raw features.",
            "",
            html_table(["Share of positives labelled", "Labelled cases", "Average precision"], [[f"{int(round(100 * r['share_of_positives_labelled']))} percent", f"{r['labelled_positives']:,}", _f(r["average_precision"])] for r in model["label_budget"]]),
            "",
            html_table(["Feature", "Permutation importance"], [[r["feature"], _f(r["importance"], 4)] for r in model["importance"][:8]]),
            "",
        ]
    lines += [
        "## Runtime",
        "",
        html_table(["Stage", "Seconds"], [[k, _f(v, 1)] for k, v in run.items()]),
        "",
        f"Peak memory {metrics.get('peak_memory_gb', 0)} GB.",
        "",
    ]
    return "\n".join(lines)
