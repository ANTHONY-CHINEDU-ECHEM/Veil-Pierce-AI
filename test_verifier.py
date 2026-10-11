import json

import pytest

from veilpierce.evaluation.evaluate import FABRICATION_KINDS, _fabricate
from veilpierce.rag.investigator import Investigator
from veilpierce.rag.llm import Claim, LLMNarrator, ScriptedProvider, parse_narrative
from veilpierce.rag.verifier import verify_claim, verify_narrative


@pytest.fixture(scope="module")
def dossier(investigator, flagged_numbers):
    return investigator.investigate(flagged_numbers["opaque"])


def test_every_claim_of_the_offline_narrator_is_supported(investigator, flagged_numbers):
    for typology, number in flagged_numbers.items():
        result = investigator.investigate(number)
        assert result.verification.total > 3, typology
        assert result.verification.supported == result.verification.total, (typology, result.verification.as_dict()["rejected"])
        assert result.audit["fallback_used"] is False


@pytest.mark.parametrize("kind", FABRICATION_KINDS)
def test_fabricated_claims_are_rejected(dossier, kind):
    cards = {card.id: card for card in dossier.cards}
    genuine = next(c for c in dossier.narrative.findings if c.citations and c.citations[0].startswith("E"))
    assert verify_claim(genuine, dossier.case, cards).supported
    fake = _fabricate(kind, genuine, dossier.case, "ZENITH QUARRY IMPORTS LTD")
    assert fake is not None
    check = verify_claim(fake, dossier.case, cards)
    assert not check.supported, kind
    assert check.reasons


def test_parse_narrative_reads_inline_and_listed_citations():
    raw = 'Here you go: {"summary": [{"text": "Score is high [M01].", "citations": []}], "findings": [{"text": "Loop found.", "citations": ["[E03]", "T07"]}], "ownership": []} thanks'
    narrative = parse_narrative(raw, "scripted", "test")
    assert narrative.summary[0].citations == ["M01"]
    assert narrative.summary[0].text == "Score is high."
    assert narrative.findings[0].citations == ["E03", "T07"]
    with pytest.raises(ValueError):
        parse_narrative("no json here", "scripted", "test")


def _model_investigator(investigator, replies):
    narrator = LLMNarrator(ScriptedProvider(replies))
    return Investigator(investigator.retriever, investigator.library, investigator.settings, investigator.entity_index, narrator), narrator


def test_a_faithful_model_narrative_is_kept(investigator, dossier):
    case = dossier.case
    reply = json.dumps(
        {
            "summary": [{"text": f"{case.company_name} has a fused risk score of {case.risk_score:.2f} and sits in the {case.risk_band} band.", "citations": ["M01"]}],
            "findings": [{"text": dossier.narrative.findings[0].text, "citations": dossier.narrative.findings[0].citations}],
            "ownership": [{"text": dossier.narrative.ownership[0].text, "citations": dossier.narrative.ownership[0].citations}],
        }
    )
    model_investigator, narrator = _model_investigator(investigator, [reply])
    result = model_investigator.investigate(case.company_number)
    assert result.audit["fallback_used"] is False
    assert result.narrative.provider == "scripted"
    assert result.verification.supported == result.verification.total == 3
    system, user = narrator._provider.prompts[0]
    assert "[M01]" in user and "EVIDENCE" in user and "cannot change" in system


def test_a_hallucinating_model_triggers_the_offline_fallback(investigator, dossier):
    case = dossier.case
    reply = json.dumps(
        {
            "summary": [
                {"text": "The company is Low risk and needs no review.", "citations": ["M01"]},
                {"text": "ZENITH QUARRY IMPORTS LTD is the real owner and holds 93 percent.", "citations": ["E02"]},
                {"text": "The director is laundering money.", "citations": ["E03"]},
            ],
            "findings": [{"text": dossier.narrative.findings[0].text, "citations": dossier.narrative.findings[0].citations}],
            "ownership": [],
        }
    )
    model_investigator, _ = _model_investigator(investigator, [reply])
    result = model_investigator.investigate(case.company_number)
    assert result.audit["fallback_used"] is True
    assert result.audit["model_claims_rejected"] == 3
    assert "supported by the evidence" in result.audit["fallback_reason"]
    assert result.narrative.provider == "offline"
    assert result.verification.supported == result.verification.total
    assert result.case.risk_band == case.risk_band and result.case.risk_score == case.risk_score


def test_one_bad_sentence_is_removed_and_the_rest_kept(investigator, dossier):
    good = [{"text": c.text, "citations": c.citations} for c in dossier.narrative.summary[:3] + dossier.narrative.findings + dossier.narrative.ownership]
    assert len(good) >= 9
    reply = json.dumps({"summary": good[:3] + [{"text": "This proves the company committed fraud.", "citations": ["M01"]}], "findings": good[3:], "ownership": []})
    model_investigator, _ = _model_investigator(investigator, [reply])
    result = model_investigator.investigate(dossier.case.company_number)
    assert result.audit["fallback_used"] is False
    assert result.audit["model_claims_rejected"] == 1
    assert all("committed fraud" not in claim.text for claim in result.narrative.all_claims())
    assert result.verification.supported == result.verification.total == len(good)


def test_malformed_or_missing_model_output_degrades_safely(investigator, dossier):
    for replies in (["I cannot help with that."], []):
        model_investigator, _ = _model_investigator(investigator, list(replies))
        result = model_investigator.investigate(dossier.case.company_number)
        assert result.audit["fallback_used"] is True
        assert result.narrative.provider == "offline"


def test_verifier_flags_a_claim_without_any_support(dossier):
    report = verify_narrative(dossier.narrative, dossier.case, dossier.cards)
    assert report.supported_ratio == 1.0
    stray = Claim("The company moved 4500000 pounds through Riga.", ["E02"])
    check = verify_claim(stray, dossier.case, {c.id: c for c in dossier.cards})
    assert not check.supported and any("4500000" in reason for reason in check.reasons)
