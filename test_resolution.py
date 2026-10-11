import pandas as pd

from veilpierce.config import ResolutionConfig
from veilpierce.evaluation.evaluate import evaluate_resolution, evaluate_screening
from veilpierce.resolution.persons import _names_compatible, resolve_persons
from veilpierce.resolution.sanctions import _ordered_similarity, _tokens_align, screen_entities, screen_persons

CFG = ResolutionConfig()


def test_name_compatibility_rules():
    assert _names_compatible(("HARGREAVES", "SIMON", "PETER"), ("HARGREAVES", "SIMON", ""), CFG)
    assert _names_compatible(("HARGREAVES", "SIMON", "PETER"), ("HARGREAVES", "SIMON", "P"), CFG)
    assert _names_compatible(("HARGREAVES", "SIMON", ""), ("HARGREEAVES", "SIMON", ""), CFG)
    assert _names_compatible(("HARGREAVES", "S", ""), ("HARGREAVES", "SIMON", ""), CFG)
    assert not _names_compatible(("HARGREAVES", "SIMON", "PETER"), ("HARGREAVES", "SIMON", "JOHN"), CFG)
    assert not _names_compatible(("HARGREAVES", "SIMON", ""), ("WHITLOCK", "SIMON", ""), CFG)
    assert not _names_compatible(("HARGREAVES", "SIMON", ""), ("HARGREAVES", "HELEN", ""), CFG)


def _officers(rows):
    frame = pd.DataFrame(rows, columns=["officer_name", "dob_year", "dob_month", "company_number"])
    frame["appointment_id"] = range(len(frame))
    frame["officer_kind"] = "person"
    frame["country_of_residence"] = "England"
    return frame


def test_spelling_variants_resolve_to_one_person_but_birth_dates_keep_people_apart():
    officers = _officers(
        [
            ("HARGREAVES, Simon Peter", 1970, 3, "00000001"),
            ("HARGREAVES, Simon", 1970, 3, "00000002"),
            ("HARGREAVES, Simon P", 1970, 3, "00000003"),
            ("HARGRAEVES, Simon Peter", 1970, 3, "00000004"),
            ("HARGREAVES, Simon Peter", 1971, 3, "00000005"),
            ("WHITLOCK, Simon Peter", 1970, 3, "00000006"),
        ]
    )
    pscs = pd.DataFrame(columns=["psc_id", "kind", "name", "dob_year", "dob_month", "company_number", "country_of_residence"])
    result = resolve_persons(officers, pscs, CFG)
    clusters = result.records.sort_values("record_id")["cluster_id"].tolist()
    assert len(set(clusters[:4])) == 1
    assert clusters[4] not in clusters[:4]
    assert clusters[5] not in clusters[:4]
    assert result.records["exact_id"].nunique() == 6


def test_resolution_beats_exact_matching_on_the_registry(state):
    metrics = evaluate_resolution(state)
    exact, resolved = metrics["persons"]["exact_matching"], metrics["persons"]["entity_resolution"]
    assert resolved["precision"] > 0.98
    assert resolved["recall"] > exact["recall"] + 0.3
    assert metrics["corporates"]["accuracy"] > 0.97
    recovery = metrics["nominee_recovery"]
    assert recovery["share_of_appointments_seen_after_resolution"] > recovery["share_of_appointments_seen_with_exact_names"] + 0.2
    assert metrics["addresses"]["mean_share_recovered_resolved"] > 0.95
    assert metrics["addresses"]["mean_share_recovered_raw"] < 0.6


SANCTIONS = pd.DataFrame(
    [
        {"entity_id": "S1", "schema": "Person", "name": "Dmitri Pavel Sokolov", "aliases": "SOKOLOV Dmitry Pavel", "birth_year": 1965, "birth_month": 4},
        {"entity_id": "S2", "schema": "Person", "name": "Layla Noor Haddad", "aliases": "", "birth_year": 0, "birth_month": 0},
        {"entity_id": "S3", "schema": "Company", "name": "BEACON GRANITE SHIPPING LTD", "aliases": "Beacon Granite Shipping Co", "birth_year": 0, "birth_month": 0},
    ]
)


def _screen(name, year, month):
    candidates = pd.DataFrame([{"node_key": "P:1", "name": name, "dob_year": year, "dob_month": month}])
    return screen_persons(SANCTIONS, candidates, CFG)


def test_confirmed_match_needs_name_and_date_of_birth():
    hit = _screen("DMITRY PAVEL SOKOLOV", 1965, 4)
    assert len(hit) == 1 and hit["decision"].iat[0] == "match" and hit["score"].iat[0] >= CFG.sanctions_threshold


def test_namesake_with_another_birth_year_is_not_alerted():
    assert _screen("DMITRI PAVEL SOKOLOV", 1980, 4).empty


def test_same_year_but_other_month_is_review_only():
    hit = _screen("DMITRI PAVEL SOKOLOV", 1965, 9)
    assert len(hit) == 1 and hit["decision"].iat[0] == "review"


def test_name_only_match_is_capped_at_review():
    hit = _screen("DMITRI PAVEL SOKOLOV", 0, 0)
    assert len(hit) == 1 and hit["decision"].iat[0] == "review" and hit["score"].iat[0] <= CFG.name_only_cap
    hit = _screen("LAYLA NOOR HADDAD", 1990, 1)
    assert len(hit) == 1 and hit["decision"].iat[0] == "review"


def test_shared_forenames_with_a_different_surname_do_not_match():
    assert _screen("DMITRI PAVEL VOLKOV", 1965, 4).empty
    assert not _tokens_align("DMITRI PAVEL VOLKOV", "DMITRI PAVEL SOKOLOV")
    assert _tokens_align("DMITRY PAVEL SOKOLOV", "SOKOLOV DMITRI PAVEL")


def test_surname_first_order_is_tolerated_but_swapped_forenames_are_not():
    assert _ordered_similarity("DMITRI PAVEL SOKOLOV", "SOKOLOV DMITRI PAVEL") > 0.95
    assert _ordered_similarity("DMITRI PAVEL SOKOLOV", "PAVEL DMITRI SOKOLOV") < 0.93


def test_entity_screening_requires_every_word_to_agree():
    candidates = pd.DataFrame(
        [
            {"node_key": "O:1", "name": "Beacon Granite Shipping Limited"},
            {"node_key": "O:2", "name": "BEACON MARBLE SHIPPING LTD"},
            {"node_key": "O:3", "name": "GRANITE BEACON FREIGHT LTD"},
        ]
    )
    hits = screen_entities(SANCTIONS, candidates, CFG)
    assert hits["node_key"].tolist() == ["O:1"]


def test_screening_on_the_registry_finds_most_linked_parties(state):
    metrics = evaluate_screening(state)
    assert metrics["party_recall"] >= 0.8
    assert metrics["alerts"]["match"]["precision"] >= 0.7
    leak = metrics["by_link_kind"].get("leak_officer")
    if leak:
        assert leak["found_as_match"] == 0.0
