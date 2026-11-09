"""Unit tests for the dpf package: spec parsing, render helpers, monitor, trace, lint and CLI exit codes.

The example products are the fixtures: they must pass every gate up to G3 and fail G4 honestly.
customer_orders has no deployed-run evidence; sales_performance has sandbox evidence but no
business attestations yet.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from dpf.cli import main
from dpf.core import Report, Workspace
from dpf.generate import build
from dpf.generate.render import dts_schedule, duration_minutes, marker, parse_markers
from dpf.lint import lint_terms
from dpf.monitor import evaluate, in_calendar, monitor, open_change, parse_ts
from dpf.specs import parse_meta, parse_spec
from dpf.trace import check_trace, trace_matrix
from dpf.validate import validate

ROOT = Path(__file__).resolve().parents[2]
PERTH_WEEKDAYS = {"days": ["MON", "TUE", "WED", "THU", "FRI"], "start": "08:00", "end": "18:00",
                  "timezone": "Australia/Perth"}


@pytest.fixture(scope="module")
def ws() -> Workspace:
    return Workspace(ROOT)


@pytest.fixture(scope="module")
def sales(ws):
    return ws.product("sales_performance")


def quiet() -> Report:
    return Report(quiet=True, stream=io.StringIO())


# ----------------------------------------------------------------- spec parsing
def test_parse_meta_reads_ids_from_metadata_lines():
    meta = parse_meta("**Decision:** D-3 · **Satisfies:** R-2, R-3 · **Model:** fct_order_line")
    assert meta == {"decision": "D-3", "satisfies": "R-2, R-3", "model": "fct_order_line"}


def test_parse_spec_requirements_and_scenarios():
    spec = parse_spec("""# Example

## Purpose
Say what the product is for.

## Requirements

### Requirement: Order line grain
**ID:** R-2 · **Priority:** must

The product SHALL hold one row per order line.

