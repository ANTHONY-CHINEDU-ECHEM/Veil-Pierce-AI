import pytest
from fastapi.testclient import TestClient

from veilpierce.api.app import create_app
from veilpierce.cli import _split
from veilpierce.config import load_settings
from veilpierce.pipeline import Runtime, load_runtime, save_artifacts


@pytest.fixture(scope="module")
def client(state, investigator, entity_index, settings):
    runtime = Runtime(settings, state.graph, state.detection, investigator, entity_index, {"dataset": {"total_records": 1}, "detection": {"pr_curves": {}, "alert_threshold": 0.5}})
    return TestClient(create_app(runtime))


def test_health_and_reference_endpoints(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["companies"] > 0 and "offline" in health["narrator"]
    assert len(client.get("/typologies").json()["cards"]) >= 24
    assert len(client.get("/mitigations").json()["fraud_vectors"]) == 6
    metrics = client.get("/metrics").json()
    assert "pr_curves" not in metrics["detection"]


def test_risk_and_dossier_endpoints(client, flagged_numbers):
    number = flagged_numbers["sanctions"]
    risk = client.get(f"/companies/{number}/risk").json()
    assert risk["company_number"] == number and "Sanctions proximity" in risk["typologies_triggered"]
    dossier = client.get(f"/companies/{number}/dossier").json()
    assert dossier["risk_band"] == risk["risk_band"]
    assert dossier["verification"]["supported"] == dossier["verification"]["claims"]
    assert all(item["citations"] for item in dossier["summary"] + dossier["findings"])
    markdown = client.get(f"/companies/{number}/dossier", params={"format": "markdown"}).json()["markdown"]
    assert markdown.startswith("# Due diligence dossier")
    graph = client.get(f"/companies/{number}/graph").json()
    assert graph["edges"] and {"source", "target", "type"} <= set(graph["edges"][0])


def test_search_top_and_ask(client, flagged_numbers, state):
    number = flagged_numbers["nominee"]
    name = state.detection.row(number)["company_name"]
    results = client.get("/entities/search", params={"q": name, "k": 3}).json()["results"]
    assert results[0]["key"] == f"C:{number}"
    top = client.get("/companies/top", params={"limit": 5, "typology": "circular"}).json()["results"]
    assert len(top) == 5 and top[0]["risk_score"] >= top[4]["risk_score"]
    answer = client.post("/ask", json={"question": f"Who are the directors of {number}?"}).json()
    assert answer["company_number"] == number and answer["answer"]


def test_errors_are_reported_cleanly(client):
    assert client.get("/companies/00000000/risk").status_code == 404
    assert client.get("/companies/00000000/dossier").status_code == 404
    assert client.get("/companies/top", params={"typology": "unknown"}).status_code == 422
    assert client.post("/ask", json={"question": "x"}).status_code == 422
    assert client.get("/entities/search", params={"q": "a"}).status_code == 422


def test_artefacts_round_trip_without_truth(state, entity_index, tmp_path, flagged_numbers):
    state.settings.artifact_dir = str(tmp_path / "artifacts")
    try:
        root = save_artifacts(state, entity_index, {"dataset": {"total_records": 5}})
        names = {p.name for p in root.iterdir()}
        assert {"graph.joblib", "detection.joblib", "tables.joblib", "entity_index.joblib", "metrics.json"} <= names
        runtime = load_runtime(state.settings)
    finally:
        state.settings.artifact_dir = "artifacts"
    assert runtime.graph.describe() == state.graph.describe()
    number = flagged_numbers["opaque"]
    assert runtime.investigator.investigate(number).case.risk_score == state.detection.row(number)["risk_rules"].round(2)
    assert runtime.metrics["dataset"]["total_records"] == 5


def test_command_line_argument_splitting():
    positional, overrides, options = _split(["09123456", "synth.n_companies=5000", "data_dir=tmp/data", "port=9000", "Who controls NORTHGATE LTD?"])
    assert positional == ["09123456", "Who controls NORTHGATE LTD?"]
    assert overrides == ["synth.n_companies=5000", "data_dir=tmp/data"]
    assert options == {"port": "9000"}
    settings = load_settings(overrides=overrides)
    assert settings.synth.n_companies == 5000 and settings.data_dir == "tmp/data"
    with pytest.raises(KeyError):
        load_settings(overrides=["synth.unknown=1"])
