"""Narrators: the offline grounded composer and language model providers.

Three ways of producing the narrative share one interface.

OfflineNarrator composes the narrative directly from the retrieved evidence
with fixed sentence patterns. It needs no network, no key and no model, it
is fully reproducible, and it is the default. Every benchmark figure in this
repository was produced with it.

LLMNarrator sends the same evidence to a hosted or local language model and
parses its JSON reply. Providers are thin wrappers over the vendor SDKs and
are imported lazily, so the SDKs are optional. The model identifier is read
from configuration or the VEILPIERCE_LLM_MODEL environment variable and is
never stored in code.

Whatever a model writes is passed through the citation verifier before it
reaches a dossier.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

from ..config import RagConfig
from ..detect.base import TYPOLOGY_TITLES
from ..logging_utils import get_logger
from .graph_retriever import CaseContext
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .typology import Card

log = get_logger(__name__)


@dataclass
class Claim:
    """One sentence of a narrative with the items it cites."""

    text: str
    citations: list[str]


@dataclass
class Narrative:
    """A dossier narrative split into three sections."""

    summary: list[Claim] = field(default_factory=list)
    findings: list[Claim] = field(default_factory=list)
    ownership: list[Claim] = field(default_factory=list)
    provider: str = "offline"
    model: str = "grounded composer"

    def all_claims(self) -> list[Claim]:
        return self.summary + self.findings + self.ownership


class Provider(Protocol):
    """Anything that can turn a system and a user prompt into text."""

    name: str
    model: str

    def generate(self, system: str, user: str) -> str: ...


class OfflineNarrator:
    """Deterministic narrator that writes only what the evidence states."""

    provider = "offline"
    model = "grounded composer"

    def narrate(self, case: CaseContext, cards: list[Card], question: str | None = None) -> Narrative:
        narrative = Narrative(provider=self.provider, model=self.model)
        count = len(case.flags)
        triggered = ", ".join(TYPOLOGY_TITLES[t] for t in case.flags)
        narrative.summary.append(
            Claim(f"{case.company_name} (company {case.company_number}) has a fused risk score of {case.risk_score:.2f}, which places it in the {case.risk_band} band.", ["M01"])
        )
        if count:
            narrative.summary.append(Claim(f"{count} of the six concealment typologies are triggered: {triggered}.", ["M01"]))
        else:
            narrative.summary.append(Claim("None of the six concealment typologies is triggered for this company.", ["M01"]))
        profile = case.profile
        ended = f" and was dissolved on {profile['dissolved']}" if profile.get("dissolved") else ""
        narrative.summary.append(
            Claim(
                f"The company was incorporated on {profile['incorporated']}{ended}. Its status is {profile['status']} and its accounts category is {profile['accounts']}.",
                [profile["profile_evidence"]],
            )
        )
        if case.injection_fields:
            guard = [item.id for item in case.evidence if item.kind == "guard"]
            narrative.summary.append(Claim("The registered name contains instruction like wording, which is itself an indicator that the filer expected automated review. It is withheld from this narrative and was treated as data.", guard))

        card_by_typology: dict[str, Card] = {}
        for card in cards:
            card_by_typology.setdefault(card.typology, card)
        for finding in case.findings:
            cites = list(finding.evidence_ids)
            card = next((c for c in cards if c.id in finding.card_ids), None) or card_by_typology.get(finding.typology)
            narrative.findings.append(Claim(f"{finding.title} (score {finding.score:.2f}). {finding.headline}", cites + ["M01"]))
            if card is not None:
                narrative.findings.append(Claim(f"Guidance on this pattern: {card.why}", [card.id]))

        evidence = case.evidence_by_id()
        for ident in profile.get("control_evidence", [])[:4] + [e for e in profile.get("chain_evidence", []) if e not in profile.get("control_evidence", [])][:6]:
            narrative.ownership.append(Claim(evidence[ident].text, [ident]))
        for ident in profile.get("officer_evidence", [])[:3]:
            narrative.ownership.append(Claim(evidence[ident].text, [ident]))
        return narrative


class LLMNarrator:
    """Narrator backed by a language model provider."""

    def __init__(self, provider: Provider) -> None:
        self._provider = provider
        self.provider = provider.name
        self.model = provider.model

    def narrate(self, case: CaseContext, cards: list[Card], question: str | None = None) -> Narrative:
        raw = self._provider.generate(SYSTEM_PROMPT, build_user_prompt(case, cards, question))
        return parse_narrative(raw, self.provider, self.model)


def parse_narrative(raw: str, provider: str, model: str) -> Narrative:
    """Parse the JSON reply of a model. Raises ValueError on malformed output."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model reply contains no JSON object")
    payload = json.loads(raw[start: end + 1])
    narrative = Narrative(provider=provider, model=model)
    for section in ("summary", "findings", "ownership"):
        for item in payload.get(section, []) or []:
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            cites = [str(c).strip().strip("[]") for c in item.get("citations", []) or []]
            cites += re.findall(r"\[([EMT]\d{2})\]", str(item["text"]))
            text = re.sub(r"\s*\[[EMT]\d{2}\]", "", str(item["text"])).strip()
            getattr(narrative, section).append(Claim(text, list(dict.fromkeys(cites))))
    return narrative


class AnthropicProvider:
    """Provider for the Anthropic Messages API. Needs the anthropic package."""

    name = "anthropic"

    def __init__(self, model: str, max_tokens: int = 1800, temperature: float = 0.0) -> None:
        import anthropic

        if not model:
            raise ValueError("set VEILPIERCE_LLM_MODEL to the model identifier to use")
        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = anthropic.Anthropic()

    def generate(self, system: str, user: str) -> str:
        reply = self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in reply.content if getattr(block, "type", "") == "text")


class OpenAICompatibleProvider:
    """Provider for any endpoint that speaks the OpenAI chat protocol.

    This covers hosted services and local servers. Set VEILPIERCE_LLM_BASE_URL
    to point at a local server. Needs the openai package.
    """

    name = "openai_compatible"

    def __init__(self, model: str, max_tokens: int = 1800, temperature: float = 0.0) -> None:
        import openai

        if not model:
            raise ValueError("set VEILPIERCE_LLM_MODEL to the model identifier to use")
        self.model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = openai.OpenAI(base_url=os.environ.get("VEILPIERCE_LLM_BASE_URL") or None)

    def generate(self, system: str, user: str) -> str:
        reply = self._client.chat.completions.create(
            model=self.model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return reply.choices[0].message.content or ""


class ScriptedProvider:
    """Provider that replays prepared replies. Used to test the verifier."""

    name = "scripted"
    model = "scripted replies"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        if not self._replies:
            raise RuntimeError("no scripted reply left")
        return self._replies.pop(0)


def make_narrator(cfg: RagConfig):
    """Build the narrator named in the configuration."""
    provider = (cfg.provider or "offline").lower()
    if provider == "offline":
        return OfflineNarrator()
    if provider == "anthropic":
        return LLMNarrator(AnthropicProvider(cfg.model, cfg.max_tokens, cfg.temperature))
    if provider in ("openai", "openai_compatible"):
        return LLMNarrator(OpenAICompatibleProvider(cfg.model, cfg.max_tokens, cfg.temperature))
    raise ValueError(f"unknown narrative provider: {cfg.provider}")
