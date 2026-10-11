"""HTTP service for Veil Pierce AI.

The service loads the artefacts written by the build or benchmark command
and answers requests from them. It never recomputes scores on request, so
every response is reproducible from the stored snapshot.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .. import __version__
from ..detect.base import TYPOLOGY_TITLES
from ..detect.engine import TYPOLOGIES
from ..pipeline import Runtime
from ..rag.report import dossier_markdown
from ..rag.typology import load_matrix


class Question(BaseModel):
    """Body of a question request."""

    question: str = Field(min_length=3, max_length=500, description="Free text question that names a company or gives its number")


def create_app(runtime: Runtime) -> FastAPI:
    """Build the FastAPI application around loaded artefacts."""
    app = FastAPI(
        title="Veil Pierce AI",
        version=__version__,
        description="Beneficial ownership opacity and sanctions evasion detection with graph retrieval and cited narratives.",
    )
    cf = runtime.detection.companies
    row_of = dict(zip(cf["company_number"], range(len(cf))))

    def company_row(number: str):
        if number not in row_of:
            raise HTTPException(status_code=404, detail=f"company {number} is not in the loaded snapshot")
        return cf.iloc[row_of[number]]

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "companies": int(len(cf)),
            "graph": runtime.graph.describe(),
            "narrator": f"{runtime.investigator.narrator.provider} ({runtime.investigator.narrator.model})",
            "data_snapshot": runtime.graph.meta.get("snapshot_date", ""),
        }

    @app.get("/entities/search")
    def search(q: str = Query(min_length=2, max_length=200), k: int = Query(default=5, ge=1, le=25), kind: str | None = None) -> dict:
        return {"query": q, "results": runtime.entity_index.search(q, k=k, kind=kind)}

    @app.get("/companies/top")
    def top(limit: int = Query(default=20, ge=1, le=200), typology: str | None = None) -> dict:
        frame = cf
        if typology:
            if typology not in TYPOLOGIES:
                raise HTTPException(status_code=422, detail=f"typology must be one of {TYPOLOGIES}")
            frame = cf[cf[f"flag_{typology}"]]
        best = frame.sort_values("risk_rules", ascending=False).head(limit)
        return {
            "results": [
                {"company_number": r.company_number, "company_name": r.company_name, "risk_score": round(float(r.risk_rules), 2), "risk_band": r.risk_band, "typologies": int(r.n_flags)}
                for r in best.itertuples(index=False)
            ]
        }

    @app.get("/companies/{number}/risk")
    def risk(number: str) -> dict:
        row = company_row(number)
        return {
            "company_number": number,
            "company_name": row["company_name"],
            "risk_score": round(float(row["risk_rules"]), 2),
            "risk_band": row["risk_band"],
            "typology_scores": {TYPOLOGY_TITLES[t]: round(float(row[f"score_{t}"]), 2) for t in TYPOLOGIES},
            "typologies_triggered": [TYPOLOGY_TITLES[t] for t in TYPOLOGIES if bool(row[f"flag_{t}"])],
        }

    @app.get("/companies/{number}/dossier")
    def dossier(number: str, format: str = Query(default="json", pattern="^(json|markdown)$")) -> dict:
        company_row(number)
        result = runtime.investigator.investigate(number)
        if format == "markdown":
            return {"company_number": number, "markdown": dossier_markdown(result)}
        return result.to_dict()

    @app.get("/companies/{number}/graph")
    def graph(number: str) -> dict:
        company_row(number)
        case = runtime.investigator.retriever.retrieve(number)
        from ..rag.graph_retriever import subgraph_frame

        return {"company_number": number, "edges": subgraph_frame(runtime.graph, case.subgraph_edges).to_dict("records")}

    @app.post("/ask")
    def ask(body: Question) -> dict:
        return runtime.investigator.ask(body.question).to_dict()

    @app.get("/typologies")
    def typologies() -> dict:
        cards = runtime.investigator.library.cards
        return {"cards": [{"id": c.id, "typology": c.typology, "title": c.title, "summary": c.summary, "indicators": list(c.indicators), "actions": list(c.actions), "sources": list(c.sources)} for c in cards]}

    @app.get("/mitigations")
    def mitigations() -> dict:
        return load_matrix()

    @app.get("/metrics")
    def metrics() -> dict:
        slim = {k: v for k, v in runtime.metrics.items() if k != "detection"}
        if "detection" in runtime.metrics:
            slim["detection"] = {k: v for k, v in runtime.metrics["detection"].items() if k != "pr_curves"}
        return slim

    return app


def app_from_settings():
    """Factory used by ASGI servers: loads artefacts from the configured folder."""
    from ..config import load_settings
    from ..pipeline import load_runtime

    return create_app(load_runtime(load_settings()))
