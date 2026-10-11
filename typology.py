"""The typology library and the mitigation matrix.

The library is the knowledge base that grounds every narrative. Each card
describes one concealment pattern: what it is, which indicators reveal it,
why it matters and what a reviewer should do. Cards are retrieved for a case
by hybrid search over the text of its findings, so a dossier always cites
the guidance that applies to the structure it describes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import KNOWLEDGE_DIR, RagConfig
from .index import HybridIndex


@dataclass(frozen=True)
class Card:
    """One entry in the typology library."""

    id: str
    typology: str
    title: str
    summary: str
    indicators: tuple[str, ...]
    why: str
    actions: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join([self.title + ".", self.summary, "Indicators: " + "; ".join(self.indicators) + ".", self.why, "Actions: " + "; ".join(self.actions) + "."])


def load_cards(path: str | Path | None = None) -> list[Card]:
    with open(path or KNOWLEDGE_DIR / "typologies.json", "r", encoding="utf8") as handle:
        payload = json.load(handle)
    return [
        Card(c["id"], c["typology"], c["title"], c["summary"], tuple(c["indicators"]), c["why"], tuple(c["actions"]), tuple(c["sources"]))
        for c in payload["cards"]
    ]


def load_matrix(path: str | Path | None = None) -> dict:
    with open(path or KNOWLEDGE_DIR / "mitigation_matrix.json", "r", encoding="utf8") as handle:
        return json.load(handle)


class TypologyLibrary:
    """Searchable typology cards."""

    def __init__(self, cfg: RagConfig | None = None, cards: list[Card] | None = None) -> None:
        cfg = cfg or RagConfig()
        self.cards = cards or load_cards()
        self.by_id = {card.id: card for card in self.cards}
        sentences = []
        for card in self.cards:
            sentences.extend(s.strip() for s in re.split(r"(?<=[.;])\s+", card.text) if len(s.strip()) > 20)
        self.index = HybridIndex(
            [c.id for c in self.cards], [c.text for c in self.cards], k1=cfg.bm25_k1, b=cfg.bm25_b,
            dimensions=cfg.lsa_dimensions, rrf_k=cfg.rrf_k, fit_texts=[c.text for c in self.cards] + sentences,
        )

    def search(self, query: str, k: int = 4, mode: str = "hybrid") -> list[Card]:
        return [self.by_id[card_id] for card_id, _ in self.index.search(query, k=k, mode=mode)]

    def for_typology(self, typology: str) -> list[Card]:
        return [card for card in self.cards if card.typology == typology]
