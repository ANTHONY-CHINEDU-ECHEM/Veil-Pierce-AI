"""Typed configuration for Veil Pierce AI.

Every tunable number in the system lives here or in veilpierce/default.yaml. The
command line accepts overrides written as section.key=value so that a run can
be reproduced from its recorded settings alone.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "default.yaml"
KNOWLEDGE_DIR = PACKAGE_DIR / "knowledge"


def project_root() -> Path:
    """Folder that relative output paths resolve against: the working directory."""
    return Path.cwd()


@dataclass
class SynthConfig:
    """Size and composition of the synthetic registry.

    Counts for the planted typologies are expressed per 200,000 companies and
    are scaled with the number of companies requested.
    """

    n_companies: int = 250_000
    seed: int = 7
    snapshot_date: str = "2026/09/30"
    n_nominees: int = 22
    nominee_min_companies: int = 30
    nominee_max_companies: int = 420
    n_professional_directors: int = 70
    n_factories: int = 16
    factory_min_companies: int = 150
    factory_max_companies: int = 900
    n_benign_agents: int = 22
    n_rings: int = 300
    ring_offshore_share: float = 0.35
    n_sanctions_entries: int = 1200
    n_sanctions_linked: int = 150
    n_namesakes: int = 320
    n_opaque_chains: int = 1500
    n_benign_foreign_parents: int = 1100
    n_burst_batches: int = 120
    n_phoenix_chains: int = 150
    n_benign_spv_batches: int = 70
    n_injection_names: int = 40
    offshore_entity_ratio: float = 0.2
    background_name_noise: float = 0.12
    nominee_name_noise: float = 0.6


@dataclass
class ResolutionConfig:
    """Thresholds for person, corporate and sanctions matching."""

    surname_similarity: float = 0.92
    forename_similarity: float = 0.88
    corporate_similarity: float = 93.0
    sanctions_threshold: float = 0.86
    sanctions_review_threshold: float = 0.74
    name_only_cap: float = 0.8
    max_block_size: int = 400


@dataclass
class DetectConfig:
    """Detector thresholds. Each one is explained in docs/methodology.md."""

    nominee_min_companies: int = 25
    nominee_score_threshold: float = 0.5
    factory_min_companies: int = 60
    factory_score_threshold: float = 0.5
    sanctions_max_hops: int = 4
    sanctions_hop_decay: float = 0.75
    control_max_depth: int = 8
    burst_min_batch: int = 5
    phoenix_gap_days: int = 120
    phoenix_name_similarity: float = 88.0
    short_life_days: int = 730
    alert_threshold: float = 0.5


@dataclass
class ModelConfig:
    """Supervised risk model settings."""

    n_folds: int = 5
    learning_rate: float = 0.08
    max_iter: int = 220
    max_leaf_nodes: int = 31
    l2_regularization: float = 1.0
    seed: int = 11


@dataclass
class RagConfig:
    """Retrieval and narrative settings."""

    bm25_k1: float = 1.4
    bm25_b: float = 0.75
    lsa_dimensions: int = 96
    rrf_k: int = 60
    top_k_typologies: int = 4
    max_evidence_items: int = 40
    max_cohabitants_listed: int = 6
    provider: str = "offline"
    model: str = ""
    max_tokens: int = 1800
    temperature: float = 0.0
    min_supported_ratio: float = 0.9
    entity_index_sample: int = 60_000


@dataclass
class Settings:
    """Top level settings object passed through the pipeline."""

    synth: SynthConfig = field(default_factory=SynthConfig)
    resolution: ResolutionConfig = field(default_factory=ResolutionConfig)
    detect: DetectConfig = field(default_factory=DetectConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    rag: RagConfig = field(default_factory=RagConfig)
    data_dir: str = "data/generated"
    artifact_dir: str = "artifacts"
    report_dir: str = "reports"
    figure_dir: str = "docs/figures"
    opacity_weights: dict[str, float] = field(default_factory=dict)
    jurisdiction_aliases: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        """Stable short hash of the full configuration, stored with every dossier."""
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf8")).hexdigest()[:12]

    def path(self, name: str) -> Path:
        """Resolve one of the directory settings against the working directory."""
        raw = Path(getattr(self, name))
        return raw if raw.is_absolute() else project_root() / raw


def _coerce(value: str, current: Any) -> Any:
    """Convert a command line string into the type of the existing value."""
    if isinstance(current, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(float(value))
    if isinstance(current, float):
        return float(value)
    return value


def _apply(target: Any, updates: dict[str, Any]) -> None:
    names = {f.name for f in fields(target)}
    for key, value in updates.items():
        if key not in names:
            raise KeyError(f"unknown configuration key: {key}")
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value)
        else:
            setattr(target, key, value)


def load_settings(path: str | os.PathLike | None = None, overrides: list[str] | None = None) -> Settings:
    """Load settings from YAML and apply section.key=value overrides.

    Environment variables VEILPIERCE_LLM_PROVIDER and VEILPIERCE_LLM_MODEL take
    precedence over the file so that credentials and model choices never need
    to be committed.
    """
    settings = Settings()
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if config_path.exists():
        with open(config_path, "r", encoding="utf8") as handle:
            loaded = yaml.safe_load(handle) or {}
        _apply(settings, loaded)
    for item in overrides or []:
        if "=" not in item:
            raise ValueError(f"override must look like section.key=value, got: {item}")
        dotted, raw = item.split("=", 1)
        parts = dotted.strip().split(".")
        target: Any = settings
        for part in parts[:-1]:
            target = getattr(target, part)
        leaf = parts[-1]
        if not hasattr(target, leaf):
            raise KeyError(f"unknown configuration key: {dotted}")
        setattr(target, leaf, _coerce(raw, getattr(target, leaf)))
    provider = os.environ.get("VEILPIERCE_LLM_PROVIDER")
    if provider:
        settings.rag.provider = provider
    model = os.environ.get("VEILPIERCE_LLM_MODEL")
    if model:
        settings.rag.model = model
    return settings
