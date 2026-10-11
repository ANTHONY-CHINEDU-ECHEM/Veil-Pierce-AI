import pandas as pd

from veilpierce.config import SynthConfig
from veilpierce.data.synth import TABLE_NAMES, TYPOLOGIES, generate_registry


def test_generation_is_deterministic():
    a = generate_registry(SynthConfig(n_companies=3000, seed=5))
    b = generate_registry(SynthConfig(n_companies=3000, seed=5))
    for name in TABLE_NAMES:
        pd.testing.assert_frame_equal(getattr(a, name), getattr(b, name))
    c = generate_registry(SynthConfig(n_companies=3000, seed=6))
    assert not a.companies["company_name"].equals(c.companies["company_name"])


def test_tables_are_consistent(registry):
    companies = registry.companies
    assert companies["company_number"].is_unique
    assert companies["company_number"].str.len().eq(8).all()
    known = set(companies["company_number"])
    assert set(registry.officers["company_number"]) <= known
    assert set(registry.pscs["company_number"]) <= known
    assert set(registry.pscs["kind"]) == {"individual", "corporate", "statement"}
    dissolved = companies["dissolution_date"].notna()
    assert (companies.loc[dissolved, "dissolution_date"] > companies.loc[dissolved, "incorporation_date"]).all()
    assert (companies.loc[dissolved, "status"] == "Dissolved").all()
    nodes = set(registry.offshore_entities["node_id"]) | set(registry.offshore_officers["node_id"])
    assert set(registry.offshore_edges["start_id"]) <= nodes
    assert set(registry.offshore_edges["end_id"]) <= set(registry.offshore_entities["node_id"])


def test_every_typology_is_planted_with_lookalikes(labels):
    for typology in TYPOLOGIES:
        assert labels[typology].sum() > 0, typology
    prevalence = labels["suspicious"].mean()
    assert 0.02 < prevalence < 0.2
    kinds = set(labels["hard_negative"]) - {""}
    assert {"benign_agent", "professional_director", "group_tree", "foreign_parent", "spv_batch"} <= kinds
    assert not (labels["suspicious"] & (labels["hard_negative"] != "")).any()


def test_truth_never_leaks_into_the_working_tables(registry):
    for name in TABLE_NAMES:
        columns = set(getattr(registry, name).columns)
        assert not {c for c in columns if c.startswith("true_")}, name


def test_sanctioned_parties_use_variant_spellings(registry):
    truth = registry.truth["sanctions"]
    assert truth["linked"].sum() > 0
    assert set(truth["link_kind"]) >= {"registry_person", "leak_officer", "offshore_entity"}
    reach = registry.truth["sanction_reach"]
    assert reach["hops"].between(1, 4).all()
