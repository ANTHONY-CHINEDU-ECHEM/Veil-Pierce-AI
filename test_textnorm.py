from veilpierce.textnorm import (
    address_key,
    canonical_jurisdiction,
    company_core,
    norm_company_name,
    norm_postcode,
    norm_text,
    parse_person_name,
    translit_key,
)


def test_norm_text_strips_accents_and_punctuation():
    assert norm_text("  José   O'Neil & Sons, Ltd. ") == "JOSE O NEIL AND SONS LTD"
    assert norm_text(None) == ""


def test_company_names_agree_across_legal_form_spellings():
    assert norm_company_name("Blue Harbour Holdings Limited") == norm_company_name("BLUE HARBOUR HOLDINGS LTD.")
    assert company_core("The Blue Harbour Holdings L.P.") == "BLUE HARBOUR HOLDINGS"
    assert company_core("Blue Harbour Holdings") == company_core("Blue Harbour Holdings (UK) Ltd")


def test_person_names_parse_from_both_register_layouts():
    assert parse_person_name("HARGREAVES, Simon Peter") == ("HARGREAVES", "SIMON", "PETER")
    assert parse_person_name("Mr Simon P Hargreaves") == ("HARGREAVES", "SIMON", "P")
    assert parse_person_name("Dr Ana de Souza") == ("DE SOUZA", "ANA", "")
    assert parse_person_name("") == ("", "", "")


def test_translit_key_joins_common_romanisations():
    assert translit_key("Mohammed") == translit_key("Muhammad") == translit_key("Mohamed")
    assert translit_key("Alexei") == translit_key("Aleksey")
    assert translit_key("Yusuf") == translit_key("Youssef")
    assert translit_key("Smith") != translit_key("Jones")


def test_address_key_ignores_units_floors_and_abbreviations():
    base = address_key("71 Example Street", "M1 4BT")
    variants = ["Suite 12, 71 Example St", "Office 4 71 Example Street", "71 Example Street, Floor 2", "Unit 4B, 71 Example St.", "2nd Floor, 71 Example Street"]
    assert all(address_key(v, "m14bt") == base for v in variants)
    assert address_key("72 Example Street", "M1 4BT") != base
    assert address_key("71 Example Street", "M1 4BX") != base


def test_postcode_and_jurisdiction_normalisation():
    assert norm_postcode("m1 4bt") == "M14BT"
    aliases = {"BVI": "BRITISH VIRGIN ISLANDS", "VIRGIN ISLANDS BRITISH": "BRITISH VIRGIN ISLANDS"}
    assert canonical_jurisdiction("B.V.I.", {"B V I": "BRITISH VIRGIN ISLANDS"}) == "BRITISH VIRGIN ISLANDS"
    assert canonical_jurisdiction("Virgin Islands, British", aliases) == "BRITISH VIRGIN ISLANDS"
    assert canonical_jurisdiction("Germany", aliases) == "GERMANY"