#### Scenario: Two lines on one order
**ID:** AX-2
- **GIVEN** an order with two lines
- **WHEN** the product is refreshed
- **THEN** two rows are present
""")
    assert spec.has_purpose and spec.has_requirements
    (req,) = spec.requirements
    assert req.name == "Order line grain" and req.meta["id"] == "R-2" and req.normative
    (sc,) = req.scenarios
    assert sc.meta["id"] == "AX-2" and sc.keywords == {"GIVEN", "WHEN", "THEN"}


# ----------------------------------------------------------------- render helpers
@pytest.mark.parametrize("iso,minutes", [("PT15M", 15), ("PT1H30M", 90), ("P1D", 1440), ("P32D", 46080),
                                         ("P1DT2H", 1560), ("PT30S", 1)])
def test_duration_minutes(iso, minutes):
    assert duration_minutes(iso) == minutes


@pytest.mark.parametrize("bad", ["", "1H", "P1W", "PT1.5H"])
def test_duration_minutes_rejects_other_formats(bad):
    with pytest.raises(ValueError):
        duration_minutes(bad)


@pytest.mark.parametrize("iso,text", [("PT15M", "every 15 minutes"), ("PT5M", "every 15 minutes"),
                                      ("PT90M", "every 90 minutes"), ("PT1H", "every 1 hours"),
                                      ("P1D", "every 24 hours")])
def test_dts_schedule(iso, text):
    assert dts_schedule(iso) == text


def test_marker_round_trip():
    line = marker({"model": "fct_order_line", "satisfies": ["R-1", "R-11"], "skill": "model-transaction-fact",
                   "empty": None, "title": "two words"})
    assert line == "-- dpf: model=fct_order_line satisfies=R-1,R-11 skill=model-transaction-fact title=two_words"
    text = f"{line}\nselect 1\n# dpf: skill=extract-rdbms-watermark tier=5 adr=ADR-015\n"
    assert parse_markers(text) == [
        {"model": "fct_order_line", "satisfies": "R-1,R-11", "skill": "model-transaction-fact", "title": "two_words"},
        {"skill": "extract-rdbms-watermark", "tier": "5", "adr": "ADR-015"},
    ]


# ----------------------------------------------------------------- monitor
def run_evidence(observed_at: str, monthly_built: str, rows: int | None = 40000, **extra) -> dict:
    fct = {"name": "fct_order_line", "last_built_at": monthly_built}
    if rows is not None:
        fct["rows_in_window"] = rows
    return {"product_id": "sales_performance", "observed_at": observed_at, "run_id": "unit-test",
            "models": [{"name": "sales_performance_monthly", "last_built_at": monthly_built},
                       {"name": "sales_performance_partner_extract", "last_built_at": "2026-10-01T19:00:00Z"},
                       fct], **extra}


def test_in_calendar_uses_the_business_timezone():
    assert in_calendar(parse_ts("2026-10-07T03:00:00Z"), PERTH_WEEKDAYS)      # Wed 11:00 Perth
    assert not in_calendar(parse_ts("2026-10-06T23:30:00Z"), PERTH_WEEKDAYS)  # Wed 07:30 Perth
    assert not in_calendar(parse_ts("2026-10-07T11:00:00Z"), PERTH_WEEKDAYS)  # Wed 19:00 Perth
    assert not in_calendar(parse_ts("2026-10-10T03:00:00Z"), PERTH_WEEKDAYS)  # Saturday
    assert in_calendar(parse_ts("2026-10-10T03:00:00Z"), None)                 # no calendar: always


@pytest.mark.parametrize("text, micros", [
    ("2026-10-07T03:00:00.5Z", 500000),
    ("2026-10-07T03:00:00.123Z", 123000),
    ("2026-10-07T03:00:00.12345+00:00", 123450),
    ("2026-10-07T03:00:00.123456789Z", 123456),   # nanoseconds cut to microseconds
    ("2026-10-07T11:00:00.25+08:00", 250000),
])
def test_parse_ts_accepts_any_rfc3339_fraction(text, micros):
    from datetime import datetime, timezone
    dt = parse_ts(text)
    assert dt.microsecond == micros
    assert dt.astimezone(timezone.utc).replace(microsecond=0) == datetime(2026, 10, 7, 3, tzinfo=timezone.utc)


def test_sales_policy_matches_the_calendar_under_test(sales):
    ob1 = next(o for o in sales.manifest["observability"]["freshness"] if o["id"] == "OB-1")
    assert ob1["calendar"] == PERTH_WEEKDAYS and ob1["max_staleness"] == "PT1H30M"


def test_freshness_breach_in_business_hours(sales):
    breaches, _ = evaluate(sales, run_evidence("2026-10-07T03:00:00Z", "2026-10-07T00:30:00Z"))
    assert [(b.kind, b.policy, b.requirements) for b in breaches] == [("freshness", "OB-1", ["R-10"])]
    assert breaches[0].summary == "sales_performance_monthly is 150 minutes old (limit 90)"


def test_freshness_is_not_evaluated_outside_the_calendar(sales):
    breaches, notes = evaluate(sales, run_evidence("2026-10-10T03:00:00Z", "2026-10-09T10:00:00Z"))
    assert breaches == []
    assert any(n.startswith("OB-1:") and "outside the business calendar" in n for n in notes)


def test_fresh_model_passes_with_a_note(sales):
    breaches, notes = evaluate(sales, run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z"))
    assert breaches == []
    assert "OB-1: sales_performance_monthly is 60 minutes old (limit 90)" in notes


def test_unobserved_model_is_a_breach(sales):
    ev = run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z")
    ev["models"] = [m for m in ev["models"] if m["name"] != "sales_performance_monthly"]
    breaches, _ = evaluate(sales, ev)
    assert [(b.kind, b.policy, b.observed) for b in breaches] == [("freshness", "OB-1", "not observed")]


@pytest.mark.parametrize("rows,breach", [(40000, False), (16000, False), (64000, False), (15000, True),
                                         (65000, True), (0, True)])
def test_volume_band_is_expected_rows_plus_or_minus_tolerance(sales, rows, breach):
    breaches, _ = evaluate(sales, run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z", rows=rows))
    assert [b.policy for b in breaches] == (["OB-3"] if breach else [])


def test_missing_row_count_is_noted_not_failed(sales):
    breaches, notes = evaluate(sales, run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z", rows=None))
    assert breaches == []
    assert any(n.startswith("OB-3:") and "not evaluated" in n for n in notes)


def test_failed_checks_and_breaking_drift_are_breaches(sales):
    ev = run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z",
                      checks=[{"id": "fct_order_line_reject_gate", "status": "failed", "detail": "3 rejected rows"},
                              {"id": "fct_order_line_grain", "status": "passed"}],
                      drift_events=[{"entity": "orders", "classification": "breaking",
                                     "changes": ["column STATUS removed"], "batch_id": "b-1"},
                                    {"entity": "customers", "classification": "additive",
                                     "changes": ["column EMAIL added"]}])
    breaches, notes = evaluate(sales, ev)
    assert [(b.kind, b.policy) for b in breaches] == [("check", "fct_order_line_reject_gate"), ("schema-drift", "orders")]
    assert breaches[0].summary == "check fct_order_line_reject_gate failed: 3 rejected rows"
    assert "batch b-1 quarantined, watermark held" in breaches[1].summary
    assert any("additive" in n and "land_and_record" in n for n in notes)


def test_monitor_validates_the_evidence_document(sales):
    r = quiet()
    bad = {"product_id": "sales_performance", "observed_at": "2026-10-07T03:00:00Z", "models": [{"name": "x"}]}
    assert monitor(sales, r, bad) == 1
    assert "does not conform to run-evidence.v1" in r.messages("fail")[0]
    r = quiet()
    other = dict(run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z"), product_id="customer_orders")
    assert monitor(sales, r, other) == 1
    assert r.messages("fail") == ["evidence is for customer_orders, not sales_performance"]


def test_monitor_passes_clean_evidence(sales):
    r = quiet()
    assert monitor(sales, r, run_evidence("2026-10-07T03:00:00Z", "2026-10-07T02:00:00Z")) == 0
    assert r.failures == 0


def test_open_change_writes_an_openspec_change(sales, tmp_path):
    ev = run_evidence("2026-10-07T03:00:00Z", "2026-10-07T00:30:00Z")
    breaches, _ = evaluate(sales, ev)
    # A stand-in product whose workspace root is the temporary directory.
    stub = SimpleNamespace(id=sales.id, manifest=sales.manifest, brd=sales.brd, ws=SimpleNamespace(root=tmp_path))
    d = open_change(stub, ev, breaches)
    assert d == tmp_path / "openspec/changes/monitor-sales-performance-freshness-20261007-0300"
    assert {f.name for f in d.iterdir()} == {".openspec.yaml", "proposal.md", "design.md", "verification.md",
                                            "operations.md", "tasks.md"}
    meta = yaml.safe_load((d / ".openspec.yaml").read_text(encoding="utf-8"))
    assert meta["schema"] == "data-product" and meta["skip_specs"] is True
    proposal = (d / "proposal.md").read_text(encoding="utf-8")
    assert "examples/sales_performance/RUNBOOK.md#freshness-or-volume-breach" in proposal
    assert "requirements at risk: R-10" in proposal


# ----------------------------------------------------------------- build and trace
def test_build_is_deterministic(sales):
    a, b = build(sales), build(sales)
    assert a.ok and a.digest == b.digest and a.files == b.files


def test_every_requirement_traces_to_a_decision_an_artefact_and_a_test(sales):
    m = trace_matrix(sales)
    assert [r["requirement"] for r in m["rows"]] == [r.meta["id"] for r in sales.brd_spec.requirements]
    for row in m["rows"]:
        assert row["decisions"] and row["artefacts"] and row["tests"], row["requirement"]
    assert m["artefact_digest"].startswith("sha256:")


def test_trace_check_passes_for_every_product(ws):
    for pid in ws.product_ids():
        r = quiet()
        check_trace(ws.product(pid), r, write=False)
        assert r.failures == 0, r.messages("fail")


# ----------------------------------------------------------------- validate and lint
def test_framework_documents_validate(ws):
    r = quiet()
    validate(ws, r)
    assert r.failures == 0, r.messages("fail")


def test_lint_terms_flags_retired_names_in_prose_only(tmp_path):
    (tmp_path / "README.md").write_text(
        "Register the tables in Dataplex.\n"                                        # 1: prose -> fail
        "Use `google_dataplex_datascan` and https://dataplex.googleapis.com/v1.\n"  # 2: identifiers -> fine
        "```hcl\n"
        "# Dataplex in a code block is fine\n"                                      # 4: code -> fine
        "```\n"
        "Share the views with Analytics Hub.\n", encoding="utf-8")                  # 6: prose -> fail
    (tmp_path / "openspec").mkdir()
    (tmp_path / "openspec/project.md").write_text(
        "| BigQuery sharing | formerly Analytics Hub |\n"   # naming table may list former names ...
        "| Knowledge Catalog | formerly Dataplex |\n",      # ... except the catalog's
        encoding="utf-8")
    r = quiet()
    lint_terms(Workspace(tmp_path), r)
    (msg,) = r.messages("fail")
    assert "README.md:1 'Dataplex' (say Knowledge Catalog)" in msg
    assert "README.md:6 'Analytics Hub' (say BigQuery sharing)" in msg
    assert "openspec/project.md:2 'Dataplex'" in msg
    for clean in ("README.md:2", "README.md:4", "openspec/project.md:1"):
        assert clean not in msg


# ----------------------------------------------------------------- CLI
def test_cli_gate_exit_codes(capsys):
    assert main(["check", "--all", "--gate", "describe", "--quiet", "--root", str(ROOT)]) == 0
    assert main(["check", "--all", "--gate", "define", "--quiet", "--root", str(ROOT)]) == 0
    assert main(["check", "--all", "--gate", "G3", "--quiet", "--root", str(ROOT)]) == 0
    assert main(["check", "--all", "--gate", "build", "--quiet", "--root", str(ROOT)]) == 0
    capsys.readouterr()
    # customer_orders has no deployed-run evidence, so G4 must fail rather than pass on nothing.
    assert main(["check", "customer_orders", "--gate", "G4", "--quiet", "--root", str(ROOT)]) == 1
    assert "no evidence for build sha256:" in capsys.readouterr().out
    assert main(["check", "customer_orders", "--gate", "accept", "--quiet", "--root", str(ROOT)]) == 1
    assert main(["check", "customer_orders", "--gate", "test", "--quiet", "--root", str(ROOT)]) == 1
    capsys.readouterr()


def test_signoff_and_attest_support_attached_links(ws, sales):
    so = dict(sales.signoff, links=["https://confluence.example.com/display/SALES/Signoff",
                                    "mailto:approvals@example.com"])
    assert ws.validate(so, "signoff.v1") == []
    ev = {
        "product_id": "sales_performance",
        "artefact_digest": "sha256:" + "a" * 64,
        "run_id": "attest-AT-5-20261005T230940Z",
        "environment": "test",
        "recorded_at": "2026-10-05T23:09:40Z",
        "results": [{
            "test_id": "acceptance:AT-5",
            "status": "passed",
            "attested_by": "Jane Doe (finance)",
            "note": "Reconciled to GL",
            "links": ["https://confluence.example.com/display/FIN/GL-Rec"],
            "finished_at": "2026-10-05T23:09:40Z",
        }],
    }
    assert ws.validate(ev, "test-evidence.v1") == []


def test_deferred_requirement_passes_g0_and_is_excluded_from_g1(tmp_path):
    import shutil
    from dpf.brd import check_brd
    from dpf.design import check_design
    from dpf.evals import COPY, IGNORE

    for rel in COPY:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, tmp_path / rel, ignore=IGNORE)
    spec_file = tmp_path / "openspec/specs/products/sales/customer-orders/brd/spec.md"
    spec_file.write_text(
        spec_file.read_text(encoding="utf-8").replace(
            "## Scope",
            "### Requirement: Future loyalty tier breakdown\n"
            "**ID:** R-99 · **Status:** deferred\n\n"
            "Users SHALL be able to filter order totals by loyalty tier in phase 2.\n\n"
            "#### Scenario: Loyalty filter\n"
            "**ID:** AX-99\n"
            "- **GIVEN** orders for customers in two loyalty tiers\n"
            "- **WHEN** a user filters by loyalty tier\n"
            "- **THEN** they see the order total for that tier\n\n"
            "## Scope",
        ),
        encoding="utf-8",
    )
    twin_ws = Workspace(tmp_path)
    p = twin_ws.product("customer_orders")
    assert "R-99" not in p.requirement_ids
    assert p.deferred_requirement_ids == ["R-99"]
    assert "AX-99" not in p.scenario_ids
    r0 = quiet()
    check_brd(p, r0, write_gaps=False)
    assert r0.failures == 0, r0.messages("fail")
    r1 = quiet()
    check_design(p, r1)
    assert r1.failures == 0, r1.messages("fail")


def test_g4_stale_evidence_fails_even_for_a_warn_level_case(sales, monkeypatch):
    # A result for another build does not count. A warn-level case that has not run against
    # this build is missing evidence, not a warning; only a run that failed on it is a warning.
    import dpf.testing as testing

    b = build(sales)
    case = next(c for c in b.spec["cases"] if c["severity"] == "warn" and c["method"] == "automated")
    old = {"product_id": sales.id, "artefact_digest": "sha256:" + "0" * 64, "run_id": "run-20260901T000000Z",
           "environment": "test", "recorded_at": "2026-09-01T00:00:00Z", "_file": "run-20260901T000000Z.json",
           "results": [{"test_id": case["id"], "status": "passed", "failing_rows": 0,
                        "finished_at": "2026-09-01T00:00:00Z"}]}
    monkeypatch.setattr(testing, "load_evidence", lambda p: [old])
    r = quiet()
    testing.check_evidence(sales, r, b)
    assert (f"{case['id']} (automated): evidence is for an older build digest; re-run against the current build"
            in r.messages("fail"))
    assert not r.messages("warn")


def test_cli_usage_errors_exit_2(capsys):
    assert main(["check", "--gate", "G1", "--root", str(ROOT)]) == 2   # neither a product nor --all
    assert "name a product or pass --all" in capsys.readouterr().err
    assert main(["proto", "init", "--quiet", "--root", str(ROOT)]) == 2
    assert "name a product" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        main(["check", "--all", "--gate", "G9"])
    assert exc.value.code == 2


def test_cli_json_report(capsys):
    assert main(["brd", "validate", "sales_performance", "--no-write", "--json", "--root", str(ROOT)]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["failures"] == 0 and doc["entries"]
    assert {e["gate"] for e in doc["entries"]} == {"G0"}


# ----------------------------------------------------------------- evals runner
def test_eval_runner_warns_on_a_fresh_workspace_and_fails_on_unknown_ids(tmp_path):
    from dpf.evals import run_evals
    (tmp_path / "tests/evals").mkdir(parents=True)
    r = quiet()
    assert run_evals(Workspace(tmp_path), r) == 0
    assert r.failures == 0 and r.warnings == 1
    r = quiet()
    assert run_evals(Workspace(tmp_path), r, only=["no-such-eval"]) == 1
    assert r.messages("fail") == ["no eval with id no-such-eval under tests/evals/"]


# ----------------------------------------------------------------- wishlist capabilities
def _clone_workspace(tmp_path: Path) -> Workspace:
    import shutil
    from dpf.evals import COPY, IGNORE
    for rel in COPY:
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, tmp_path / rel, ignore=IGNORE)
    return Workspace(tmp_path)


def test_multi_environment_configs_and_permissions(tmp_path):
    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("sales_performance")
    man = p.manifest
    man["deployment"]["environments"] = {
        "dev": {
            "gcp_project": "example-dpf-dev",
            "dataset_prefix": "dev_",
            "prevent_destroy": False,
            "enforce_policy_tags": False,
            "principals": {
                "finance_readers_group": "dev-finance@example.com",
                "pii_unmasked_group": "dev-pii@example.com",
            },
        },
        "prod": {
            "gcp_project": "example-dpf-prod",
            "prevent_destroy": True,
            "enforce_policy_tags": True,
            "principals": {
                "finance_readers_group": "prod-finance@example.com",
                "pii_unmasked_group": "prod-pii@example.com",
            },
        },
    }
    assert twin_ws.validate(man, "product-manifest.v1") == []

    b_base = build(p)
    assert "terraform/envs/dev.tfvars" in b_base.files
    assert "terraform/envs/prod.tfvars" in b_base.files

    b_dev = build(p, env="dev")
    assert b_dev.ok, b_dev.problems
    assert "terraform/envs/dev.tfvars" in b_dev.files
    assert "terraform/envs/prod.tfvars" not in b_dev.files
    assert 'project_id = "example-dpf-dev"' in b_dev.files["terraform/envs/dev.tfvars"]
    assert 'finance_readers_group = "dev-finance@example.com"' in b_dev.files["terraform/envs/dev.tfvars"]
    # dev disables policy tags and prevent_destroy, and prefixes datasets with dev_
    assert "terraform/governance.tf" not in b_dev.files
    assert "prevent_destroy = false" in b_dev.files["terraform/datasets.tf"]
    assert 'dataset_id                 = "dev_gold_sales"' in b_dev.files["terraform/datasets.tf"]
    assert "bigqueryPolicyTags" not in b_dev.files["dataform/definitions/silver/dim_customer.sqlx"]

    b_prod = build(p, env="prod", engine="dbt")
    assert b_prod.ok, b_prod.problems
    assert "terraform/governance.tf" in b_prod.files
    assert "prevent_destroy = true" in b_prod.files["terraform/datasets.tf"]
    profiles = yaml.safe_load(b_prod.files["dbt/profiles.yml.example"])
    assert set(profiles["dpf_sales_performance"]["outputs"]) == {"dev", "prod"}
    assert profiles["dpf_sales_performance"]["outputs"]["dev"]["dataset"] == "dev_stg_sales"


def test_non_blocking_quarantine_and_percentage_thresholds(tmp_path):
    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("customer_orders")
    man = p.manifest
    man["quality"]["max_reject_pct"] = 5.0
    man["quality"]["warn_reject_pct"] = 1.0
    for r in man["quality"]["rules"]:
        if r.get("on_fail") == "quarantine":
            r["severity"] = "warn"
    assert twin_ws.validate(man, "product-manifest.v1") == []

    b = build(p)
    assert b.ok, b.problems
    # Staging still filters out bad rows (_reject_reason IS NULL)
    assert "_reject_reason IS NULL" in b.files["dataform/definitions/staging/stg_orders.sqlx"]
    # Reject gate is now warn-level and checks > 5.0%, and does NOT block downstream customer_orders
    gate_case = next(c for c in b.spec["cases"] if c["id"] == "reject_gate:stg_orders")
    assert gate_case["severity"] == "warn"
    assert "SAFE_DIVIDE(COUNTIF(_reject_reason IS NOT NULL) * 100.0, COUNT(*)) > 5.0" in gate_case["sql"]
    warn_case = next(c for c in b.spec["cases"] if c["id"] == "reject_warn:stg_orders")
    assert warn_case["severity"] == "warn"
    co_action = next(a for a in b.actions if a.name == "customer_orders")
    assert "assert_stg_orders_no_rejects" not in co_action.dependencies


def test_bqml_model_training_and_prediction_roles(tmp_path):
    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("customer_orders")
    pdir = p.dir
    (pdir / "sql/mdl_high_value.sql").write_text(
        "SELECT\n  order_total,\n  IF(order_total > 100, 1, 0) AS label\nFROM {{ ref('stg_orders') }}\n",
        encoding="utf-8",
    )
    (pdir / "sql/pred_high_value.sql").write_text(
        "SELECT\n  order_id,\n  predicted_label\n"
        "FROM ML.PREDICT(MODEL {{ ref('mdl_high_value') }}, (SELECT order_id, order_total FROM {{ ref('stg_orders') }}))\n",
        encoding="utf-8",
    )
    man = p.manifest
    man["layers"]["gold"]["models"].extend([
        {
            "name": "mdl_high_value",
            "role": "ml_model",
            "grain_statement": "One trained logistic regression model over stg_orders",
            "grain_columns": ["order_id"],
            "history_semantics": "current_only",
            "materialisation": "bqml_model",
            "body": "sql/mdl_high_value.sql",
            "attributes": {
                "model_type": "LOGISTIC_REG",
                "options": {"input_label_cols": ["label"]},
                "evaluation": {"metric": "roc_auc", "min": 0.75},
            },
            "brd_requirement_id": ["R-1"],
        },
        {
            "name": "pred_high_value",
            "role": "ml_prediction",
            "grain_statement": "One prediction row per order_id",
            "grain_columns": ["order_id"],
            "history_semantics": "current_only",
            "materialisation": "table",
            "body": "sql/pred_high_value.sql",
            "brd_requirement_id": ["R-1"],
        },
    ])
    assert twin_ws.validate(man, "product-manifest.v1") == []

    b_df = build(p)
    assert b_df.ok, b_df.problems
    mdl_sqlx = b_df.files["dataform/definitions/gold/mdl_high_value.sqlx"]
    assert 'type: "operations"' in mdl_sqlx
    assert "hasOutput: true" in mdl_sqlx
    assert "CREATE OR REPLACE MODEL ${self()}" in mdl_sqlx
    assert "OPTIONS(model_type='LOGISTIC_REG', input_label_cols=['label']) AS" in mdl_sqlx
    eval_sqlx = b_df.files["dataform/definitions/assertions/assert_mdl_high_value_ml_eval.sqlx"]
    assert 'FROM ML.EVALUATE(MODEL ${ref("mdl_high_value")})' in eval_sqlx
    assert "WHERE roc_auc < 0.75" in eval_sqlx

    b_dbt = build(p, engine="dbt")
    assert b_dbt.ok, b_dbt.problems
    assert "materialized='bqml_model'" in b_dbt.files["dbt/models/gold/mdl_high_value.sql"]
    assert "CREATE OR REPLACE MODEL {{ this }}" in b_dbt.files["dbt/models/gold/mdl_high_value.sql"]
    assert "dbt/macros/materializations/bqml_model.sql" in b_dbt.files


def test_versioned_semantic_layer_generation(tmp_path):
    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("sales_performance")
    p.manifest["semantic_layer"] = {
        "targets": ["cube", "metricflow", "atscale", "osi"],
        "brd_requirement_id": ["R-1"],
    }
    assert twin_ws.validate(p.manifest, "product-manifest.v1") == []
    b = build(p)
    assert b.ok, b.problems
    assert "semantic-layer.json" in b.files
    sl = json.loads(b.files["semantic-layer.json"])
    assert sl["artefact_digest"] == b.digest
    assert sl["version"] == str(p.manifest["version"])
    assert "semantic_layer/cube/fct_order_line.yml" in b.files
    assert "semantic_layer/metricflow/semantic_models.yml" in b.files
    assert "semantic_layer/atscale/sales_performance.atscale.yml" in b.files
    assert "semantic_layer/osi/sales_performance.osi.yaml" in b.files


def test_playback_md_and_playback_digest_support(tmp_path):
    from dpf.design import check_design, write_signoff
    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("customer_orders")
    old_sem = p.tdd_dir / "semantics.md"
    new_pb = p.tdd_dir / "playback.md"
    new_pb.write_text(old_sem.read_text(encoding="utf-8"), encoding="utf-8")
    old_sem.unlink()
    assert p.playback_path == new_pb
    assert p.semantics_path == new_pb
    so = write_signoff(p, by="Test Owner", role="business_owner")
    assert "playback_digest" in so
    assert so["playback_digest"] == p.playback_digest()
    r = quiet()
    check_design(twin_ws.product("customer_orders"), r)
    assert r.failures == 0, r.messages("fail")
    b = build(twin_ws.product("customer_orders"))
    cat = json.loads(b.files["catalog-registration.json"])
    assert cat["playback_link"].endswith("playback.md")


def test_expanded_orchestration_engines(tmp_path):
    import re
    var_ref = re.compile(r"\bvar\.([A-Za-z0-9_]+)")
    var_decl = re.compile(r'^variable\s+"([A-Za-z0-9_]+)"', re.M)

    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("customer_orders")

    for orch in ("dataform", "composer", "cloud_run_jobs", "cloud_workflows", "dagster", "prefect"):
        for eng in (None, "dbt"):
            p.manifest["orchestration"]["engine"] = orch
            b = build(p, engine=eng)
            assert b.ok, f"orch={orch} eng={eng}: {b.problems}"
            declared = set(var_decl.findall(b.files.get("terraform/variables.tf", "")))
            used = {v for path, text in b.files.items()
                    if path.startswith("terraform/") and path.endswith(".tf")
                    for v in var_ref.findall(text)}
            assert used - declared == set(), f"orch={orch} eng={eng} undeclared={used - declared}"
            has_df_wf = "google_dataform_repository_workflow_config" in b.files.get("terraform/orchestration.tf", "")
            assert has_df_wf == (orch == "dataform" and eng is None)

    p.manifest["orchestration"]["engine"] = "cloud_run_jobs"
    b_cr = build(p)
    assert 'resource "google_cloud_run_v2_job" "runner"' in b_cr.files["terraform/orchestration.tf"]
    assert 'resource "google_cloud_scheduler_job" "daily"' in b_cr.files["terraform/orchestration.tf"]

    p.manifest["orchestration"]["engine"] = "cloud_workflows"
    b_wf = build(p)
    assert 'resource "google_workflows_workflow" "product"' in b_wf.files["terraform/orchestration.tf"]
    assert "workflowInvocations" in b_wf.files["terraform/orchestration.tf"]

    p.manifest["orchestration"]["engine"] = "composer"
    b_af = build(p)
    assert "airflow/dags/customer_orders_dag.py" in b_af.files
    assert "pendulum.datetime(2026, 1, 1, tz='Australia/Perth')" in b_af.files["airflow/dags/customer_orders_dag.py"]

    p.manifest["orchestration"]["engine"] = "dagster"
    b_dg = build(p)
    assert "dagster/customer_orders_assets.py" in b_dg.files

    p.manifest["orchestration"]["engine"] = "prefect"
    b_pf = build(p)
    assert "prefect/customer_orders_flow.py" in b_pf.files


def test_terraform_prevent_destroy_safeguard(ws, sales):
    b = build(sales)
    for tf_file in ("terraform/datasets.tf", "terraform/governance.tf", "terraform/sharing.tf", "terraform/control.tf"):
        assert "lifecycle {\n    prevent_destroy = true\n  }" in b.files[tf_file]


def test_prototype_cheat_code_and_promotion(tmp_path, capsys):
    _clone_workspace(tmp_path)
    root = str(tmp_path)
    # 1. Scaffold prototype product without BRD/TDD
    assert main(["proto", "init", "citibike_proto", "--quiet", "--root", root]) == 0
    # 2. --gate proto passes
    assert main(["check", "citibike_proto", "--gate", "proto", "--quiet", "--root", root]) == 0
    # 3. dpf generate works directly in prototype mode (and sets prevent_destroy = false)
    assert main(["generate", "citibike_proto", "--quiet", "--root", root]) == 0
    ds_tf = (tmp_path / "generated/citibike_proto/terraform/datasets.tf").read_text(encoding="utf-8")
    assert "prevent_destroy = false" in ds_tf
    # 4. G0 and G1 block prototype products until promoted
    assert main(["check", "citibike_proto", "--gate", "G0", "--quiet", "--root", root]) == 1
    assert main(["check", "citibike_proto", "--gate", "G1", "--quiet", "--root", root]) == 1
    capsys.readouterr()
    # 5. Promote prototype to draft and verify BRD/TDD + playback.md are scaffolded
    assert main(["proto", "promote", "citibike_proto", "--quiet", "--root", root]) == 0
    p = Workspace(tmp_path).product("citibike_proto")
    assert not p.is_prototype
    assert (p.tdd_dir / "playback.md").exists()


def test_dataform_gemini_md_labels_and_release_gate(tmp_path):
    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("sales_performance")
    b = build(p)
    assert b.ok, b.problems
    assert "dataform/GEMINI.md" in b.files
    assert "ADR-017" in b.files["dataform/GEMINI.md"]
    assert "`fct_order_line`" in b.files["dataform/GEMINI.md"]

    fct_sqlx = b.files["dataform/definitions/silver/fct_order_line.sqlx"]
    assert 'dpf_product: "sales_performance"' in fct_sqlx
    assert 'dpf_layer: "silver"' in fct_sqlx
    assert 'dpf_status: "draft"' in fct_sqlx
    # Views do not carry table-only BigQuery labels block
    stg_sqlx = b.files["dataform/definitions/staging/stg_order_lines.sqlx"]
    assert "dpf_product:" not in stg_sqlx
    # Governed builds disable auto-release cron by default so unreviewed console edits cannot auto-promote
    vars_tf = b.files["terraform/variables.tf"]
    assert 'variable "dataform_release_schedule" {' in vars_tf
    assert 'type        = string\n  default     = ""\n}' in vars_tf.split('variable "dataform_release_schedule" {', 1)[1]
    assert 'cron_schedule = var.dataform_release_schedule == "" ? null : var.dataform_release_schedule' in b.files["terraform/orchestration.tf"]
    assert "dataform/GEMINI.md" not in build(p, engine="dbt").files

    # Prototype builds keep hourly auto-release convenience in dev sandboxes
    p.manifest["status"] = "prototype"
    b_proto = build(p)
    proto_vars = b_proto.files["terraform/variables.tf"]
    assert 'type        = string\n  default     = "0 * * * *"\n}' in proto_vars.split('variable "dataform_release_schedule" {', 1)[1]


def test_staging_anti_silent_drop_and_dataform_js_leakage(tmp_path):
    from dpf.design import check_design, check_prototype

    twin_ws = _clone_workspace(tmp_path)
    stg_file = twin_ws.root / "products/customer_orders/sql/stg_orders.sql"
    orig_sql = stg_file.read_text(encoding="utf-8")

    # 1. Unmarked top-level WHERE fails G1
    stg_file.write_text(orig_sql + "\nWHERE order_total > 0\n", encoding="utf-8")
    r = quiet()
    check_design(twin_ws.product("customer_orders"), r)
    assert any("silently drops rows before quarantine" in m for m in r.messages("fail"))

    # 2. Top-level QUALIFY fails G1
    stg_file.write_text(
        orig_sql + "\nQUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY source_modified_ts DESC) = 1\n",
        encoding="utf-8",
    )
    r = quiet()
    check_design(twin_ws.product("customer_orders"), r)
    assert any("bypasses dpf deduplication and quarantine" in m for m in r.messages("fail"))

    # 3. Subquery WHERE / QUALIFY inside parentheses passes
    subq_sql = orig_sql.replace(
        "{{ ref('raw_orders') }}",
        "(SELECT * FROM {{ ref('raw_orders') }} WHERE order_id IS NOT NULL QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingest_ts DESC) = 1)",
    )
    stg_file.write_text(subq_sql, encoding="utf-8")
    r = quiet()
    check_design(twin_ws.product("customer_orders"), r)
    assert not any("silently drops rows" in m or "bypasses dpf deduplication" in m for m in r.messages("fail"))

    # 4. -- dpf: allow_staging_filter=true warns in prototype mode, fails G1 without decision=D-n, passes G1 with decision=D-1
    stg_file.write_text("-- dpf: allow_staging_filter=true\n" + orig_sql + "\nWHERE order_total > 0\n", encoding="utf-8")
    r_g1_bad = quiet()
    check_design(twin_ws.product("customer_orders"), r_g1_bad)
    assert any("must cite a valid TDD decision=D-n at G1" in m for m in r_g1_bad.messages("fail"))

    p_proto = twin_ws.product("customer_orders")
    p_proto.manifest["status"] = "prototype"
    r_proto = quiet()
    check_prototype(p_proto, r_proto)
    assert r_proto.failures == 0, r_proto.messages("fail")
    assert any("allowed top-level WHERE filter" in m for m in r_proto.messages("warn"))

    stg_file.write_text("-- dpf: allow_staging_filter=true decision=D-1\n" + orig_sql + "\nWHERE order_total > 0\n", encoding="utf-8")
    r_g1_ok = quiet()
    check_design(twin_ws.product("customer_orders"), r_g1_ok)
    assert not any("silently drops rows" in m or "must cite a valid TDD decision" in m for m in r_g1_ok.messages("fail"))

    # 5. Dataform-specific ${ref(...)} syntax inside sql/*.sql fails check_design
    stg_file.write_text(orig_sql.replace("{{ ref('raw_orders') }}", '${ref("raw_orders")}'), encoding="utf-8")
    r_js = quiet()
    check_design(twin_ws.product("customer_orders"), r_js)
    assert any("Dataform-specific" in m for m in r_js.messages("fail"))


def test_proto_import_dataform_and_promote(tmp_path, capsys):
    _clone_workspace(tmp_path)
    dea_dir = tmp_path / "dea_export"
    (dea_dir / "definitions/sources").mkdir(parents=True)
    (dea_dir / "definitions/staging").mkdir(parents=True)
    (dea_dir / "definitions/marts").mkdir(parents=True)

    (dea_dir / "workflow_settings.yaml").write_text(
        "defaultProject: dea-sandbox\ndefaultLocation: australia-southeast1\ndataformCoreVersion: 3.0.0\n",
        encoding="utf-8",
    )
    (dea_dir / "definitions/sources/raw_trips.sqlx").write_text(
        'config { type: "declaration", schema: "raw_mobility", name: "raw_trips" }\n',
        encoding="utf-8",
    )
    (dea_dir / "definitions/sources/raw_stations.sqlx").write_text(
        'config { type: "declaration", schema: "raw_mobility", name: "raw_stations" }\n',
        encoding="utf-8",
    )
    (dea_dir / "definitions/staging/stg_trips.sqlx").write_text(
        'config {\n'
        '  type: "view",\n'
        '  assertions: { uniqueKey: ["trip_id"], nonNull: ["trip_id", "station_id"] }\n'
        '}\n'
        'SELECT trip_id, station_id, duration_sec, updated_at\n'
        'FROM ${ref("raw_trips")}\n'
        'WHERE duration_sec > 0\n',
        encoding="utf-8",
    )
    (dea_dir / "definitions/marts/station_summary.sqlx").write_text(
        'config {\n'
        '  type: "table",\n'
        '  assertions: { uniqueKey: ["station_id"] }\n'
        '}\n'
        'SELECT t.station_id, s.station_name, COUNT(*) AS trip_count\n'
        'FROM ${ref("stg_trips")} AS t\n'
        'LEFT JOIN ${ref("raw_stations")} AS s ON t.station_id = s.station_id\n'
        'GROUP BY 1, 2\n',
        encoding="utf-8",
    )

    root = str(tmp_path)
    assert main(["proto", "import-dataform", "mobility_proto", "--from", str(dea_dir), "--quiet", "--root", root]) == 0
    assert main(["check", "mobility_proto", "--gate", "proto", "--quiet", "--root", root]) == 0
    assert main(["generate", "mobility_proto", "--quiet", "--root", root]) == 0

    ws_imported = Workspace(tmp_path)
    p = ws_imported.product("mobility_proto")
    stg_names = {m["name"] for _, m in p.models(("staging",))}
    assert {"stg_trips", "stg_stations"} <= stg_names
    gold_sql = (p.dir / "sql/station_summary.sql").read_text(encoding="utf-8")
    assert "{{ ref('stg_stations') }}" in gold_sql
    assert "${ref" not in gold_sql
    assert len((p.manifest.get("quality") or {}).get("rules") or []) == 2

    assert main(["proto", "promote", "mobility_proto", "--quiet", "--root", root]) == 0
    capsys.readouterr()
    assert not Workspace(tmp_path).product("mobility_proto").is_prototype


def test_dpf_init_copies_agents_skills(tmp_path):
    dest = tmp_path / "new_ws"
    assert main(["init", str(dest), "--quiet"]) == 0
    assert (dest / ".agents/skills.json").exists()
    assert (dest / ".agents/skills/goldfish-verify/SKILL.md").exists()
    assert (dest / ".agents/skills/assess-use-case/SKILL.md").exists()
    assert (dest / "framework/contracts/product-manifest.v1.schema.json").exists()
    assert (dest / "framework/templates/define/1-use-case.pdf").exists()
    assert (dest / "docs/adr/ADR-019-symbiotic-agentic-governance-framework.md").exists()
    assert not (dest / "products/sales_performance").exists()
    assert not (dest / "docs/fhd").exists()
    assert main(["validate", "--quiet", "--root", str(dest)]) == 0
    assert main(["lint", "--quiet", "--root", str(dest)]) == 0


def test_lookml_coupled_hub_spoke_auth_and_env_retargeting(tmp_path):
    from dpf.core import retarget_env

    twin_ws = _clone_workspace(tmp_path)
    p = twin_ws.product("sales_performance")
    b = build(p)
    assert b.ok, b.problems

    # 1. Coupled LookML project files generated on sales_performance
    assert "semantic_layer/lookml/manifest.lkml" in b.files
    assert "semantic_layer/lookml/sales_performance.model.lkml" in b.files
    assert "semantic_layer/lookml/views/fct_order_line.view.lkml" in b.files
    assert "semantic_layer/lookml/views/dim_customer.view.lkml" in b.files
    assert "semantic_layer/lookml/explores/order_lines.explore.lkml" in b.files
    assert "semantic_layer/lookml/dashboards/executive_sales_pulse.dashboard.lookml" in b.files
    assert "semantic_layer/lookml/GEMINI.md" in b.files

    fct_lkml = b.files["semantic_layer/lookml/views/fct_order_line.view.lkml"]
    assert "dimension: _dpf_pk {" in fct_lkml
    assert "primary_key: yes" in fct_lkml
    assert 'filters: [is_cancelled: "no"]' in fct_lkml

    exp_lkml = b.files["semantic_layer/lookml/explores/order_lines.explore.lkml"]
    assert "sql_on: ${fct_order_line.sk_customer} = ${dim_customer.sk_customer} ;;" in exp_lkml
    assert "conditionally_filter: {" in exp_lkml
    assert "aggregate_table: sales_performance_monthly {" in exp_lkml

    dash_lkml = b.files["semantic_layer/lookml/dashboards/executive_sales_pulse.dashboard.lookml"]
    assert "unpinAxis: false" in dash_lkml
    assert "order_date: fct_order_line.order_date" in dash_lkml

    # 2. Hub-and-Spoke import_views_from emits local_dependency and +view refinements
    p.manifest["semantic_layer"]["looker"]["import_views_from"] = "sales_hub"
    b_hub = build(p)
    assert b_hub.ok, b_hub.problems
    assert 'local_dependency: {\n  project: "sales_hub"\n}' in b_hub.files["semantic_layer/lookml/manifest.lkml"]
    assert 'include: "//sales_hub/views/fct_order_line.view.lkml"' in b_hub.files["semantic_layer/lookml/views/fct_order_line.view.lkml"]
    assert "view: +fct_order_line {" in b_hub.files["semantic_layer/lookml/views/fct_order_line.view.lkml"]

    # 3. service_account auth_mode emits LookML access_grant + required_access_grants + Terraform READER IAM
    del p.manifest["semantic_layer"]["looker"]["import_views_from"]
    p.manifest["semantic_layer"]["looker"]["auth_mode"] = "service_account"
    p.manifest["semantic_layer"]["looker"]["service_account_var"] = "looker_sa_email"
    b_sa = build(p)
    assert b_sa.ok, b_sa.problems
    assert "access_grant: can_view_pii_contact {" in b_sa.files["semantic_layer/lookml/sales_performance.model.lkml"]
    assert "required_access_grants: [can_view_pii_contact]" in b_sa.files["semantic_layer/lookml/views/dim_customer.view.lkml"]
    assert 'variable "looker_sa_email"' in b_sa.files["terraform/variables.tf"]
    assert "var.looker_sa_email" in b_sa.files["terraform/access.tf"]

    # 4. Environment retargeting updates LookML manifest constants
    p_env_base = twin_ws.product("sales_performance")
    p_env_base.manifest["deployment"]["environments"] = {"prod": {"gcp_project": "dpf-example-prod"}}
    p_prod = retarget_env(p_env_base, "prod")
    b_prod = build(p_prod)
    assert b_prod.ok, b_prod.problems
    prod_manifest = b_prod.files["semantic_layer/lookml/manifest.lkml"]
    assert 'value: "dpf-example-prod"' in prod_manifest


def test_decoupled_looker_product_mode_a_and_upstream_guards(tmp_path):
    import yaml
    from dpf.brd import check_brd
    from dpf.compose import check_acceptance, compose
    from dpf.design import check_design, write_signoff
    from dpf.generate import generate
    from dpf.trace import check_trace

    twin_ws = _clone_workspace(tmp_path)
    root = twin_ws.root

    # Author a governed Mode-A decoupled Looker data product over sales_performance (zero sources/layers)
    brd_dir = root / "openspec/specs/products/sales/exec-looker-cockpit/brd"
    tdd_dir = root / "openspec/specs/products/sales/exec-looker-cockpit/tdd"
    p_dir = root / "products/exec_looker_cockpit"
    brd_dir.mkdir(parents=True)
    tdd_dir.mkdir(parents=True)
    p_dir.mkdir(parents=True)

    (brd_dir / "spec.md").write_text(
        "# Executive Sales Cockpit — Business Requirements\n\n"
        "## Purpose\n\n"
        "**BRD:** BRD-SALES-010 · **Version:** 1.0.0 · **Status:** approved · **Owner:** Sales Leadership · **Steward:** Data Analytics\n\n"
        "Give sales leadership a governed self-service exploration surface and executive summary board over verified order lines.\n\n"
        "## Requirements\n\n"
        "### Requirement: Regional and segment net sales board\n"
        "**ID:** R-1\n\n"
        "Sales leadership SHALL view net sales by region and customer segment on an interactive summary board.\n\n"
        "#### Scenario: Filtering by region\n"
        "**ID:** AX-1\n"
        "- **WHEN** a director filters the board to a region\n"
        "- **THEN** net sales and order counts reflect non-cancelled lines for that region\n",
        encoding="utf-8",
    )
    co_brd = yaml.safe_load((root / "openspec/specs/products/sales/customer-orders/brd/brd.yaml").read_text(encoding="utf-8"))
    co_brd["product_id"] = "exec_looker_cockpit"
    co_brd["brd_id"] = "BRD-SALES-010"
    co_brd["version"] = "1.0.0"
    co_brd["fitness"]["on_bad_data"] = "Handled upstream by sales_performance."
    co_brd["timeliness"]["freshness_need"] = "Within 2 hours during business hours."
    co_brd["exceptions"] = ["Amendments are handled upstream."]
    for key, val in list(co_brd.items()):
        if isinstance(val, dict) and "satisfies" in val:
            val["satisfies"] = ["R-1"]
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and "satisfies" in item:
                    item["satisfies"] = ["R-1"]
    (brd_dir / "brd.yaml").write_text(yaml.safe_dump(co_brd, sort_keys=False), encoding="utf-8")

    (tdd_dir / "spec.md").write_text(
        "# Executive Sales Cockpit — Technical Design\n\n"
        "## Purpose\n\n"
        "**TDD:** TDD-SALES-010 · **Satisfies:** BRD-SALES-010@1.0.0 · **Version:** 1.0.0 · **Owner:** Data Analytics\n\n"
        "Decoupled LookML semantic and dashboard data product bound to `sales_performance`.\n\n"
        "## Requirements\n\n"
        "### Requirement: Decoupled LookML explore and dashboard\n"
        "**Decision:** D-1 · **Satisfies:** R-1 · **ADR:** ADR-018\n\n"
        "The product SHALL bind `sales_performance` (>= 1.2.0) and publish an `order_lines` LookML explore and `exec_board` dashboard.\n\n"
        "#### Scenario: Explore and dashboard compile cleanly\n"
        "- **WHEN** artefacts are generated\n"
        "- **THEN** LookML views, explore and dashboard SHALL reference `sales_performance` silver datasets with zero PDTs\n\n"
        "## Decision records\n\n"
        "- **ADR-018** (platform): governed LookML semantic explore and dashboard over upstream DPF product (D-1).\n",
        encoding="utf-8",
    )
    (tdd_dir / "semantics.md").write_text(
        "# Executive Sales Cockpit — what you will receive\n\n"
        "- An interactive summary board of net sales by region and customer segment over verified order lines.\n",
        encoding="utf-8",
    )

    (p_dir / "acceptance.yaml").write_text(
        yaml.safe_dump({
            "product_id": "exec_looker_cockpit",
            "tests": [
                {
                    "id": "AT-1",
                    "verifies": ["AX-1"],
                    "method": "static",
                    "check": "lookml_dashboard",
                    "element": "dashboard:exec_board",
                    "description": "Executive LookML dashboard resolves all fields and anchors bars at zero.",
                }
            ],
        }, sort_keys=False),
        encoding="utf-8",
    )

    manifest = {
        "product_id": "exec_looker_cockpit",
        "version": "1.0.0",
        "status": "draft",
        "owner": "sales-leadership",
        "steward": "data-analytics",
        "domain": "sales",
        "classification": "INTERNAL-COMMERCIAL",
        "registry_overlay": "examples/registry",
        "specs": {
            "brd": "products/sales/exec-looker-cockpit/brd",
            "tdd": "products/sales/exec-looker-cockpit/tdd",
        },
        "brd_id": "BRD-SALES-010",
        "tdd_id": "TDD-SALES-010",
        "satisfies": "BRD-SALES-010@1.0.0",
        "adrs": ["ADR-018"],
        "acceptance": "acceptance.yaml",
        "deployment": {
            "gcp_project": "data-product-framework",
            "region": "us-central1",
            "datasets": {},
        },
        "upstream": [
            {
                "product": "sales_performance",
                "min_version": "1.2.0",
                "models": ["fct_order_line", "dim_customer", "dim_product", "dim_date"],
                "brd_requirement_id": ["R-1"],
            }
        ],
        "output_ports": [
            {
                "name": "exec_explore",
                "type": "looker_explore",
                "explore": "order_lines",
                "access": "looker_model_set",
                "consumers": ["sales-leadership"],
                "brd_requirement_id": ["R-1"],
            },
            {
                "name": "exec_board",
                "type": "looker_dashboard",
                "dashboard": "exec_board",
                "access": "looker_folder_grant",
                "consumers": ["sales-leadership"],
                "brd_requirement_id": ["R-1"],
            },
        ],
        "observability": {
            "freshness": [
                {
                    "id": "OB-1",
                    "model": "fct_order_line",
                    "max_staleness": "PT2H",
                    "check_every": "PT30M",
                    "brd_requirement_id": ["R-1"],
                }
            ],
            "schema_drift": {
                "on_additive": "land_and_record",
                "on_breaking": "quarantine_and_alert",
                "implements": "monitor-data-product",
            },
            "alerting": {
                "notification_channel_var": "alert_channel",
            },
            "slo": {
                "objective": 0.99,
                "window": "P28D",
            },
        },
        "governance": {
            "register": "knowledge_catalog",
            "registered_via": "knowledge-catalog-mcp",
        },
        "semantic_layer": {
            "targets": ["lookml"],
            "looker": {"connection": "bigquery_sales", "project_name": "exec_looker_cockpit", "auth_mode": "oauth"},
            "metrics": [
                {
                    "name": "net_sales",
                    "label": "Net Sales",
                    "type": "simple",
                    "model": "fct_order_line",
                    "expr": "net_amount",
                    "filter": "is_cancelled = FALSE",
                }
            ],
            "explores": [
                {
                    "name": "order_lines",
                    "from": "fct_order_line",
                    "joins": "auto",
                    "brd_requirement_id": ["R-1"],
                }
            ],
            "dashboards": [
                {
                    "name": "exec_board",
                    "title": "Executive Sales Cockpit",
                    "explore": "order_lines",
                    "brd_requirement_id": ["R-1"],
                    "filters": [{"name": "region", "title": "Region", "field": "dim_customer.region"}],
                    "tiles": [
                        {
                            "name": "sales_by_region",
                            "title": "Net Sales by Region",
                            "kind": "ranked_bar",
                            "dimensions": ["dim_customer.region"],
                            "measures": ["fct_order_line.net_sales"],
                            "y_axis_zero": True,
                        }
                    ],
                }
            ],
        },
    }
    (p_dir / "product.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    ws2 = Workspace(root)
    p_dec = ws2.product("exec_looker_cockpit")
    write_signoff(p_dec, "Sales VP", "business_owner", "2026-10-05", "Signed", None)
    ws2 = Workspace(root)
    p_dec = ws2.product("exec_looker_cockpit")

    r = quiet()
    check_brd(p_dec, r, write_gaps=False)
    check_design(p_dec, r)
    ok_dag, dag = compose(p_dec, r, write=False)
    assert ok_dag, r.messages("fail")
    assert any(n["skill"] == "bind-upstream-foundation" for n in dag["nodes"])
    assert any(n["skill"] == "render-lookml-artefacts" for n in dag["nodes"])
    assert not any(n["stage"] == "orchestrate" for n in dag["nodes"])
    check_acceptance(p_dec, r)
    b = generate(p_dec, r, check=False, write=False)
    assert b.ok, b.problems
    assert not any(k.startswith("dataform/") or k.startswith("dbt/") for k in b.files)
    assert "value       = {}" in b.files["terraform/outputs.tf"]
    check_trace(p_dec, r, b)
    assert r.failures == 0, r.messages("fail")

    # Upstream SemVer guard fails when min_version > 1.2.0
    p_dec.manifest["upstream"][0]["min_version"] = "2.0.0"
    r_ver = quiet()
    check_design(p_dec, r_ver)
    assert any("below required min_version 2.0.0" in m for m in r_ver.messages("fail"))

    # Upstream freshness SLA guard fails when downstream asks for PT30M < upstream PT1H30M
    p_dec.manifest["upstream"][0]["min_version"] = "1.2.0"
    p_dec.manifest["observability"]["freshness"][0]["max_staleness"] = "PT30M"
    r_sla = quiet()
    check_design(p_dec, r_sla)
    assert any("is tighter than upstream" in m for m in r_sla.messages("fail"))

    # Staging models cannot be bound across products
    p_dec.manifest["observability"]["freshness"][0]["max_staleness"] = "PT2H"
    p_dec.manifest["upstream"][0]["models"].append("stg_order_lines")
    r_stg = quiet()
    check_design(p_dec, r_stg)
    assert any("staging model 'stg_order_lines' cannot be bound across product boundaries" in m for m in r_stg.messages("fail"))


def test_decoupled_external_foundation_mode_b_and_hybrid_gold_view(tmp_path):
    import yaml
    from dpf.compose import compose
    from dpf.design import check_prototype
    from dpf.testing import render_live_sql, run_static

    twin_ws = _clone_workspace(tmp_path)
    root = twin_ws.root

    # Add a foundation entry in registry/foundations.yaml
    (root / "registry/foundations.yaml").write_text(
        yaml.safe_dump({
            "foundations": {
                "core_edw": {
                    "gcp_project": "corp-edw-prod",
                    "dataset": "fin_mart",
                    "owner": "edw-team@example.com",
                    "max_staleness": "PT4H",
                    "tables": [
                        {
                            "name": "gl_postings",
                            "role": "fact",
                            "grain_statement": "One row per GL posting line",
                            "grain_columns": ["posting_id"],
                            "history_semantics": "append_only",
                            "partition_by": "posting_date",
                            "columns": [
                                {"name": "posting_id", "type": "STRING"},
                                {"name": "posting_date", "type": "DATE"},
                                {"name": "cost_center", "type": "STRING"},
                                {"name": "amount_aud", "type": "NUMERIC"},
                            ],
                            "attributes": {"measures": [{"name": "amount_aud", "additivity": "additive"}]},
                        }
                    ],
                }
            }
        }, sort_keys=False),
        encoding="utf-8",
    )

    p_dir = root / "products/fin_gl_looker"
    (p_dir / "sql").mkdir(parents=True)
    # Hybrid mode: thin gold view reading upstream foundation table directly
    (p_dir / "sql/cost_center_summary.sql").write_text(
        "SELECT cost_center, SUM(amount_aud) AS total_aud\nFROM {{ ref('gl_postings') }}\nGROUP BY cost_center\n",
        encoding="utf-8",
    )
    (p_dir / "product.yaml").write_text(
        yaml.safe_dump({
            "product_id": "fin_gl_looker",
            "version": "0.1.0",
            "status": "prototype",
            "owner": "fin-bi@example.com",
            "domain": "finance",
            "classification": "INTERNAL",
            "deployment": {
                "gcp_project": "fin-bi-proj",
                "region": "australia-southeast1",
                "datasets": {"gold": "fin_bi_gold", "assertions": "fin_bi_assertions", "control": "fin_bi_control"},
            },
            "upstream": [{"foundation": "core_edw"}],
            "layers": {
                "gold": {
                    "methodology": "direct",
                    "engine": "dataform",
                    "storage": "bigquery_native",
                    "models": [
                        {
                            "name": "cost_center_summary",
                            "role": "business_view",
                            "grain_statement": "One row per cost center",
                            "grain_columns": ["cost_center"],
                            "history_semantics": "current_only",
                            "materialisation": "view",
                            "body": "sql/cost_center_summary.sql",
                        }
                    ],
                }
            },
            "output_ports": [
                {"name": "gl_explore", "type": "looker_explore", "explore": "gl_postings", "access": "looker_model_set"}
            ],
            "semantic_layer": {
                "targets": ["lookml"],
                "looker": {"connection": "bq_fin", "project_name": "fin_gl_looker"},
                "explores": [{"name": "gl_postings", "from": "gl_postings"}],
            },
        }, sort_keys=False),
        encoding="utf-8",
    )

    ws2 = Workspace(root)
    p_hyb = ws2.product("fin_gl_looker")
    r = quiet()
    check_prototype(p_hyb, r)
    assert r.failures == 0, r.messages("fail")
    ok_dag, _ = compose(p_hyb, r, write=False)
    assert ok_dag, r.messages("fail")

    for eng in (None, "dbt"):
        b = build(p_hyb, engine=eng)
        assert b.ok, f"eng={eng}: {b.problems}"
        case_ids = {c["id"] for c in b.spec["cases"]}
        assert "grain:gl_postings" in case_ids
        assert "grain_not_null:gl_postings" in case_ids

    b_df = build(p_hyb)
    grain_case = next(c for c in b_df.spec["cases"] if c["id"] == "grain:gl_postings")
    live_sql = render_live_sql(p_hyb, b_df, grain_case["sql"])
    assert "`corp-edw-prod.fin_mart.gl_postings`" in live_sql
    static_res = run_static(b_df)
    assert static_res == {"lookml_explore:gl_postings": []}


def test_lookml_design_and_visual_failure_guards(tmp_path):
    from dpf.design import check_design
    from dpf.generate.lookml import validate_lookml_files

    twin_ws = _clone_workspace(tmp_path)

    # 1. allow_pdt: true fails unless a product ADR decides semantic_layer beyond ADR-018
    p = twin_ws.product("sales_performance")
    p.manifest["semantic_layer"]["looker"]["allow_pdt"] = True
    r = quiet()
    check_design(p, r)
    assert any("allow_pdt: true" in m for m in r.messages("fail"))

    # 2. Summing a non_additive measure fails G1
    p = twin_ws.product("sales_performance")
    p.manifest["layers"]["silver"]["models"][3]["attributes"]["measures"].append(
        {"name": "unit_margin_pct", "additivity": "non_additive"}
    )
    p.manifest["semantic_layer"]["metrics"].append(
        {"name": "bad_margin_sum", "type": "simple", "model": "fct_order_line", "expr": "unit_margin_pct"}
    )
    r = quiet()
    check_design(p, r)
    assert any("non_additive" in m for m in r.messages("fail"))

    # 3. Joining SCD2 dimension on natural key fails G1
    p = twin_ws.product("sales_performance")
    p.manifest["semantic_layer"]["explores"][0]["joins"] = [
        {
            "view": "dim_customer",
            "type": "left_outer",
            "relationship": "many_to_one",
            "sql_on": "${fct_order_line.customer_id} = ${dim_customer.customer_id}",
        }
    ]
    r = quiet()
    check_design(p, r)
    assert any("joins SCD2 dimension on natural key" in m for m in r.messages("fail"))

    # 4. Pie chart, unpinned bar axis, and unknown field fail G1
    p = twin_ws.product("sales_performance")
    p.manifest["semantic_layer"]["dashboards"][0]["tiles"].extend([
        {"name": "bad_pie", "title": "Pie", "kind": "pie", "dimensions": ["dim_customer.region"], "measures": ["fct_order_line.net_sales"]},
        {"name": "bad_bar", "title": "Bar", "kind": "ranked_bar", "dimensions": ["dim_customer.region"], "measures": ["fct_order_line.net_sales"], "y_axis_zero": False},
        {"name": "bad_field", "title": "Unknown", "kind": "kpi", "measures": ["fct_order_line.does_not_exist"]},
    ])
    r = quiet()
    check_design(p, r)
    msgs = r.messages("fail")
    assert any("violates Stephen Few visual rules" in m for m in msgs)
    assert any("must anchor Y-axis at zero" in m for m in msgs)
    assert any("does not exist in explore" in m for m in msgs)

    # 5. Built-in LookML syntax & anti-PDT validator catches derived_table and unbalanced braces
    pdt_errs = validate_lookml_files({
        "semantic_layer/lookml/manifest.lkml": 'project_name: "x"\n',
        "semantic_layer/lookml/x.model.lkml": 'connection: "c"\n',
        "semantic_layer/lookml/views/v.view.lkml": "view: v {\n  derived_table: {\n    sql: SELECT 1 ;;\n    sql_trigger_value: SELECT CURRENT_DATE() ;;\n  }\n",
    }, {"looker": {"allow_pdt": False}})
    assert any("unbalanced" in e for e in pdt_errs)
    assert any("derived_table" in e or "PDT" in e for e in pdt_errs)


def test_proto_import_looker_and_promote(tmp_path, capsys):
    _clone_workspace(tmp_path)
    lk_dir = tmp_path / "looker_export"
    (lk_dir / "views").mkdir(parents=True)
    (lk_dir / "dashboards").mkdir(parents=True)

    (lk_dir / "manifest.lkml").write_text(
        'project_name: "retail_pulse"\nconstant: GCP_PROJECT { value: "retail-edw" }\n',
        encoding="utf-8",
    )
    (lk_dir / "retail.model.lkml").write_text(
        'connection: "bq_retail"\ninclude: "/views/*.view.lkml"\n\n'
        'explore: store_sales {\n'
        '  view_name: fct_store_sales\n'
        '  join: dim_store {\n'
        '    type: left_outer\n'
        '    relationship: many_to_one\n'
        '    sql_on: ${fct_store_sales.store_id} = ${dim_store.store_id} ;;\n'
        '  }\n'
        '}\n',
        encoding="utf-8",
    )
    (lk_dir / "views/fct_store_sales.view.lkml").write_text(
        'view: fct_store_sales {\n'
        '  sql_table_name: `@{GCP_PROJECT}.mart_retail.fct_store_sales` ;;\n'
        '  dimension: sale_id { primary_key: yes type: string sql: ${TABLE}.sale_id ;; }\n'
        '  dimension: store_id { type: string sql: ${TABLE}.store_id ;; }\n'
        '  dimension_group: sale { type: time timeframes: [raw, date, month] sql: ${TABLE}.sale_date ;; }\n'
        '  measure: revenue { type: sum sql: ${TABLE}.revenue ;; }\n'
        '}\n',
        encoding="utf-8",
    )
    (lk_dir / "views/dim_store.view.lkml").write_text(
        'view: dim_store {\n'
        '  sql_table_name: `@{GCP_PROJECT}.mart_retail.dim_store` ;;\n'
        '  dimension: store_id { primary_key: yes type: string sql: ${TABLE}.store_id ;; }\n'
        '  dimension: state { type: string sql: ${TABLE}.state ;; }\n'
        '}\n',
        encoding="utf-8",
    )
    (lk_dir / "dashboards/store_overview.dashboard.lookml").write_text(
        '- dashboard: store_overview\n'
        '  title: Store Sales Overview\n'
        '  layout: newspaper\n'
        '  elements:\n'
        '  - name: rev_by_state\n'
        '    title: Revenue by State\n'
        '    model: retail\n'
        '    explore: store_sales\n'
        '    type: looker_bar\n'
        '    fields: [dim_store.state, fct_store_sales.revenue]\n'
        '    y_axes: [{unpinAxis: false}]\n',
        encoding="utf-8",
    )

    root = str(tmp_path)
    assert main(["proto", "import-looker", "retail_looker", "--from", str(lk_dir), "--quiet", "--root", root]) == 0
    assert main(["check", "retail_looker", "--gate", "proto", "--quiet", "--root", root]) == 0
    assert main(["generate", "retail_looker", "--quiet", "--root", root]) == 0
    assert (tmp_path / "generated/retail_looker/semantic_layer/lookml/explores/store_sales.explore.lkml").exists()
    assert (tmp_path / "generated/retail_looker/semantic_layer/lookml/dashboards/store_overview.dashboard.lookml").exists()
    assert main(["proto", "promote", "retail_looker", "--quiet", "--root", root]) == 0
    capsys.readouterr()
    p_prom = Workspace(tmp_path).product("retail_looker")
    assert not p_prom.is_prototype
    assert (p_prom.tdd_dir / "playback.md").exists()


def test_agf_symbiotic_governance_contracts_and_gates(tmp_path):
    from dpf.design import check_design

    # 1. Valid AGF (ADG-00) binding passes G1 and emits all 7 canonical Single-Writer Aspects
    twin_ws = _clone_workspace(tmp_path / "ok")
    p = twin_ws.product("sales_performance")
    p.manifest["adrs"].append("ADR-019")
    p.manifest["governance"]["agf"] = {
        "enabled": True,
        "glossary_ref": "projects/data-product-framework/locations/us-central1/glossaries/enterprise_sales",
        "purpose_codes": ["SALES_REPORTING", "FINANCE_CLOSE"],
        "cde_terms": ["net_sales"],
        "retention_years": 7,
        "legal_hold_default": False,
        "allowed_regions": ["us-central1"],
        "classified_columns": {
            "dim_customer.customer_email": "RESTRICTED",
            "dim_customer.customer_phone": "RESTRICTED",
            "dim_customer.customer_name": "CONFIDENTIAL",
        },
        "brd_requirement_id": ["R-12", "R-13"],
    }
    assert twin_ws.validate(p.manifest, "product-manifest.v1") == []
    r = quiet()
    check_design(p, r)
    assert r.failures == 0, r.messages("fail")

    b = build(p)
    assert b.ok, b.problems
    cat = json.loads(b.files["catalog-registration.json"])
    assert twin_ws.validate(cat, "catalog-registration.v1") == []
    aspects = cat["agf_aspects"]
    assert set(aspects) == {
        "governance-ownership-v1",
        "catalog-registration-v1",
        "sensitivity-classification-v1",
        "cde-financial-governance-v1",
        "lineage-governance-v1",
        "data-product-quality-v1",
        "retention-lifecycle-v1",
    }
    assert aspects["governance-ownership-v1"]["accountability_status"] == "ASSIGNED"
    assert aspects["catalog-registration-v1"]["purpose_codes"] == ["FINANCE_CLOSE", "SALES_REPORTING"]
    assert aspects["cde-financial-governance-v1"]["gl_reconciliation_required"] is True
    assert aspects["retention-lifecycle-v1"]["retention_years"] == 7

    # 2. Residency violation (C10), unknown CDE (DC-2), and external sharing leak (C6) fail G1
    twin_bad = _clone_workspace(tmp_path / "bad")
    partner_sql = twin_bad.root / "products/sales_performance/sql/sales_performance_partner_extract.sql"
    partner_sql.write_text(
        "SELECT d.year_month, p.product_category, c.region, MAX(c.customer_email) AS customer_email, "
        "SUM(f.net_amount) AS net_sales, SUM(f.quantity) AS units_sold "
        "FROM {{ ref('fct_order_line') }} AS f "
        "JOIN {{ ref('dim_date') }} AS d ON d.date_key = f.date_key "
        "JOIN {{ ref('dim_customer') }} AS c ON c.sk_customer = f.sk_customer "
        "JOIN {{ ref('dim_product') }} AS p ON p.sk_product = f.sk_product "
        "GROUP BY d.year_month, p.product_category, c.region\n",
        encoding="utf-8",
    )
    pb = twin_bad.product("sales_performance")
    pb.manifest["governance"]["agf"] = {
        "enabled": True,
        "allowed_regions": ["australia-southeast1"],
        "cde_terms": ["non_existent_term"],
        "classified_columns": {
            "dim_customer.customer_email": "RESTRICTED",
            "dim_customer.customer_phone": "RESTRICTED",
        },
    }
    rb = quiet()
    check_design(pb, rb)
    msgs = rb.messages("fail")
    assert any("AGF C10: deployment.region 'us-central1'" in m for m in msgs)
    assert any("AGF DC-2: unknown cde_terms non_existent_term" in m for m in msgs)
    assert any("AGF C6: external sharing_listing port 'sales_performance_partner_extract' exposes restricted column(s) customer_email" in m for m in msgs)




