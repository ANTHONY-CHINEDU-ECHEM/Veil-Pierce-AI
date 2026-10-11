"""Shared fixtures: one small synthetic registry taken through the full pipeline."""

from __future__ import annotations

import pytest

from veilpierce.config import load_settings
from veilpierce.data.synth import generate_registry
from veilpierce.pipeline import build_entity_index, build_investigator, run_pipeline

TEST_COMPANIES = 12_000


@pytest.fixture(scope="session")
def settings():
    return load_settings(
        overrides=[
            f"synth.n_companies={TEST_COMPANIES}",
            "synth.seed=21",
            "detect.nominee_min_companies=21",
            "detect.factory_min_companies=25",
        ]
    )


@pytest.fixture(scope="session")
def registry(settings):
    return generate_registry(settings.synth)


@pytest.fixture(scope="session")
def state(settings, registry):
    return run_pipeline(settings, registry, train_model=False)


@pytest.fixture(scope="session")
def entity_index(state, settings):
    return build_entity_index(state.graph, settings)


@pytest.fixture(scope="session")
def investigator(state, entity_index):
    return build_investigator(state, entity_index)


@pytest.fixture(scope="session")
def labels(registry):
    return registry.truth["company_labels"]


@pytest.fixture(scope="session")
def flagged_numbers(state):
    """One company number per typology that the detectors flagged."""
    cf = state.detection.companies
    out = {}
    for typology in ("nominee", "address_factory", "circular", "sanctions", "opaque", "phoenix_burst"):
        hits = cf[cf[f"flag_{typology}"]].sort_values("risk_rules", ascending=False)
        if len(hits):
            out[typology] = hits["company_number"].iloc[0]
    return out
