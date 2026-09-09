#!/usr/bin/env python3
"""Contract self-tests. Stdlib only; no test framework required.

    python3 tests/contracts/test_contracts.py
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
fails = []

def check(cond, msg):
    print(("  ok | " if cond else "FAIL | ") + msg)
    if not cond:
        fails.append(msg)

print("\nContract schemas")
schemas = sorted((ROOT / "contracts").glob("*.schema.json"))
check(len(schemas) == 8, f"expected 8 contracts, found {len(schemas)}")

for p in schemas:
    d = json.loads(p.read_text())
    check("$id" in d and d["$id"].endswith(".json"), f"{p.name}: has $id")
    check(bool(d.get("required")), f"{p.name}: declares required fields")
    check(d.get("additionalProperties") is False,
          f"{p.name}: rejects unknown properties")
    for r in d.get("required", []):
        check(r in d["properties"], f"{p.name}: required '{r}' is defined")

print("\nUniversal traceability field")
for p in schemas:
    d = json.loads(p.read_text())
    check("brd_requirement_id" in d["properties"],
          f"{p.name}: carries brd_requirement_id (orphan-design check)")

print("\nGrain is mandatory on every semantic model")
sm = json.loads((ROOT / "contracts/semantic-model.v1.schema.json").read_text())
for f in ("grain_statement", "grain_columns", "methodology", "role"):
    check(f in sm["required"], f"semantic-model.v1: '{f}' is required")
check(sm["properties"]["grain_columns"].get("minItems") == 1,
      "semantic-model.v1: grain_columns needs at least one column")

print("\nData product versioning")
dp = json.loads((ROOT / "contracts/data-product.v1.schema.json").read_text())
check("pattern" in dp["properties"]["version"], "data-product.v1: version is semver-shaped")
check("provisional" in dp["properties"]["status"]["enum"],
      "data-product.v1: supports provisional status")

print()
if fails:
    print(f"\033[31m{len(fails)} failure(s)\033[0m"); sys.exit(1)
print("\033[32mall contract tests passed\033[0m")
