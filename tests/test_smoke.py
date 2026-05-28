"""Smoke tests. Run with: pytest -q"""

import json
from pathlib import Path

import pytest

import starter_server as ss


def test_database_present():
    db = Path(__file__).parent.parent / "data" / "admet_library.db"
    assert db.exists(), "Run 'python data/seed_db.py' before tests."


def test_toxicity_aspirin_runs():
    """Aspirin should run cleanly and return a valid ToxicityProfile."""
    r = ss.compute_toxicity_alerts("CC(=O)Oc1ccccc1C(=O)O")
    assert r.compound.canonical_name == "Aspirin"
    assert r.overall_verdict in {"clean", "watch", "concern"}
    assert all(a.confidence in {"rule_based", "heuristic"} for a in r.alerts)


def test_toxicity_haloperidol_fires_herg():
    """Haloperidol should trigger the hERG heuristic."""
    sm = "O=C(CCCN1CCC(O)(c2ccc(Cl)cc2)CC1)c1ccc(F)cc1"
    r = ss.compute_toxicity_alerts(sm)
    categories = [a.category for a in r.alerts]
    assert "hERG_heuristic" in categories


def test_invalid_smiles_raises_clear_error():
    with pytest.raises(ValueError, match="Could not parse"):
        ss.compute_toxicity_alerts("not a smiles string")


def test_reference_resource():
    payload = json.loads(ss.reference_compound("aspirin"))
    assert payload["name"] == "Aspirin"
    assert payload["smiles"]
    assert payload["therapeutic_class"] == "analgesic"


def test_reference_resource_case_insensitive():
    payload = json.loads(ss.reference_compound("ASPIRIN"))
    assert payload["name"] == "Aspirin"


def test_reference_resource_miss_returns_error():
    payload = json.loads(ss.reference_compound("not_a_drug"))
    assert "error" in payload
