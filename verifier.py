"""Citation verifier: the last gate before a narrative reaches a reviewer.

A language model can write a fluent sentence that no evidence supports. In a
financial crime setting that sentence is an accusation. The verifier checks
every claim of every narrative, whoever wrote it, against the evidence that
was retrieved for the case:

1. the claim cites at least one item and every cited item exists
2. every number in the claim appears in a cited item
3. every name in the claim, known or unknown, appears in a cited item
4. the claim does not contradict the risk band computed by the detectors
5. the claim does not assert guilt or a confirmed offence
6. the claim does not echo instruction like text from the registry

Claims that fail are removed and reported. If too few claims survive, the
investigator discards the model narrative and uses the offline composer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..detect.base import RISK_BANDS
from .graph_retriever import CaseContext
from .guard import looks_like_injection
from .llm import Claim, Narrative
from .typology import Card

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_ITEM_ID = re.compile(r"\b[EMT]\d{2}\b")
_CONCLUSIONS = [
    r"\b(is|are|was|were)\s+(guilty|a\s+criminal|criminals|a\s+fraudster|fraudsters|a\s+money\s+launderer)\b",
    r"\b(is|are|was|were)\s+(laundering|committing|evading\s+sanctions)\b",
    r"\b(committed|commits)\s+(fraud|money\s+laundering|an?\s+offence|a\s+crime)\b",
    r"\b(proves|proven|proof\s+that|certainly|undoubtedly|beyond\s+doubt)\b",
    r"\bconfirmed\s+(sanctions\s+)?(evasion|breach|launder\w*)\b",
]
_CONCLUSION_RE = [re.compile(p, re.IGNORECASE) for p in _CONCLUSIONS]
_BAND_WORDS = [name for _, name in RISK_BANDS]
_BAND_RE = re.compile(r"\b(" + "|".join(_BAND_WORDS) + r")\s+(risk|band)\b|\bband\s+(" + "|".join(_BAND_WORDS) + r")\b", re.IGNORECASE)
_NOT_NAMES = {"THE", "NO", "IT", "ITS", "THAT", "THIS", "A", "AN", "LEAK", "GUIDANCE", "NONE", "ACCOUNTS", "REGISTERED", "ACTIVITY", "TYPOLOGIES", "UK", "AT", "BASIS", "LINK", "EXAMPLES", "SANCTIONS", "COMPANY", "ENTITY", "DECLARED"}
_SAFE_SMALL_NUMBERS: set[str] = set()


@dataclass
class ClaimCheck:
    """Outcome of verifying one claim."""

    claim: Claim
    supported: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    """Outcome of verifying a whole narrative."""

    checks: list[ClaimCheck]

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def supported(self) -> int:
        return sum(1 for check in self.checks if check.supported)

    @property
    def supported_ratio(self) -> float:
        return self.supported / self.total if self.total else 1.0

    def rejected(self) -> list[ClaimCheck]:
        return [check for check in self.checks if not check.supported]

    def as_dict(self) -> dict:
        return {
            "claims": self.total,
            "supported": self.supported,
            "supported_ratio": round(self.supported_ratio, 4),
            "rejected": [{"text": c.claim.text, "reasons": c.reasons} for c in self.rejected()],
        }


def _numbers(text: str) -> set[str]:
    cleaned = _ITEM_ID.sub(" ", text)
    out = set()
    for token in _NUMBER.findall(cleaned):
        out.add(token)
        if "." in token:
            out.add(token.rstrip("0").rstrip("."))
        else:
            out.add(token.lstrip("0") or "0")
    return out


def _name_spans(text: str) -> list[str]:
    """Runs of two or more capitalised words, which is how names appear.

    Registry company names are upper case and person names are title case,
    so a run of capitalised words in a claim is almost always a name. Each
    run has to be found in the cited evidence. The first word of a sentence
    is ignored unless the run continues beyond it.
    """
    spans = []
    for sentence in re.split(r"(?<=[.:;])\s+", _ITEM_ID.sub(" ", text)):
        words = sentence.split()
        run: list[str] = []
        for position, raw in enumerate(words + [""]):
            word = raw.strip(".,;:()«»'\"")
            is_name = len(word) >= 2 and word[0].isupper() and word.isalpha() and word.upper() not in _NOT_NAMES
            if is_name:
                if raw[:1] in "(«" and len(run) >= 2:
                    spans.append(" ".join(run))
                    run = []
                run.append(word)
                if raw[-1:] not in ",;)»":
                    continue
            if len(run) >= 2:
                spans.append(" ".join(run))
            run = []
    return spans


def verify_claim(claim: Claim, case: CaseContext, cards: dict[str, Card]) -> ClaimCheck:
    """Apply every check to one claim."""
    reasons: list[str] = []
    evidence = case.evidence_by_id()
    cited_text = []
    if not claim.citations:
        reasons.append("no citation")
    for ident in claim.citations:
        if ident in evidence:
            cited_text.append(evidence[ident].text)
        elif ident in cards:
            cited_text.append(cards[ident].text)
        else:
            reasons.append(f"cites unknown item {ident}")
    support = " ".join(cited_text)
    support_lower = support.lower()

    allowed = _numbers(support) | _numbers(case.company_number)
    for number in sorted(_numbers(claim.text)):
        if number not in allowed and number not in _SAFE_SMALL_NUMBERS:
            reasons.append(f"number {number} is not in the cited evidence")

    claim_lower = claim.text.lower()
    for name in case.entity_names:
        lowered = name.lower()
        if lowered in claim_lower and lowered not in support_lower:
            reasons.append(f"names {name} without citing evidence about it")

    for span in _name_spans(claim.text):
        if span.lower() not in support_lower and span.lower() not in case.company_name.lower():
            reasons.append(f"names {span}, which is not in the cited evidence")

    for match in _BAND_RE.finditer(claim.text):
        word = next(group for group in match.groups() if group and group.capitalize() in _BAND_WORDS)
        if word.capitalize() != case.risk_band:
            reasons.append(f"states risk band {word.capitalize()} but the detectors computed {case.risk_band}")

    if any(pattern.search(claim.text) for pattern in _CONCLUSION_RE):
        reasons.append("asserts an offence instead of describing an indicator")

    if looks_like_injection(claim.text) and "instruction like wording" not in claim_lower:
        reasons.append("repeats instruction like text from the registry")

    return ClaimCheck(claim, not reasons, reasons)


def verify_narrative(narrative: Narrative, case: CaseContext, cards: list[Card]) -> VerificationReport:
    """Verify every claim of a narrative."""
    by_id = {card.id: card for card in cards}
    return VerificationReport([verify_claim(claim, case, by_id) for claim in narrative.all_claims()])


def keep_supported(narrative: Narrative, report: VerificationReport) -> Narrative:
    """Return a copy of the narrative without the rejected claims."""
    rejected = {id(check.claim) for check in report.rejected()}
    return Narrative(
        summary=[c for c in narrative.summary if id(c) not in rejected],
        findings=[c for c in narrative.findings if id(c) not in rejected],
        ownership=[c for c in narrative.ownership if id(c) not in rejected],
        provider=narrative.provider,
        model=narrative.model,
    )
