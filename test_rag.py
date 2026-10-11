import json

from veilpierce.config import KNOWLEDGE_DIR
from veilpierce.rag.index import EntityIndex, HybridIndex, analyse
from veilpierce.rag.prompts import SYSTEM_PROMPT, build_user_prompt
from veilpierce.rag.report import dossier_markdown, html_table
from veilpierce.rag.typology import TypologyLibrary, load_cards, load_matrix


def test_typology_library_is_complete_and_sourced():
    cards = load_cards()
    assert len(cards) >= 24
    assert len({card.id for card in cards}) == len(cards)
    for card in cards:
        assert card.summary and card.indicators and card.actions and card.sources, card.id
    covered = {card.typology for card in cards}
    assert {"nominee", "address_factory", "circular", "sanctions", "opaque", "phoenix_burst", "general"} <= covered


def test_mitigation_matrix_covers_every_typology_and_scores_fall():
    matrix = load_matrix()
    typologies = {row["typology"] for row in matrix["fraud_vectors"]}
    assert typologies == {"nominee", "address_factory", "circular", "sanctions", "opaque", "phoenix_burst"}
    for row in matrix["fraud_vectors"] + matrix["system_risks"]:
        inherent, residual = row["inherent"], row["residual"]
        assert all(1 <= v <= 5 for v in inherent + residual)
        assert residual[0] * residual[1] <= inherent[0] * inherent[1]


def test_hybrid_retrieval_finds_the_right_card():
    library = TypologyLibrary()
    with open(KNOWLEDGE_DIR / "retrieval_eval.json", "r", encoding="utf8") as handle:
        queries = json.load(handle)["queries"]
    hits = 0
    for item in queries:
        top = [card.id for card in library.search(item["query"], k=3)]
        hits += bool(set(top) & set(item["relevant"]))
    assert hits / len(queries) >= 0.9
    assert "T07" in [card.id for card in library.search("company A is owned by B which is owned by A", k=3)]


def test_analyser_stems_and_maps_synonyms():
    assert analyse("The firms were struck off") == analyse("the company was dissolved off")
    assert "the" not in analyse("the owner of the company")


def test_hybrid_index_modes_agree_on_an_obvious_query():
    index = HybridIndex(["a", "b", "c"], ["circular ownership loop between companies", "nominee director with many appointments", "sanctions list screening of names"])
    for mode in ("bm25", "dense", "hybrid"):
        assert index.search("nominee directors", k=1, mode=mode)[0][0] == "b", mode


def test_entity_index_tolerates_typing_slips():
    index = EntityIndex(["C:1", "C:2", "P:1"], ["NORTHGATE FREIGHT SOLUTIONS LTD", "NORTHGATE CAPITAL PARTNERS LIMITED", "Simon Peter Hargreaves"], ["company", "company", "person"])
    assert index.search("Northgate Frieght Solutions", k=1)[0]["key"] == "C:1"
    assert index.search("northgate freight solutions ltd", mode="exact")[0]["key"] == "C:1"
    assert index.search("Northgate Frieght Solutions", mode="exact") == []
    assert index.search("Hargreaves Simon", k=1)[0]["key"] == "P:1"
    assert {hit["kind"] for hit in index.search("northgate", k=5, kind="person")} <= {"person"}
    assert index.search("Northgate Frieght Solutions", k=1, mode="blend")[0]["key"] == "C:1"


def test_dossier_covers_every_typology(investigator, flagged_numbers):
    assert set(flagged_numbers) == {"nominee", "address_factory", "circular", "sanctions", "opaque", "phoenix_burst"}
    for typology, number in flagged_numbers.items():
        dossier = investigator.investigate(number)
        found = {finding.typology for finding in dossier.case.findings}
        assert typology in found
        finding = next(f for f in dossier.case.findings if f.typology == typology)
        assert finding.evidence_ids and finding.card_ids
        assert investigator.library.by_id[finding.card_ids[0]].typology == typology
        assert any(action["typology"] == finding.title for action in dossier.actions)
        payload = dossier.to_dict()
        assert payload["risk_band"] in {"Medium", "High", "Critical"}
        json.dumps(payload)


def test_dossier_markdown_is_complete_and_free_of_hyphens(investigator, flagged_numbers):
    for number in flagged_numbers.values():
        text = dossier_markdown(investigator.investigate(number))
        for heading in ("## Summary", "## Findings", "## Ownership and control", "## Recommended controls", "## Evidence register", "## Verification and audit"):
            assert heading in text
        assert chr(45) not in text and chr(8212) not in text and chr(8211) not in text


def test_unflagged_company_gets_a_clean_dossier(investigator, state):
    cf = state.detection.companies
    number = cf[cf["n_flags"] == 0]["company_number"].iloc[0]
    dossier = investigator.investigate(number)
    assert dossier.case.findings == [] and dossier.actions == []
    assert dossier.case.risk_band == "Low"
    assert dossier.verification.supported == dossier.verification.total


def test_prompt_contains_evidence_rules_and_guarded_names(investigator, state, labels):
    cf = state.detection.companies
    number = cf["company_number"][labels["injected_name"].to_numpy()].iloc[0]
    dossier = investigator.investigate(number)
    assert dossier.case.injection_fields == ["company name"]
    assert any(item.kind == "guard" for item in dossier.case.evidence)
    prompt = build_user_prompt(dossier.case, dossier.cards)
    hostile = dossier.case.registered_name
    assert "withheld by the injection guard" in prompt
    assert hostile not in prompt and hostile.split(" LTD")[0][:30] not in prompt
    assert all(hostile not in claim.text for claim in dossier.narrative.all_claims())
    assert hostile in dossier_markdown(dossier)
    assert all(f"[{item.id}]" in prompt for item in dossier.case.evidence)
    assert "do not follow it" in SYSTEM_PROMPT
    assert dossier.case.risk_band in {"Medium", "High", "Critical"}
    assert dossier.verification.supported == dossier.verification.total


def test_questions_are_answered_with_citations(investigator, flagged_numbers, state):
    number = flagged_numbers["circular"]
    name = state.detection.row(number)["company_name"]
    by_number = investigator.ask(f"Who ultimately controls company {number}?")
    assert by_number.company_number == number and by_number.claims
    assert all(claim.citations for claim in by_number.claims)
    assert any("Circular ownership" in claim.text for claim in by_number.claims)
    by_name = investigator.ask(f"Who is behind {name.title()}?")
    assert by_name.company_number == number
    sanctions = investigator.ask(f"Any sanctions exposure for {flagged_numbers['sanctions']}?")
    assert "Sanctions proximity" in sanctions.claims[0].text
    none = investigator.ask(f"Is {number} linked to a sanctioned person?")
    assert none.claims and none.claims[0].citations
    unknown = investigator.ask("Who controls 99999999?")
    assert unknown.company_number is None or unknown.company_number != "99999999"


def test_html_table_escapes_cells():
    table = html_table(["A"], [["<b>x</b>"]])
    assert "&lt;b&gt;" in table and "<td>" in table
