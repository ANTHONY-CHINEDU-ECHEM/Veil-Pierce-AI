import pandas as pd

from veilpierce.data.loaders import band_from_natures, export_official_layout, load_official_directory
from veilpierce.data.store import load_registry, save_registry
from veilpierce.data.synth import TABLE_NAMES


def test_ownership_band_is_read_from_the_nature_text():
    assert band_from_natures("ownership of shares 75 to 100 percent") == 0.875
    assert band_from_natures("ownership of shares 25 to 50 percent|voting rights 50 to 75 percent") == 0.625
    assert band_from_natures("significant influence or control") == 0.5
    assert band_from_natures("") == 0.0


def test_public_source_layouts_round_trip(registry, tmp_path):
    export_official_layout(registry, tmp_path)
    assert (tmp_path / "BasicCompanyData.csv").exists()
    loaded = load_official_directory(tmp_path, snapshot=registry.meta["snapshot_date"])
    assert loaded.summary() == registry.summary()
    for column in ("company_number", "company_name", "status", "address_line1", "postcode", "accounts_category", "sic_code"):
        assert (loaded.companies[column].to_numpy() == registry.companies[column].to_numpy()).all(), column
    assert (loaded.companies["incorporation_date"].to_numpy() == registry.companies["incorporation_date"].to_numpy()).all()
    assert (loaded.companies["accounts_overdue"].to_numpy() == registry.companies["accounts_overdue"].to_numpy()).all()
    for column in ("company_number", "kind", "dob_year", "dob_month", "natures_of_control", "registration_number", "country_registered"):
        assert (loaded.pscs[column].to_numpy() == registry.pscs[column].to_numpy()).all(), column
    assert (loaded.pscs["ownership_band"].to_numpy() == registry.pscs["ownership_band"].to_numpy()).all()
    assert (loaded.officers["officer_name"].to_numpy() == registry.officers["officer_name"].to_numpy()).all()
    for column in ("entity_id", "schema", "name", "aliases", "birth_year", "birth_month"):
        assert (loaded.sanctions[column].to_numpy() == registry.sanctions[column].to_numpy()).all(), column
    assert (loaded.offshore_entities["jurisdiction"].to_numpy() == registry.offshore_entities["jurisdiction"].to_numpy()).all()
    assert len(loaded.offshore_edges) == len(registry.offshore_edges)
    assert loaded.truth == {}


def test_parquet_store_round_trip(registry, tmp_path):
    save_registry(registry, tmp_path)
    loaded = load_registry(tmp_path)
    for name in TABLE_NAMES:
        pd.testing.assert_frame_equal(getattr(loaded, name), getattr(registry, name), check_dtype=False)
    assert set(loaded.truth) == set(registry.truth)
    assert loaded.meta["seed"] == registry.meta["seed"]
