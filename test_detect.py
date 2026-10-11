import numpy as np
import pandas as pd

from veilpierce.detect.address_factory import score_addresses
from veilpierce.detect.base import risk_band
from veilpierce.detect.engine import TYPOLOGIES, fuse_scores
from veilpierce.detect.nominee import score_directors
from veilpierce.evaluation.evaluate import evaluate_ablations, evaluate_detection


def test_nominee_score_needs_shell_companies_not_just_volume():
    n_companies = 120
    shell = np.zeros(n_companies)
    shell[:60] = 1.0
    directors = np.ones(n_companies)
    person = np.concatenate([np.zeros(60, dtype=int), np.ones(60, dtype=int)])
    company = np.arange(n_companies)
    table = score_directors(person, company, shell, directors, min_companies=25, n_persons=2)
    assert table["n_companies"].tolist() == [60, 60]
    assert table["nominee_score"].iat[0] >= 0.5
    assert table["nominee_score"].iat[1] < 0.5
    small = score_directors(np.zeros(10, dtype=int), np.arange(10), np.ones(10), np.ones(10), min_companies=25, n_persons=1)
    assert small["nominee_score"].iat[0] == 0.0


def test_address_score_separates_a_factory_from_a_busy_agent():
    factory = np.zeros(200, dtype=int)
    agent = np.ones(200, dtype=int)
    address = np.concatenate([factory, agent])
    shell = np.concatenate([np.ones(170), np.zeros(30), np.zeros(170), np.ones(30)])
    overseas = np.concatenate([np.full(200, 0.8), np.full(200, 0.05)])
    inc_day = np.concatenate([np.full(200, 1000), np.arange(200) * 20])
    table = score_addresses(address, shell, overseas, inc_day, min_companies=60, n_addresses=2)
    assert table["factory_score"].iat[0] >= 0.5 > table["factory_score"].iat[1]
    assert table["burst_share"].iat[0] == 1.0
    assert table["burst_share"].iat[1] < 0.05


def test_fusion_and_bands():
    frame = pd.DataFrame({f"score_{t}": [0.0, 0.0, 0.9] for t in TYPOLOGIES})
    frame.loc[1, "score_circular"] = 0.95
    fused = fuse_scores(frame)
    assert fused[0] == 0.0
    assert 0.85 < fused[1] < 0.95
    assert fused[2] > fused[1]
    assert (fused <= 1.0).all()
    assert [risk_band(v) for v in (0.1, 0.45, 0.7, 0.9)] == ["Low", "Medium", "High", "Critical"]


def test_scores_are_probabilities(state):
    cf = state.detection.companies
    for typology in TYPOLOGIES:
        assert cf[f"score_{typology}"].between(0, 1).all(), typology
    assert cf["risk_rules"].between(0, 1).all()
    assert set(cf["risk_band"]) <= {"Low", "Medium", "High", "Critical"}


def test_detectors_recover_the_planted_typologies(state):
    metrics = evaluate_detection(state)
    for typology, row in metrics["per_typology"].items():
        assert row["recall"] >= 0.75, (typology, row)
        floor = 0.5 if typology == "sanctions" else 0.85
        assert row["precision"] >= floor, (typology, row)
    fused = metrics["comparison"]["Veil Pierce rule fusion"]
    assert fused["average_precision"] > 0.9
    for name in ("Direct name screening only", "Address density rule", "Appointment count rule"):
        assert metrics["comparison"][name]["average_precision"] < fused["average_precision"] - 0.25, name


def test_lookalikes_are_rarely_alerted(state):
    hard = evaluate_detection(state)["hard_negatives"]
    for kind in ("benign_agent", "professional_director", "group_tree", "foreign_parent", "spv_batch", "ordinary background"):
        if kind in hard:
            assert hard[kind]["alert_rate"] < 0.03, (kind, hard[kind])


def test_each_ablation_costs_something(state):
    ablations = evaluate_ablations(state)
    assert ablations["nominee"]["ablated"]["recall"] < ablations["nominee"]["full"]["recall"]
    assert ablations["address_factory"]["ablated"]["recall"] < ablations["address_factory"]["full"]["recall"] - 0.3
    assert ablations["circular"]["ablated"]["recall"] <= ablations["circular"]["full"]["recall"]
    assert ablations["sanctions_direct_only"]["ablated"]["recall"] < ablations["sanctions_direct_only"]["full"]["recall"]
    assert ablations["opaque"]["ablated"]["precision"] < ablations["opaque"]["full"]["precision"]
    assert ablations["phoenix_burst"]["ablated"]["precision"] < ablations["phoenix_burst"]["full"]["precision"]
