"""Assemble the knowledge graph from the canonical tables and resolution output."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Settings
from ..data.synth import Registry
from ..logging_utils import get_logger
from ..resolution.corporates import link_leak_companies, resolve_corporates
from ..resolution.persons import PersonResolution, resolve_persons
from ..resolution.sanctions import screen_entities, screen_persons
from ..textnorm import address_key, canonical_jurisdiction
from .store import KnowledgeGraph

log = get_logger(__name__)


@dataclass
class ResolutionBundle:
    """Everything entity resolution produced, kept for evaluation and audit."""

    persons: PersonResolution
    corporates: pd.DataFrame
    leak_links: pd.DataFrame
    sanction_matches: pd.DataFrame
    address_keys: pd.Series


def _edge_frame(src, dst, etype, text="", band=0.0, date=None, record="", confidence=1.0) -> pd.DataFrame:
    count = len(src)
    return pd.DataFrame(
        {
            "src": np.asarray(src, dtype=np.int64),
            "dst": np.asarray(dst, dtype=np.int64),
            "etype": etype,
            "text": np.broadcast_to(np.asarray(text, dtype=object), (count,)).copy(),
            "band": np.broadcast_to(np.asarray(band, dtype=np.float32), (count,)).copy(),
            "date": pd.to_datetime(np.broadcast_to(np.asarray(date if date is not None else np.datetime64("NaT", "s")), (count,))),
            "record": np.broadcast_to(np.asarray(record, dtype=object), (count,)).copy(),
            "confidence": np.broadcast_to(np.asarray(confidence, dtype=np.float32), (count,)).copy(),
        }
    )


def _fullest_variants(variants: str) -> list[str]:
    """Keep the name variants that carry the most complete set of name tokens.

    Screening a shortened variant of a person whose full name is known would
    only add false matches, so the shortened forms are left out.
    """
    names = variants.split("|")
    richness = [sum(1 for tok in name.split() if len(tok) > 1) for name in names]
    top = max(richness)
    return [name for name, rich in zip(names, richness) if rich == top][:3]


def build_graph(registry: Registry, settings: Settings) -> tuple[KnowledgeGraph, ResolutionBundle]:
    """Run entity resolution and build the typed knowledge graph."""
    rcfg = settings.resolution
    aliases = settings.jurisdiction_aliases
    opacity = settings.opacity_weights
    companies = registry.companies

    persons = resolve_persons(registry.officers, registry.pscs, rcfg)
    corporates = resolve_corporates(registry.pscs, companies, registry.offshore_entities, rcfg, aliases)
    leak_links = link_leak_companies(registry.offshore_officers, companies, rcfg)

    # ================================================================== nodes
    addr_keys = pd.Series(
        [address_key(line, pc) for line, pc in zip(companies["address_line1"], companies["postcode"])],
        index=companies.index,
    )
    line = companies["address_line1"].str.title().str.replace(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), regex=True)
    addr_label = line + ", " + companies["post_town"].str.title() + " " + companies["postcode"].str.upper()
    addr_table = pd.DataFrame({"key": addr_keys.to_numpy(), "label": addr_label.to_numpy()}).drop_duplicates("key")

    clusters = persons.clusters
    foreign = corporates[corporates["target_kind"] == "foreign"].drop_duplicates("target_key")
    linked_leak = set(leak_links["node_id"])
    leak_officers = registry.offshore_officers[~registry.offshore_officers["node_id"].isin(linked_leak)]
    off_jur = registry.offshore_entities["jurisdiction"].map(lambda j: canonical_jurisdiction(j, aliases))

    parts = [
        pd.DataFrame({"kind": "company", "key": "C:" + companies["company_number"], "label": companies["company_name"], "jurisdiction": "UNITED KINGDOM"}),
        pd.DataFrame({"kind": "person", "key": "P:" + clusters["cluster_id"].astype(str), "label": clusters["label"].str.title(), "jurisdiction": ""}),
        pd.DataFrame({"kind": "address", "key": "A:" + addr_table["key"], "label": addr_table["label"], "jurisdiction": ""}),
        pd.DataFrame({"kind": "offshore", "key": "O:" + registry.offshore_entities["node_id"].astype(str), "label": registry.offshore_entities["name"], "jurisdiction": off_jur}),
        pd.DataFrame({"kind": "foreign", "key": "F:" + foreign["target_key"], "label": foreign["target_label"], "jurisdiction": foreign["jurisdiction"]}),
        pd.DataFrame({"kind": "leak_officer", "key": "LO:" + leak_officers["node_id"].astype(str), "label": leak_officers["name"], "jurisdiction": ""}),
        pd.DataFrame({"kind": "sanction", "key": "S:" + registry.sanctions["entity_id"], "label": registry.sanctions["name"], "jurisdiction": ""}),
    ]
    nodes = pd.concat(parts, ignore_index=True)
    default_weight = np.where(nodes["kind"].isin(["offshore", "foreign"]), 0.5, 0.0)
    mapped = nodes["jurisdiction"].map(opacity).to_numpy(dtype=float)
    nodes["opacity"] = np.where(np.isnan(mapped), default_weight, mapped).astype(np.float32)
    key_to_id = dict(zip(nodes["key"], range(len(nodes))))

    def ids(prefix: str, values) -> np.ndarray:
        return np.array([key_to_id[prefix + str(v)] for v in values], dtype=np.int64)

    # ================================================================== edges
    rec = persons.records
    off_rec = rec[rec["source"] == "officer"].merge(
        registry.officers[["appointment_id", "role", "appointed_on", "resigned_on"]], left_on="record_id", right_on="appointment_id"
    )
    off_rec = off_rec.drop_duplicates(["cluster_id", "company_number", "role"])
    edges = [
        _edge_frame(
            ids("P:", off_rec["cluster_id"]), ids("C:", off_rec["company_number"]), "officer_of",
            off_rec["role"].to_numpy(dtype=object), 0.0, off_rec["appointed_on"].to_numpy(),
            ("appointment " + off_rec["appointment_id"].astype(str)).to_numpy(dtype=object),
        )
    ]
    psc_rec = rec[rec["source"] == "psc"].merge(
        registry.pscs[["psc_id", "natures_of_control", "ownership_band", "notified_on"]], left_on="record_id", right_on="psc_id"
    )
    edges.append(
        _edge_frame(
            ids("P:", psc_rec["cluster_id"]), ids("C:", psc_rec["company_number"]), "controls",
            psc_rec["natures_of_control"].to_numpy(dtype=object), psc_rec["ownership_band"].to_numpy(), psc_rec["notified_on"].to_numpy(),
            ("control record " + psc_rec["psc_id"].astype(str)).to_numpy(dtype=object),
        )
    )
    corp = corporates.merge(registry.pscs[["psc_id", "company_number", "natures_of_control", "ownership_band", "notified_on", "name"]], on="psc_id")
    prefix = corp["target_kind"].map({"company": "C:", "offshore": "O:", "foreign": "F:"})
    corp_src = np.array([key_to_id[p + k] for p, k in zip(prefix, corp["target_key"])], dtype=np.int64)
    corp_text = corp["natures_of_control"] + "; filed as " + corp["name"] + "; resolved by " + corp["method"]
    edges.append(
        _edge_frame(
            corp_src, ids("C:", corp["company_number"]), "controls", corp_text.to_numpy(dtype=object),
            corp["ownership_band"].to_numpy(), corp["notified_on"].to_numpy(),
            ("control record " + corp["psc_id"].astype(str)).to_numpy(dtype=object),
            np.where(corp["method"] == "unresolved stub", 0.8, np.clip(corp["score"] / 100.0, 0.8, 1.0)),
        )
    )
    edges.append(_edge_frame(ids("C:", companies["company_number"]), ids("A:", addr_keys), "registered_at", "registered office", record="company register"))

    leak_map = dict(zip(leak_links["node_id"], "C:" + leak_links["company_number"]))
    entity_ids = set(registry.offshore_entities["node_id"])
    oe = registry.offshore_edges
    from_entity = oe["start_id"].isin(entity_ids)
    ent_edges = oe[from_entity]
    edges.append(
        _edge_frame(ids("O:", ent_edges["start_id"]), ids("O:", ent_edges["end_id"]), "leak_shareholder_of", ent_edges["link"].to_numpy(dtype=object), 0.5, record="leak data")
    )
    off_edges = oe[~from_entity]
    start_keys = [leak_map.get(s, f"LO:{s}") for s in off_edges["start_id"]]
    start_ids = np.array([key_to_id[k] for k in start_keys], dtype=np.int64)
    via_name = np.array([k.startswith("C:") for k in start_keys])
    text = np.where(via_name, off_edges["link"] + "; leak officer matched to UK company by name", off_edges["link"])
    edges.append(
        _edge_frame(start_ids, ids("O:", off_edges["end_id"]), "leak_officer_of", text, 0.5, record="leak data", confidence=np.where(via_name, 0.9, 1.0))
    )

    # ======================================================= sanctions screening
    person_candidates = clusters.assign(name=clusters["variants"].map(_fullest_variants)).explode("name")
    person_candidates = pd.DataFrame(
        {
            "node_key": "P:" + person_candidates["cluster_id"].astype(str),
            "name": person_candidates["name"],
            "dob_year": person_candidates["dob_year"],
            "dob_month": person_candidates["dob_month"],
        }
    )
    leak_people = leak_officers[leak_officers["kind"] == "person"]
    leak_candidates = pd.DataFrame({"node_key": "LO:" + leak_people["node_id"].astype(str), "name": leak_people["name"], "dob_year": 0, "dob_month": 0})
    person_matches = screen_persons(registry.sanctions, pd.concat([person_candidates, leak_candidates], ignore_index=True), rcfg)
    leak_corps = leak_officers[leak_officers["kind"] == "company"]
    entity_candidates = pd.concat(
        [
            pd.DataFrame({"node_key": "O:" + registry.offshore_entities["node_id"].astype(str), "name": registry.offshore_entities["name"]}),
            pd.DataFrame({"node_key": "F:" + foreign["target_key"], "name": foreign["target_label"]}),
            pd.DataFrame({"node_key": "LO:" + leak_corps["node_id"].astype(str), "name": leak_corps["name"]}),
            pd.DataFrame({"node_key": "C:" + companies["company_number"], "name": companies["company_name"]}),
        ],
        ignore_index=True,
    )
    entity_matches = screen_entities(registry.sanctions, entity_candidates, rcfg)
    matches = pd.concat([person_matches, entity_matches], ignore_index=True)
    if len(matches):
        match_text = matches["decision"] + "; " + matches["dob_status"] + "; list name " + matches["matched_name"]
        edges.append(
            _edge_frame(
                ids("S:", matches["entity_id"]), np.array([key_to_id[k] for k in matches["node_key"]], dtype=np.int64),
                "sanctions_match", match_text.to_numpy(dtype=object), 0.0, record="sanctions screening",
                confidence=matches["score"].to_numpy(),
            )
        )
    edge_table = pd.concat(edges, ignore_index=True)
    graph = KnowledgeGraph(nodes, edge_table, {"snapshot_date": registry.meta.get("snapshot_date", ""), "synthetic": registry.meta.get("synthetic", False)})
    log.info("graph built: %s", graph.describe())
    bundle = ResolutionBundle(persons, corporates, leak_links, matches, addr_keys)
    return graph, bundle
