"""Unit tests for the dpf package: spec parsing, render helpers, monitor, trace, lint and CLI exit codes.

The example products are the fixtures: they must pass every gate up to G3 and fail G4 honestly,
because no deployed-run evidence exists for them.
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
    assert main(["check", "--all", "--gate", "G3", "--quiet", "--root", str(ROOT)]) == 0
    capsys.readouterr()
    # The examples have no deployed-run evidence, so G4 must fail rather than pass on nothing.
    assert main(["check", "sales_performance", "--gate", "G4", "--quiet", "--root", str(ROOT)]) == 1
    assert "no evidence for build sha256:" in capsys.readouterr().out


def test_cli_usage_errors_exit_2(capsys):
    assert main(["check", "--gate", "G1", "--root", str(ROOT)]) == 2   # neither a product nor --all
    assert "name a product or pass --all" in capsys.readouterr().err
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
