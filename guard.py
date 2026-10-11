"""Prompt injection guard for registry free text.

Company names, officer occupations and legal form fields are typed by the
filer. Anyone who expects their filings to be read by a language model can
register a company whose name is an instruction. The guard treats every
registry string as untrusted data: it detects instruction like wording,
strips markup and control characters, truncates over long values and wraps
the result in explicit data delimiters before it can reach a prompt.

The guard is one of three layers. The second is architectural: the risk
score is computed by deterministic code, so a model that was fooled could
still not change a verdict. The third is the citation verifier, which
rejects any narrative claim that the retrieved evidence does not support.
"""

from __future__ import annotations

import hashlib
import re

_PATTERNS = [
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instruction|instructions|prompt|rules|context|evidence|guidelines)\b",
    r"\b(system|developer|admin)\s+(prompt|mode|message|says|override)\b",
    r"\byou\s+(are\s+now|must|should|will)\b",
    r"\b(assistant|language\s+model|ai|chatbot|llm)\b.{0,30}\b(must|should|do\s+not|report|mark|rate|state|output)\b",
    r"\bnew\s+instructions?\b",
    r"\b(mark|rate|score|report|describe|state)\b.{0,40}\b(low\s+risk|risk\s+score\s+zero|no\s+adverse|approved|verified|compliant|trusted)\b",
    r"\b(delete|clear|remove)\b.{0,20}\b(all\s+)?(red\s+)?flags?\b",
    r"\bend\s+of\s+(evidence|context|document)\b",
    r"\bdo\s+not\s+mention\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]
_MARKUP = re.compile(r"[<>{}\[\]`]|\\n|\\r")
_CONTROL = re.compile(r"[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f\x7f]")
MAX_FIELD_LENGTH = 160


def injection_signals(text: object) -> list[str]:
    """Return the patterns that make a string look like an instruction."""
    value = "" if text is None else str(text)
    return [pattern.pattern for pattern in _COMPILED if pattern.search(value)]


def looks_like_injection(text: object) -> bool:
    """True when a registry string contains instruction like wording."""
    value = "" if text is None else str(text)
    return any(pattern.search(value) for pattern in _COMPILED)


def sanitise_field(text: object) -> str:
    """Make a registry string safe to place inside a prompt as quoted data."""
    value = "" if text is None else str(text)
    value = _CONTROL.sub(" ", value)
    value = _MARKUP.sub(" ", value)
    value = " ".join(value.split())
    if len(value) > MAX_FIELD_LENGTH:
        value = value[:MAX_FIELD_LENGTH].rstrip() + " (truncated)"
    return value


def quote_data(text: object) -> str:
    """Return a registry value in the form that is allowed into a narrative.

    Ordinary values are sanitised and returned. A value that reads like an
    instruction is withheld completely and replaced by a neutral reference,
    so the hostile wording never reaches a prompt or a narrative. The
    reference is stable, which keeps two withheld names in one case apart.
    The original text stays available to human reviewers in the dossier
    header, where it is labelled as raw registry text.
    """
    value = sanitise_field(text)
    if looks_like_injection(value):
        digest = hashlib.sha256(value.encode("utf8")).hexdigest()[:6]
        token = "".join("abcdefghijklmnop"[int(ch, 16)] for ch in digest)
        return f"name withheld by the injection guard (reference {token})"
    return value
