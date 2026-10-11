"""Graph retrieval: turns the neighbourhood of a company into cited evidence.

Text retrieval alone cannot answer who ultimately controls a company. The
answer is a path, and the path has to be walked. This module walks the graph
around one company (its officers, its control records, the ownership chain
above it, any loop it sits on, any path from a sanctions match, and the
address it shares) and converts every edge it uses into a numbered evidence
item written in plain language.

Evidence items are the only facts a narrative is allowed to state. Each one
carries the identifier of the edge or analysis it came from, so a reviewer
can trace every sentence in a dossier back to a source record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import Settings
from ..detect.base import FLAG_THRESHOLDS, TYPOLOGY_TITLES, Finding
from ..detect.engine import TYPOLOGIES, DetectionResult
from ..graph.algorithms import find_cycle, path_to_source, upstream_edges
from ..graph.store import OWNERSHIP_TYPES, KnowledgeGraph
from .guard import looks_like_injection, quote_data, sanitise_field

MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
KIND_WORDS = {
    "company": "UK company",
    "person": "resolved person",
    "address": "address",
    "offshore": "offshore entity",
    "foreign": "foreign company",
    "leak_officer": "leak data officer",
    "sanction": "sanctions list entry",
}


def fmt_date(value) -> str:
    """Render a timestamp as 02 Apr 2019, or the word unknown."""
    if value is None or pd.isna(value):
        return "unknown"
    stamp = pd.Timestamp(value)
    return f"{stamp.day:02d} {MONTHS[stamp.month]} {stamp.year}"


def pct(value: float) -> str:
    return f"{int(round(100 * float(value)))} percent"


@dataclass
class Evidence:
    """One retrieved fact with its provenance."""

    id: str
    kind: str
    text: str
    source: str
    edge_id: int | None = None


@dataclass
class CaseContext:
    """Everything retrieved for one company."""

    company_number: str
    company_name: str
    registered_name: str
    node_id: int
    risk_score: float
    risk_band: str
    scores: dict[str, float]
    flags: list[str]
    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    entity_names: list[str] = field(default_factory=list)
    injection_fields: list[str] = field(default_factory=list)
    subgraph_edges: list[int] = field(default_factory=list)
    profile: dict = field(default_factory=dict)

    def evidence_by_id(self) -> dict[str, Evidence]:
        return {item.id: item for item in self.evidence}


class GraphRetriever:
    """Builds a CaseContext for any company in the graph."""

    def __init__(
        self,
        graph: KnowledgeGraph,
        detection: DetectionResult,
        companies: pd.DataFrame,
        clusters: pd.DataFrame,
        sanctions: pd.DataFrame,
        settings: Settings,
    ) -> None:
        self.graph = graph
        self.detection = detection
        self.settings = settings
        self.companies = companies.reset_index(drop=True)
        self.number_to_row = dict(zip(self.companies["company_number"], range(len(self.companies))))
        self.cluster_by_key = {f"P:{cid}": row for cid, row in zip(clusters["cluster_id"], clusters.to_dict("records"))}
        self.sanction_by_key = {f"S:{row['entity_id']}": row for row in sanctions.to_dict("records")}
        self.edge_text = graph.edges["text"].to_numpy(dtype=object)
        self.edge_band = graph.edges["band"].to_numpy(dtype=np.float32)
        self.edge_date = graph.edges["date"]
        self.edge_record = graph.edges["record"].to_numpy(dtype=object)
        self.edge_conf = graph.edges["confidence"].to_numpy(dtype=np.float32)
        self.jurisdiction = graph.nodes["jurisdiction"].to_numpy(dtype=object)
        self.opacity = graph.nodes["opacity"].to_numpy(dtype=np.float32)

    # ============================================================ node wording
    def name(self, node: int) -> str:
        return quote_data(self.graph.label[node])

    def describe(self, node: int) -> str:
        """Name of a node with the identifier a reviewer needs to find it."""
        graph = self.graph
        kind, key, label = graph.kind[node], graph.key[node], self.name(node)
        if kind == "company":
            return f"{label} (company {key[2:]})"
        if kind == "person":
            info = self.cluster_by_key.get(key, {})
            year, month = int(info.get("dob_year", 0) or 0), int(info.get("dob_month", 0) or 0)
            born = f", born {MONTHS[month]} {year}" if year and 1 <= month <= 12 else ""
            return f"{label} (person {key[2:]}{born})"
        if kind == "offshore":
            return f"{label} (offshore entity {key[2:]}, {str(self.jurisdiction[node]).title()})"
        if kind == "foreign":
            place = str(self.jurisdiction[node]).title() or "unknown jurisdiction"
            return f"{label} (foreign company not found in any dataset, {place})"
        if kind == "leak_officer":
            return f"{label} (leak data officer {key[3:]})"
        if kind == "sanction":
            info = self.sanction_by_key.get(key, {})
            return f"{label} (list entry {key[2:]}, regime {info.get('regime', 'unknown')})"
        return label

    def edge_statement(self, eid: int) -> tuple[str, str]:
        """Plain language statement of one edge and the name of its source."""
        graph = self.graph
        src, dst, etype = int(graph.src[eid]), int(graph.dst[eid]), graph.etype[eid]
        text = sanitise_field(self.edge_text[eid])
        when = fmt_date(self.edge_date.iat[eid])
        record = str(self.edge_record[eid])
        if etype == "officer_of":
            residence = sanitise_field(self.cluster_by_key.get(graph.key[src], {}).get("residence", ""))
            lives = f", usual residence {residence}," if residence else ""
            return f"{self.describe(src)}{lives} is recorded as {text} of {self.describe(dst)}, appointed {when}.", f"officer register, {record}"
        if etype == "controls":
            if graph.kind[src] == "person":
                return f"{self.describe(src)} is recorded as a person with significant control of {self.describe(dst)}: {text}, notified {when}.", f"control register, {record}"
            return (
                f"{self.describe(src)} is recorded as a corporate controller of {self.describe(dst)}: {text}, notified {when}. "
                f"Link confidence {self.edge_conf[eid]:.2f}.",
                f"control register, {record}",
            )
        if etype == "leak_officer_of":
            link, _, note = text.partition(";")
            matched = " The leak officer was matched to the UK company by name." if note.strip() else ""
            return f"Leak data records {self.describe(src)} as {link.strip()} {self.describe(dst)}.{matched}", "offshore leak data"
        if etype == "leak_shareholder_of":
            return f"Leak data records {self.describe(src)} as {text} {self.describe(dst)}.", "offshore leak data"
        if etype == "sanctions_match":
            return (
                f"Sanctions screening: {self.describe(dst)} matches {self.describe(src)} with score {self.edge_conf[eid]:.2f}. Basis: {text}.",
                "sanctions screening",
            )
        if etype == "registered_at":
            return f"{self.describe(src)} has its registered office at {self.name(dst)}.", "company register"
        return f"{self.describe(src)} is linked to {self.describe(dst)}.", record

    # ================================================================= retrieve
    def retrieve(self, company_number: str) -> CaseContext:
        if company_number not in self.number_to_row:
            raise KeyError(f"unknown company number: {company_number}")
        graph, det = self.graph, self.detection
        node = self.number_to_row[company_number]
        row = det.companies.iloc[node]
        company = self.companies.iloc[node]
        scores = {t: round(float(row[f"score_{t}"]), 2) for t in TYPOLOGIES}
        flags = [t for t in TYPOLOGIES if bool(row[f"flag_{t}"])]
        case = CaseContext(
            company_number=company_number,
            company_name=quote_data(company["company_name"]),
            registered_name=sanitise_field(company["company_name"]),
            node_id=node,
            risk_score=round(float(row["risk_rules"]), 2),
            risk_band=str(row["risk_band"]),
            scores=scores,
            flags=flags,
        )
        seen_edges: dict[int, str] = {}
        names: set[str] = set()

        def add(kind: str, text: str, source: str, edge_id: int | None = None) -> str:
            eid = f"E{len(case.evidence) + 1:02d}"
            case.evidence.append(Evidence(eid, kind, text, source, edge_id))
            return eid

        def add_edge(eid: int, kind: str) -> str:
            eid = int(eid)
            if eid in seen_edges:
                return seen_edges[eid]
            text, source = self.edge_statement(eid)
            ident = add(kind, text, source, eid)
            seen_edges[eid] = ident
            case.subgraph_edges.append(eid)
            for endpoint in (int(graph.src[eid]), int(graph.dst[eid])):
                names.add(sanitise_field(graph.label[endpoint]))
            return ident

        # Model output is evidence too, so that statements about scores can be cited.
        triggered = ", ".join(TYPOLOGY_TITLES[t] for t in flags) or "none"
        score_text = "; ".join(f"{TYPOLOGY_TITLES[t]} {scores[t]:.2f}" for t in TYPOLOGIES)
        case.evidence.append(
            Evidence(
                "M01", "model",
                f"Deterministic detectors give {case.company_name} (company {company_number}) a fused risk score of {case.risk_score:.2f}, "
                f"band {case.risk_band}. Typology scores: {score_text}. Typologies triggered ({len(flags)}): {triggered}.",
                "Veil Pierce AI detectors",
            )
        )
        status = str(company["status"])
        ended = f", dissolved {fmt_date(company['dissolution_date'])}" if pd.notna(company["dissolution_date"]) else ""
        address_node = int(row["address_node"])
        profile_id = add(
            "profile",
            f"{case.company_name} (company {company_number}) was incorporated on {fmt_date(company['incorporation_date'])}, status {status}{ended}. "
            f"Accounts category: {sanitise_field(company['accounts_category'])}. Registered office: {self.name(address_node)}. "
            f"Activity code: {sanitise_field(company['sic_code'])} {sanitise_field(company['sic_text'])}.",
            "company register",
        )
        names.add(sanitise_field(company["company_name"]))
        case.profile = {
            "status": status,
            "incorporated": fmt_date(company["incorporation_date"]),
            "dissolved": fmt_date(company["dissolution_date"]) if pd.notna(company["dissolution_date"]) else "",
            "accounts": str(company["accounts_category"]),
            "address": self.name(address_node),
            "profile_evidence": profile_id,
        }
        if looks_like_injection(company["company_name"]):
            case.injection_fields.append("company name")
            add(
                "guard",
                f"The registered name of company {company_number} contains instruction like wording. It is withheld from the narrative, treated strictly as data and has no effect on scoring.",
                "prompt injection guard",
            )

        officer_ids = [add_edge(e, "officer") for e in graph.in_edges(node, ("officer_of",))[:6]]
        control_ids = [add_edge(e, "control") for e in graph.in_edges(node, ("controls",))[:6]]
        if not control_ids:
            control_ids = [add("control", f"No person with significant control is recorded for company {company_number}.", "control register")]

        max_items = self.settings.rag.max_evidence_items
        chain = upstream_edges(graph, node, self.settings.detect.control_max_depth, OWNERSHIP_TYPES, limit=max_items)
        chain_ids = [add_edge(e, "ownership chain") for e, _ in chain[:14]]

        # ============================================================ findings
        if "nominee" in flags and int(row["top_director_node"]) >= 0:
            person = int(row["top_director_node"])
            stats = det.persons.loc[person]
            info = self.cluster_by_key.get(graph.key[person], {})
            variants = [v.title() for v in str(info.get("variants", "")).split("|") if v][:5]
            link = [seen_edges.get(int(e)) or add_edge(e, "officer") for e in graph.out_edges(person, ("officer_of",)) if int(graph.dst[e]) == node][:1]
            analysis = add(
                "analysis",
                f"Entity resolution links {int(info.get('n_variants', 1))} name spellings to {self.describe(person)}"
                f"{' (for example ' + ', '.join(variants) + ')' if len(variants) > 1 else ''}. That person holds {int(stats['n_companies'])} director appointments. "
                f"{pct(stats['shell_ratio'])} of those companies are shell like (dissolved within two years, dormant, or overdue with no accounts) and the person is the sole director of {pct(stats['sole_ratio'])}.",
                "entity resolution and appointment analysis",
            )
            case.findings.append(
                Finding(
                    "nominee", scores["nominee"],
                    f"The director {self.name(person)} holds {int(stats['n_companies'])} director appointments, {pct(stats['shell_ratio'])} of them in shell like companies, "
                    f"and is the sole director of {pct(stats['sole_ratio'])}.",
                    {"appointments": int(stats["n_companies"]), "shell_ratio": float(stats["shell_ratio"]), "person": graph.key[person]},
                    evidence_ids=link + [analysis],
                )
            )

        if "address_factory" in flags:
            stats = det.addresses.loc[address_node]
            analysis = add(
                "analysis",
                f"{int(stats['n_companies'])} companies share the resolved address {self.name(address_node)}. {pct(stats['shell_ratio'])} of them are shell like, "
                f"{pct(stats['overseas_ratio'])} of their directors are resident overseas, and the busiest 14 day window accounts for {pct(stats['burst_share'])} of all incorporations there.",
                "address resolution and address statistics",
            )
            case.findings.append(
                Finding(
                    "address_factory", scores["address_factory"],
                    f"The registered office is shared by {int(stats['n_companies'])} companies, {pct(stats['shell_ratio'])} of which are shell like, with {pct(stats['overseas_ratio'])} of directors resident overseas.",
                    {"companies": int(stats["n_companies"]), "shell_ratio": float(stats["shell_ratio"])},
                    evidence_ids=[profile_id, analysis],
                )
            )

        if "circular" in flags:
            loop = find_cycle(graph, node, det.component)
            loop_ids = [add_edge(e, "ownership loop") for e in loop]
            loop_ids.append(
                add(
                    "analysis",
                    f"The shortest loop of declared control through company {company_number} has {len(loop)} links. No natural person appears on it.",
                    "strongly connected component analysis",
                )
            )
            members = [self.name(int(graph.src[e])) for e in loop]
            route = ", which controls ".join(members + members[:1]) if members else case.company_name
            case.findings.append(
                Finding(
                    "circular", scores["circular"],
                    f"The company sits on a closed loop of declared control with {len(loop)} links: {route}. No natural person appears on the loop.",
                    {"loop_length": len(loop)},
                    edge_ids=[int(e) for e in loop],
                    evidence_ids=loop_ids,
                )
            )

        if "sanctions" in flags:
            reach = det.reach
            origin = int(reach["origin"][node])
            hops = int(reach["dist"][node])
            path = path_to_source(graph, node, reach["pred"])
            match_edges = graph.in_edges(origin, ("sanctions_match",))
            best = int(match_edges[np.argmax(self.edge_conf[match_edges])])
            match_id = add_edge(best, "sanctions match")
            path_ids = [add_edge(e, "control path") for e in path]
            bands = [float(self.edge_band[e]) for e in path if graph.etype[e] == "controls" and self.edge_band[e] > 0]
            decision = "confirmed by date of birth" if self.edge_conf[best] >= self.settings.resolution.sanctions_threshold else "a potential match that needs manual review"
            ownership = (
                f" Declared ownership bands along the path multiply to an effective holding of about {pct(float(np.prod(bands)))}." if len(bands) == len(path) and bands else
                " At least one link on the path is control by office or an unquantified leak record, so effective ownership cannot be computed."
            )
            steps = f"{hops} control step{'s' if hops != 1 else ''}"
            analysis = add(
                "analysis",
                f"Company {company_number} is {steps} downstream of {self.describe(origin)}, which matches {self.describe(int(graph.src[best]))} "
                f"with score {self.edge_conf[best]:.2f}. The match is {decision}.{ownership}",
                "downstream control search",
            )
            case.findings.append(
                Finding(
                    "sanctions", scores["sanctions"],
                    f"The company is {steps} downstream of {self.name(origin)}, which matches sanctions list entry {self.name(int(graph.src[best]))} "
                    f"with score {self.edge_conf[best]:.2f}. The match is {decision}.",
                    {"hops": hops, "match_score": float(self.edge_conf[best]), "list_entry": graph.key[int(graph.src[best])]},
                    edge_ids=[best] + [int(e) for e in path],
                    evidence_ids=[match_id] + path_ids + [analysis],
                )
            )

        if "opaque" in flags:
            corporate = [(e, d) for e, d in chain if graph.kind[int(graph.src[e])] in ("offshore", "foreign")]
            top_edge = max(corporate, key=lambda item: self.opacity[int(graph.src[item[0]])])[0] if corporate else None
            leak_edges = [e for e, _ in chain if graph.etype[e] in ("leak_officer_of", "leak_shareholder_of")]
            hidden = [self.name(int(graph.src[e])) for e in leak_edges if graph.kind[int(graph.src[e])] == "leak_officer"]
            ids = [seen_edges[int(e)] for e, _ in corporate[:4] if int(e) in seen_edges]
            ids += [seen_edges[int(e)] for e in leak_edges[:4] if int(e) in seen_edges]
            headline = "The declared chain of control reaches no natural person."
            if top_edge is not None:
                owner = int(graph.src[top_edge])
                headline += f" It ends at {self.name(owner)}, registered in {str(self.jurisdiction[owner]).title() or 'an unknown jurisdiction'}."
            if hidden:
                headline += f" Leak data names {', '.join(hidden[:3])} behind the offshore owner, which the register does not show."
            analysis = add(
                "analysis",
                f"Walking up the control records from company {company_number} finds no natural person within {self.settings.detect.control_max_depth} steps. "
                f"The longest chain of corporate owners above it has {int(row['chain_depth'])} link(s) and the highest jurisdiction opacity weight on the chain is {float(row['upstream_opacity']):.2f}.",
                "ownership chain analysis",
            )
            ids = list(dict.fromkeys(ids))
            case.findings.append(Finding("opaque", scores["opaque"], headline, {"chain_depth": int(row["chain_depth"]), "hidden_controllers": hidden[:3]}, evidence_ids=ids + [analysis]))

        if "phoenix_burst" in flags:
            ids, parts = [], []
            pairs = det.phoenix[(det.phoenix["c_old"] == node) | (det.phoenix["c_new"] == node)]
            for pair in pairs.head(3).itertuples(index=False):
                old, new = int(pair.c_old), int(pair.c_new)
                old_row, new_row = self.companies.iloc[old], self.companies.iloc[new]
                ids.append(
                    add(
                        "analysis",
                        f"{self.describe(old)} was dissolved on {fmt_date(old_row['dissolution_date'])}. {self.describe(new)} was incorporated on {fmt_date(new_row['incorporation_date'])}, "
                        f"{int(pair.gap_days)} days later, with the same director {self.name(int(pair.p))} at the same address. Name similarity {int(pair.similarity)} out of 100.",
                        "phoenix pair analysis",
                    )
                )
                names.update({sanitise_field(old_row["company_name"]), sanitise_field(new_row["company_name"])})
            if len(pairs):
                ids.append(add("analysis", f"Company {company_number} appears in {len(pairs)} dissolved and reborn pair(s).", "phoenix pair analysis"))
                parts.append(f"The company is part of {len(pairs)} dissolved and reborn pair(s) with a near identical name, the same director and the same address.")
            if float(row["batch_size"]) > 0:
                runs = det.batches[det.batches["c"] == node].sort_values("run_size", ascending=False).head(1)
                for run in runs.itertuples(index=False):
                    members = det.batches[det.batches["run"] == run.run]["c"].to_numpy()
                    dates = self.companies["incorporation_date"].iloc[members]
                    sample = ", ".join(self.name(int(m)) for m in members[:4])
                    ids.append(
                        add(
                            "analysis",
                            f"{len(members)} companies were incorporated between {fmt_date(dates.min())} and {fmt_date(dates.max())} with the same director {self.name(int(run.p))} at {self.name(int(run.a))}. "
                            f"{pct(run.run_shell)} of them are shell like. Examples: {sample}.",
                            "batch analysis",
                        )
                    )
                    parts.append(f"The company was created in a batch of {len(members)} companies by the same director at the same address, {pct(run.run_shell)} of which are shell like.")
                    names.update(sanitise_field(graph.label[int(m)]) for m in members[:4])
            if parts:
                case.findings.append(Finding("phoenix_burst", scores["phoenix_burst"], " ".join(parts), {"pairs": int(len(pairs)), "batch_size": int(row["batch_size"])}, evidence_ids=ids))

        case.entity_names = sorted(n for n in names if len(n) >= 6)
        case.profile.update({"officer_evidence": officer_ids, "control_evidence": control_ids, "chain_evidence": chain_ids})
        return case


def subgraph_frame(graph: KnowledgeGraph, edge_ids: list[int]) -> pd.DataFrame:
    """Edges of a case as a small table, for drawing and for the API."""
    rows = []
    for eid in edge_ids:
        src, dst = int(graph.src[eid]), int(graph.dst[eid])
        rows.append(
            {
                "source": graph.key[src],
                "source_label": sanitise_field(graph.label[src]),
                "source_kind": graph.kind[src],
                "target": graph.key[dst],
                "target_label": sanitise_field(graph.label[dst]),
                "target_kind": graph.kind[dst],
                "type": graph.etype[eid],
            }
        )
    return pd.DataFrame(rows, columns=["source", "source_label", "source_kind", "target", "target_label", "target_kind", "type"])


def threshold_note() -> str:
    """One line reminder of the flag thresholds, used in reports."""
    return ", ".join(f"{TYPOLOGY_TITLES[t]} {v:.2f}" for t, v in FLAG_THRESHOLDS.items())
