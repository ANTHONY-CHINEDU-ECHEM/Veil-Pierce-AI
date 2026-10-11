"""Repository writing rule: no hyphen and no dash characters in prose.

The rule covers every documentation, configuration and knowledge file, and
inside Python files it covers comments, docstrings and string literals. The
only place the ASCII 45 character may appear is as the arithmetic minus
operator in code. The characters are built from their codes here so that
this file obeys the rule it enforces.
"""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {chr(45): "hyphen", chr(8211): "en dash", chr(8212): "em dash", chr(8209): "non breaking hyphen", chr(8722): "minus sign"}
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt", ".cfg", ".toml", ".example", ".sh"}
TEXT_NAMES = {"Makefile", "Dockerfile", "LICENSE", ".gitignore", ".dockerignore"}
SKIP_ANYWHERE = {".git", "__pycache__", ".pytest_cache"}
SKIP_AT_ROOT = {"artifacts", "data", "build", "dist"}


def _files():
    for path in sorted(ROOT.rglob("*")):
        parts = path.relative_to(ROOT).parts
        if not path.is_file() or parts[0] in SKIP_AT_ROOT or any(part in SKIP_ANYWHERE or part.endswith("info") for part in parts[:len(parts) - 1]):
            continue
        yield path


def text_violations() -> list[str]:
    found = []
    for path in _files():
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        for number, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
            for char, label in FORBIDDEN.items():
                if char in line:
                    found.append(f"{path.relative_to(ROOT)}:{number}: {label}: {line.strip()[:90]}")
    return found


def python_violations() -> list[str]:
    checked = {tokenize.STRING, tokenize.COMMENT}
    middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    if middle is not None:
        checked.add(middle)
    found = []
    for path in _files():
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf8")
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in checked:
                for char, label in FORBIDDEN.items():
                    if char in token.string:
                        found.append(f"{path.relative_to(ROOT)}:{token.start[0]}: {label} in text: {token.string.strip()[:90]}")
    return found


def test_no_hyphens_in_documents():
    problems = text_violations()
    assert not problems, "\n".join(problems[:40])


@pytest.mark.skipif(sys.version_info < (3, 12), reason="f string contents are tokenised separately from Python 3.12")
def test_no_hyphens_in_python_text():
    problems = python_violations()
    assert not problems, "\n".join(problems[:40])


def test_file_names_have_no_hyphens():
    bad = [str(p.relative_to(ROOT)) for p in _files() if any(char in p.name for char in FORBIDDEN)]
    assert not bad, "\n".join(bad)
