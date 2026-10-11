"""End to end orchestration and artefact persistence.

One call to run_pipeline takes a registry (synthetic or loaded from the
public source layouts) through entity resolution, graph construction,
detection and, when labels exist, the supervised challenger model. The
resulting state can be saved to disk and reloaded by the service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import Settings
from .data.store import load_registry, save_registry
from .data.synth import Registry, generate_registry
from .detect.engine import DetectionResult, run_detection
from .detect.risk_model import RiskModelResult, train_risk_model
from .graph.build import ResolutionBundle, build_graph
from .graph.store import KnowledgeGraph
from .logging_utils import StageTimer, get_logger
from .rag.graph_retriever import GraphRetriever
from .rag.index import EntityIndex
from .rag.investigator import Investigator
from .rag.typology import TypologyLibrary

log = get_logger(__name__)


@dataclass
class PipelineState:
    """Everything produced by a pipeline run."""

    settings: Settings
    registry: Registry
    graph: KnowledgeGraph
    bundle: ResolutionBundle
    detection: DetectionResult
    model: RiskModelResult | None = None
    timer: StageTimer = field(default_factory=StageTimer)


@dataclass
class Runtime:
    """The parts of a run that the service needs to answer requests."""

    settings: Settings
    graph: KnowledgeGraph
    detection: DetectionResult
    investigator: Investigator
    entity_index: EntityIndex
    metrics: dict


def obtain_registry(settings: Settings, timer: StageTimer, regenerate: bool = False) -> Registry:
    """Load the registry from the data directory or generate and store it."""
    data_dir = settings.path("data_dir")
    meta_path = data_dir / "meta.json"
    if meta_path.exists() and not regenerate:
        with open(meta_path, "r", encoding="utf8") as handle:
            meta = json.load(handle)
        same = (not meta.get("synthetic")) or (meta.get("n_companies") == settings.synth.n_companies and meta.get("seed") == settings.synth.seed)
        if same:
            with timer.stage("load registry"):
                return load_registry(data_dir)
    with timer.stage("generate registry"):
        registry = generate_registry(settings.synth)
    with timer.stage("store registry"):
        save_registry(registry, data_dir)
    return registry


def run_pipeline(settings: Settings, registry: Registry, train_model: bool = True, timer: StageTimer | None = None) -> PipelineState:
    """Resolve, build, detect and optionally train the challenger model."""
    timer = timer or StageTimer()
    with timer.stage("entity resolution and graph build"):
        graph, bundle = build_graph(registry, settings)
    with timer.stage("detection"):
        detection = run_detection(registry, graph, bundle, settings)
    state = PipelineState(settings, registry, graph, bundle, detection, None, timer)
    labels = registry.truth.get("company_labels")
    if train_model and labels is not None and labels["suspicious"].any():
        with timer.stage("challenger model"):
            state.model = train_risk_model(
                detection.companies, labels["suspicious"].to_numpy(), detection.companies["address_node"].to_numpy(), settings.model
            )
            detection.companies["risk_model"] = state.model.oof
    return state


def build_entity_index(graph: KnowledgeGraph, settings: Settings) -> EntityIndex:
    """Name index over every node that has a name worth searching."""
    mask = np.isin(graph.kind, ["company", "person", "offshore", "foreign", "leak_officer", "sanction"])
    return EntityIndex(graph.key[mask], graph.label[mask], graph.kind[mask], rrf_k=settings.rag.rrf_k)


def build_investigator(state: PipelineState, entity_index: EntityIndex | None = None, narrator=None) -> Investigator:
    retriever = GraphRetriever(
        state.graph, state.detection, state.registry.companies, state.bundle.persons.clusters, state.registry.sanctions, state.settings
    )
    return Investigator(retriever, TypologyLibrary(state.settings.rag), state.settings, entity_index, narrator)


def save_artifacts(state: PipelineState, entity_index: EntityIndex, metrics: dict | None = None) -> Path:
    """Persist what the service needs. Truth tables are never written here."""
    root = state.settings.path("artifact_dir")
    root.mkdir(parents=True, exist_ok=True)
    state.graph.save(root / "graph.joblib")
    joblib.dump(state.detection, root / "detection.joblib", compress=3)
    joblib.dump(
        {"companies": state.registry.companies, "clusters": state.bundle.persons.clusters, "sanctions": state.registry.sanctions},
        root / "tables.joblib", compress=3,
    )
    joblib.dump(entity_index, root / "entity_index.joblib", compress=3)
    if state.model is not None:
        joblib.dump(state.model.model, root / "risk_model.joblib", compress=3)
    with open(root / "metrics.json", "w", encoding="utf8") as handle:
        json.dump(metrics or {}, handle, indent=2, default=str)
    return root


def load_runtime(settings: Settings) -> Runtime:
    """Reload saved artefacts and assemble the investigator for serving."""
    root = settings.path("artifact_dir")
    if not (root / "graph.joblib").exists():
        raise FileNotFoundError(f"no artefacts in {root}; run the build or benchmark command first")
    graph = KnowledgeGraph.load(root / "graph.joblib")
    detection: DetectionResult = joblib.load(root / "detection.joblib")
    tables: dict[str, pd.DataFrame] = joblib.load(root / "tables.joblib")
    entity_index: EntityIndex = joblib.load(root / "entity_index.joblib")
    retriever = GraphRetriever(graph, detection, tables["companies"], tables["clusters"], tables["sanctions"], settings)
    investigator = Investigator(retriever, TypologyLibrary(settings.rag), settings, entity_index)
    metrics = {}
    if (root / "metrics.json").exists():
        with open(root / "metrics.json", "r", encoding="utf8") as handle:
            metrics = json.load(handle)
    return Runtime(settings, graph, detection, investigator, entity_index, metrics)
