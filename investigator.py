"""The investigator: retrieval, narration and verification for one company.

This is the retrieval augmented generation loop of Veil Pierce AI.

1. Graph retrieval collects the facts around the company as cited evidence.
2. Typology retrieval finds the guidance that matches each finding.
3. A narrator writes the dossier from the evidence and the guidance.
4. The verifier removes any claim the evidence does not support.
5. The mitigation matrix supplies the recommended controls.

The risk score is never produced here. It is an input, computed earlier by
the deterministic detectors, and the narrative is only allowed to explain it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from ..config import Settings
from ..detect.base import TYPOLOGY_TITLES, Finding
from ..logging_utils import get_logger
from .graph_retriever import CaseContext, Evidence, GraphRetriever, subgraph_frame
from .index import EntityIndex
from .llm import Claim, LLMNarrator, Narrative, OfflineNarrator, make_narrator
from .typology import Card, TypologyLibrary, load_matrix
from .verifier import VerificationReport, keep_supported, verify_narrative

log = get_logger(__name__)
_COMPANY_NUMBER = re.compile(r"\b(?:\d{8}|[^\W\d_]{2}\d{6})\b")
_QUESTION_WORDS = {
    "who", "what", "which", "where", "when", "why", "how", "does", "do", "is", "are", "the", "a", "an", "of", "for", "to", "behind",
    "ultimately", "ultimate", "controls", "control", "owns", "own", "owner", "owners", "company", "any", "there", "have", "has",
    "sanctions", "sanction", "exposure", "address", "registered", "director", "directors", "officers", "tell", "me", "about", "and",
    "risk", "risky", "linked", "link", "links", "list", "with", "it", "its", "this", "that", "in", "on", "at", "by", "show", "explain",
}
INTENTS = {
    "ownership": ("own", "control", "behind", "ultimate", "parent", "shareholder", "beneficial"),
    "sanctions": ("sanction", "designated", "listed", "ofsi", "ofac", "blocked"),
    "address": ("address", "office", "registered at", "premises", "located"),
    "officers": ("director", "officer", "nominee", "secretary", "appointment"),
}


@dataclass
class Dossier:
    """The finished output for one company."""

    case: CaseContext
    narrative: Narrative
    verification: VerificationReport
    cards: list[Card]
    actions: list[dict]
    audit: dict
    subgraph: pd.DataFrame

    def to_dict(self) -> dict:
        case = self.case

        def claims(items: list[Claim]) -> list[dict]:
            return [{"text": c.text, "citations": c.citations} for c in items]

        return {
            "company_number": case.company_number,
            "company_name": case.company_name,
            "registered_name_raw": case.registered_name,
            "risk_score": case.risk_score,
            "risk_band": case.risk_band,
            "typology_scores": case.scores,
            "typologies_triggered": [TYPOLOGY_TITLES[t] for t in case.flags],
            "summary": claims(self.narrative.summary),
            "findings": claims(self.narrative.findings),
            "ownership": claims(self.narrative.ownership),
            "evidence": [{"id": e.id, "kind": e.kind, "text": e.text, "source": e.source} for e in case.evidence],
            "typology_cards": [{"id": c.id, "title": c.title, "sources": list(c.sources)} for c in self.cards],
            "recommended_actions": self.actions,
            "verification": self.verification.as_dict(),
            "audit": self.audit,
            "graph": self.subgraph.to_dict("records"),
        }


@dataclass
class Answer:
    """Reply to a free text analyst question."""

    question: str
    company_number: str | None
    company_name: str | None
    claims: list[Claim] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "company_number": self.company_number,
            "company_name": self.company_name,
            "answer": [{"text": c.text, "citations": c.citations} for c in self.claims],
            "evidence": [{"id": e.id, "text": e.text, "source": e.source} for e in self.evidence],
            "verification": self.verification,
            "note": self.note,
        }


class Investigator:
    """Produces dossiers and answers questions for companies in the graph."""

    def __init__(
        self,
        retriever: GraphRetriever,
        library: TypologyLibrary,
        settings: Settings,
        entity_index: EntityIndex | None = None,
        narrator=None,
    ) -> None:
        self.retriever = retriever
        self.library = library
        self.settings = settings
        self.entity_index = entity_index
        self.narrator = narrator or make_narrator(settings.rag)
        self.offline = OfflineNarrator()
        self.matrix = load_matrix()
        self._matrix_by_typology = {row["typology"]: row for row in self.matrix["fraud_vectors"]}

    # ================================================================ retrieval
    def cards_for(self, case: CaseContext) -> list[Card]:
        """Retrieve the typology cards that match the findings of a case."""
        chosen: dict[str, Card] = {}
        for finding in case.findings:
            hits = self.library.search(f"{finding.title}. {finding.headline}", k=2)
            finding.card_ids = [card.id for card in hits]
            for card in hits:
                chosen.setdefault(card.id, card)
        if not case.findings:
            for card in self.library.search("identify the beneficial owner and understand the ownership and control structure", k=1):
                chosen.setdefault(card.id, card)
        limits = self.library.by_id.get("T24")
        if limits is not None:
            chosen.setdefault(limits.id, limits)
        return list(chosen.values())[: self.settings.rag.top_k_typologies + 3]

    def actions_for(self, findings: list[Finding], cards: list[Card]) -> list[dict]:
        actions = []
        card_by_id = {card.id: card for card in cards}
        for finding in findings:
            row = self._matrix_by_typology.get(finding.typology)
            if row is None:
                continue
            card = next((card_by_id[c] for c in finding.card_ids if c in card_by_id), None)
            actions.append(
                {
                    "typology": finding.title,
                    "preventive_control": row["preventive"],
                    "detective_control": row["detective"],
                    "corrective_action": row["corrective"],
                    "owner": row["owner"],
                    "regulatory_anchor": row["anchor"],
                    "reviewer_steps": list(card.actions) if card else [],
                    "card": card.id if card else "",
                }
            )
        return actions

    # ================================================================== dossier
    def investigate(self, company_number: str) -> Dossier:
        case = self.retriever.retrieve(company_number)
        cards = self.cards_for(case)
        audit = {
            "provider": self.narrator.provider,
            "model": self.narrator.model,
            "fallback_used": False,
            "fallback_reason": "",
            "config_fingerprint": self.settings.fingerprint(),
            "data_snapshot": self.retriever.graph.meta.get("snapshot_date", ""),
            "evidence_items": len(case.evidence),
            "typology_cards": [card.id for card in cards],
        }
        narrative, report = self._narrate(case, cards, None, audit)
        return Dossier(case, narrative, report, cards, self.actions_for(case.findings, cards), audit, subgraph_frame(self.retriever.graph, case.subgraph_edges))

    def _narrate(self, case: CaseContext, cards: list[Card], question: str | None, audit: dict) -> tuple[Narrative, VerificationReport]:
        """Narrate with the configured narrator and fall back when it fails checks."""
        if isinstance(self.narrator, LLMNarrator):
            try:
                draft = self.narrator.narrate(case, cards, question)
                report = verify_narrative(draft, case, cards)
                audit["model_claims"] = report.total
                audit["model_claims_rejected"] = report.total - report.supported
                audit["rejected_claims"] = [{"text": c.claim.text, "reasons": c.reasons} for c in report.rejected()]
                if report.total and report.supported_ratio >= self.settings.rag.min_supported_ratio:
                    kept = keep_supported(draft, report)
                    return kept, verify_narrative(kept, case, cards)
                audit["fallback_reason"] = f"only {report.supported} of {report.total} model claims were supported by the evidence"
            except Exception as error:  # noqa: BLE001 (any provider failure must degrade safely)
                audit["fallback_reason"] = f"model narrative unavailable: {type(error).__name__}"
            audit["fallback_used"] = True
            log.warning("falling back to the offline narrator for %s: %s", case.company_number, audit["fallback_reason"])
        narrative = self.offline.narrate(case, cards, question)
        if audit["fallback_used"]:
            audit["provider"], audit["model"] = narrative.provider, narrative.model
        return narrative, verify_narrative(narrative, case, cards)

    # ================================================================ questions
    def resolve_company(self, question: str) -> tuple[str | None, str]:
        """Find the company a question is about, by number or by name."""
        for candidate in _COMPANY_NUMBER.findall(question.upper()):
            if candidate in self.retriever.number_to_row:
                return candidate, "company number in the question"
        if self.entity_index is None:
            return None, "no company number found and no name index loaded"
        words = [w for w in re.findall(r"[^\W_]+", question) if w.lower() not in _QUESTION_WORDS]
        if not words:
            return None, "no company name found in the question"
        hits = self.entity_index.search(" ".join(words), k=1, kind="company")
        if not hits or hits[0]["score"] < 0.35:
            return None, "no company in the graph resembles the name in the question"
        return hits[0]["key"][2:], f"name match with similarity {hits[0]['score']:.2f}"

    @staticmethod
    def intent_of(question: str) -> str:
        lowered = question.lower()
        for intent, words in INTENTS.items():
            if any(word in lowered for word in words):
                return intent
        return "summary"

    def ask(self, question: str) -> Answer:
        """Answer a free text question about one company with cited evidence."""
        number, how = self.resolve_company(question)
        if number is None:
            return Answer(question, None, None, note=how)
        case = self.retriever.retrieve(number)
        cards = self.cards_for(case)
        audit = {"provider": self.narrator.provider, "model": self.narrator.model, "fallback_used": False, "fallback_reason": ""}
        if isinstance(self.narrator, LLMNarrator):
            narrative, report = self._narrate(case, cards, question, audit)
            claims = narrative.all_claims() if not audit["fallback_used"] else self._select(narrative, case, question)
        else:
            narrative, report = self._narrate(case, cards, question, audit)
            claims = self._select(narrative, case, question)
        cited = {c for claim in claims for c in claim.citations}
        evidence = [item for item in case.evidence if item.id in cited]
        return Answer(question, number, case.company_name, claims, evidence, report.as_dict(), f"company found by {how}")

    def _select(self, narrative: Narrative, case: CaseContext, question: str) -> list[Claim]:
        """Pick the claims of an offline narrative that answer the question."""
        intent = self.intent_of(question)
        by_typology = {f.typology: f for f in case.findings}

        def finding_claims(*typologies: str) -> list[Claim]:
            out = []
            for typology in typologies:
                finding = by_typology.get(typology)
                if finding is not None:
                    out.append(Claim(f"{finding.title} (score {finding.score:.2f}). {finding.headline}", list(finding.evidence_ids) + ["M01"]))
            return out

        if intent == "ownership":
            return narrative.ownership[:6] + finding_claims("circular", "opaque")
        if intent == "sanctions":
            found = finding_claims("sanctions")
            return found or [Claim("No sanctions proximity finding was triggered for this company within the configured number of control steps.", ["M01"])]
        if intent == "address":
            return [narrative.summary[2]] + finding_claims("address_factory")
        if intent == "officers":
            officers = [c for c in narrative.ownership if "is recorded as director" in c.text or "is recorded as secretary" in c.text]
            return officers + finding_claims("nominee", "phoenix_burst")
        return narrative.summary + narrative.findings[:4]
