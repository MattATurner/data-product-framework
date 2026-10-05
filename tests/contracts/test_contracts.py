"""Contract registry tests: every contract is well-formed, and the cross-cutting rules hold."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = sorted((ROOT / "contracts").glob("*.schema.json"))
# Contracts that describe design elements must carry the universal traceability field.
TRACEABLE = ["catalog-registration.v1", "data-product.v1", "landing-manifest.v1", "quality-policy.v1",
             "raw-table.v1", "semantic-model.v1", "source-binding.v1", "staging-model.v1"]


def load(name: str) -> dict:
    return json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8"))


def test_registry_is_complete():
    names = {p.name.removesuffix(".schema.json") for p in SCHEMAS}
    for required in ["brd.v1", "product-manifest.v1", "acceptance.v1", "signoff.v1", "test-spec.v1",
                     "test-evidence.v1", "trace-matrix.v1", "observability-policy.v1", "run-evidence.v1",
                     "skill.v1", "methodology-pack.v1", "engine-adapter.v1", "rule.v1", "common.v1", *TRACEABLE]:
        assert required in names, f"missing contract {required}"


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_contract_is_valid_json_schema(path):
    from jsonschema import Draft202012Validator
    d = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(d)
    assert d["$id"].endswith(path.name.replace(".schema.json", ".json"))
    if path.name != "common.v1.schema.json":
        assert d.get("required"), "declares required fields"
        for r in d.get("required", []):
            assert r in d.get("properties", {}), f"required '{r}' is defined"


@pytest.mark.parametrize("name", TRACEABLE)
def test_traceable_contracts_carry_requirement_ids(name):
    assert "brd_requirement_id" in load(name)["properties"]


def test_grain_is_mandatory_on_semantic_models():
    sm = load("semantic-model.v1")
    for f in ("grain_statement", "grain_columns", "methodology", "role"):
        assert f in sm["required"]
    assert sm["properties"]["grain_columns"].get("minItems") == 1


def test_data_product_versioning():
    dp = load("data-product.v1")
    version = dp["properties"]["version"]
    if "$ref" in version:  # shared definition in common.v1
        assert version["$ref"].endswith("common.v1.json#/$defs/semver")
        version = load("common.v1")["$defs"]["semver"]
    assert "pattern" in version
    assert "provisional" in dp["properties"]["status"]["enum"]


def test_evidence_binds_to_a_build_digest():
    te = load("test-evidence.v1")
    assert "artefact_digest" in te["required"]
    assert te["properties"]["artefact_digest"]["pattern"] == "^sha256:[0-9a-f]{64}$"


def test_landing_manifest_records_quarantine():
    lm = json.dumps(load("landing-manifest.v1"))
    assert "quarantined" in lm
