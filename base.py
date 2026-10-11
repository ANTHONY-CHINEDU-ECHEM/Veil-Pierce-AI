"""Shared definitions for the detectors."""

from __future__ import annotations

from dataclasses import dataclass, field

TYPOLOGY_CODES = {
    "nominee": "NOM",
    "address_factory": "FAC",
    "circular": "CIR",
    "sanctions": "SAN",
    "opaque": "OPQ",
    "phoenix_burst": "PHX",
}
TYPOLOGY_TITLES = {
    "nominee": "Nominee director network",
    "address_factory": "Mass registration address",
    "circular": "Circular ownership",
    "sanctions": "Sanctions proximity",
    "opaque": "Opaque offshore ownership",
    "phoenix_burst": "Burst incorporation and phoenix activity",
}
FUSION_WEIGHTS = {
    "nominee": 0.9,
    "address_factory": 0.85,
    "circular": 0.95,
    "sanctions": 1.0,
    "opaque": 0.85,
    "phoenix_burst": 0.8,
}
FLAG_THRESHOLDS = {
    "nominee": 0.5,
    "address_factory": 0.5,
    "circular": 0.5,
    "sanctions": 0.3,
    "opaque": 0.5,
    "phoenix_burst": 0.5,
}
RISK_BANDS = ((0.85, "Critical"), (0.65, "High"), (0.4, "Medium"), (0.0, "Low"))
UK_RESIDENCE = {"ENGLAND", "UNITED KINGDOM", "SCOTLAND", "WALES", "NORTHERN IRELAND", "GREAT BRITAIN", "UK", ""}


def risk_band(score: float) -> str:
    """Translate a score between 0 and 1 into a named risk band."""
    for floor, name in RISK_BANDS:
        if score >= floor:
            return name
    return "Low"


@dataclass
class Finding:
    """One typology finding for one company, with the facts that support it."""

    typology: str
    score: float
    headline: str
    facts: dict = field(default_factory=dict)
    edge_ids: list[int] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    card_ids: list[str] = field(default_factory=list)

    @property
    def code(self) -> str:
        return TYPOLOGY_CODES[self.typology]

    @property
    def title(self) -> str:
        return TYPOLOGY_TITLES[self.typology]
