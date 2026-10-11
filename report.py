"""Rendering of dossiers as Markdown.

Tables are written as HTML so that the files render the same way on every
Markdown viewer.
"""

from __future__ import annotations

import html
from pathlib import Path

from ..detect.base import TYPOLOGY_TITLES
from ..detect.engine import TYPOLOGIES
from .investigator import Dossier
from .llm import Claim


def html_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build an HTML table. Cell text is escaped."""
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>\n" for row in rows)
    return f"<table>\n<tr>{head}</tr>\n{body}</table>"


def _claims(claims: list[Claim]) -> str:
    return "\n".join(f"* {claim.text} {''.join('[' + c + ']' for c in claim.citations)}" for claim in claims) or "* Nothing to report."


def dossier_markdown(dossier: Dossier) -> str:
    """Full dossier as a Markdown document."""
    case = dossier.case
    lines = [
        f"# Due diligence dossier: {case.company_name}",
        "",
        html_table(
            ["Company number", "Risk score", "Risk band", "Typologies triggered", "Narrative source"],
            [[case.company_number, f"{case.risk_score:.2f}", case.risk_band, str(len(case.flags)), f"{dossier.audit['provider']} ({dossier.audit['model']})"]],
        ),
        "",
        *(
            [f"Registered name as filed (raw registry text, withheld from the narrative because it contains instruction like wording): {html.escape(case.registered_name)}", ""]
            if case.injection_fields else []
        ),
        "This dossier describes indicators of risk found in public and leaked records. It does not establish that any person or company has committed an offence. Every finding needs confirmation by a trained reviewer before action is taken.",
        "",
        "## Summary",
        "",
        _claims(dossier.narrative.summary),
        "",
        "## Typology scores",
        "",
        html_table(["Typology", "Score", "Triggered"], [[TYPOLOGY_TITLES[t], f"{case.scores[t]:.2f}", "yes" if t in case.flags else "no"] for t in TYPOLOGIES]),
        "",
        "## Findings",
        "",
        _claims(dossier.narrative.findings),
        "",
        "## Ownership and control",
        "",
        _claims(dossier.narrative.ownership),
        "",
        "## Recommended controls",
        "",
    ]
    if dossier.actions:
        lines.append(
            html_table(
                ["Typology", "Preventive control", "Corrective action", "Owner", "Regulatory anchor"],
                [[a["typology"], a["preventive_control"], a["corrective_action"], a["owner"], a["regulatory_anchor"]] for a in dossier.actions],
            )
        )
        for action in dossier.actions:
            if action["reviewer_steps"]:
                lines += ["", f"Reviewer steps for {action['typology']} [{action['card']}]:", ""]
                lines += [f"* {step}" for step in action["reviewer_steps"]]
    else:
        lines.append("No typology was triggered, so standard due diligence applies.")
    lines += [
        "",
        "## Evidence register",
        "",
        html_table(["Item", "Kind", "Statement", "Source"], [[e.id, e.kind, e.text, e.source] for e in case.evidence]),
        "",
        "## Typology cards retrieved",
        "",
        html_table(["Card", "Title", "Reading references"], [[c.id, c.title, "; ".join(c.sources)] for c in dossier.cards]),
        "",
        "## Verification and audit",
        "",
        html_table(
            ["Claims checked", "Claims supported", "Fallback used", "Configuration fingerprint", "Data snapshot"],
            [[
                str(dossier.verification.total), str(dossier.verification.supported), "yes" if dossier.audit["fallback_used"] else "no",
                dossier.audit["config_fingerprint"], dossier.audit["data_snapshot"],
            ]],
        ),
        "",
    ]
    if dossier.audit.get("rejected_claims"):
        lines += ["Claims written by the model and removed by the verifier:", ""]
        lines += [f"* {item['text']} ({'; '.join(item['reasons'])})" for item in dossier.audit["rejected_claims"]]
        lines.append("")
    return "\n".join(lines)


def write_dossier(dossier: Dossier, directory: str | Path, stem: str | None = None) -> Path:
    """Write a dossier to a Markdown file and return its path."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem or 'dossier_' + dossier.case.company_number}.md"
    path.write_text(dossier_markdown(dossier), encoding="utf8")
    return path
