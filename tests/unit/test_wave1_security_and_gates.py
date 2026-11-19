"""Regression tests for Wave 1 security, SQL lexing, gate integrity, orchestration, and bootstrap fixes."""

from __future__ import annotations

import copy
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from dpf.brd import check_brd
from dpf.cli import main
from dpf.compose import compose
from dpf.core import Report, Workspace, load_yaml, retarget_env, write_text
from dpf.design import check_design
from dpf.generate import build
from dpf.generate.docs import catalog_registration, data_product
from dpf.generate.plan import bqml_model_sql, fact_sql, staging_view_sql
from dpf.generate.testspec import quality_condition
from dpf.graph import ProductGraph
from dpf.init import init as dpf_init
from dpf.looker_cockpit import _render_cockpit_html
from dpf.looker_deploy import _resolve_folder_id
from dpf.sql import (
    find_staging_violations,
    safe_subpath,
    select_columns,
    sql_escape_str,
    strip_sql_comments,
)
from dpf.testing import attest, check_evidence, latest_results, render_live_sql, run_tests

ROOT = Path(__file__).resolve().parents[2]


def _make_twin(tmp_path: Path) -> Workspace:
    ignore = shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".venv", ".git", "generated", "evidence", ".pytest_cache",
        ".terraform", "terraform.tfstate*",
    )
    for rel in (
        "framework", "openspec", "registry", "examples", "products", "docs", "bootstrap",
        ".agents", "pyproject.toml", "Makefile", ".gitignore", "AGENTS.md",
    ):
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, tmp_path / rel, ignore=ignore)
        elif src.is_file():
            shutil.copy2(src, tmp_path / rel)
    (tmp_path / "tests/contracts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests/contracts/test_contracts.py", tmp_path / "tests/contracts/test_contracts.py")
    (tmp_path / "tests/evals").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests/evals/README.md", tmp_path / "tests/evals/README.md")
    (tmp_path / "tests/golden").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests/golden/README.md", tmp_path / "tests/golden/README.md")
    return Workspace(tmp_path)


# ------------------------------------------------------------------ 1. SQL lexer (P0-3)
def test_select_columns_handles_valid_from_comments_in_strings_and_union_all():
    sql = """
    -- leading comment
    SELECT
      customer_id,
      valid_from,
      valid_to,
      'https://example.com/--not-a-comment' AS profile_url,
      customer_email
    FROM {{ ref('dim_customer') }}
    UNION ALL
    SELECT id2, vf2, vt2, url2, em2 FROM {{ ref('other') }}
    """
    cols = select_columns(sql)
    assert cols == ["customer_id", "valid_from", "valid_to", "profile_url", "customer_email"]
    stripped = strip_sql_comments(sql)
    assert "'https://example.com/--not-a-comment'" in stripped


def test_staging_violations_catches_cte_where_limit_but_allows_left_join_lookup():
    cte_bypass = """
    WITH filtered AS (
      SELECT id, updated_at AS source_modified_ts, _ingest_ts
      FROM {{ ref('raw_orders') }}
      WHERE amount > 0
      LIMIT 100
    )
    SELECT id, source_modified_ts, _ingest_ts
    FROM filtered
    """
    v = find_staging_violations(cte_bypass)
    assert any("CTE 'filtered'" in s for s in v["where"])
    assert any("CTE 'filtered'" in s for s in v["qualify_limit"])

    # LEFT JOIN lookup deduplication (as in examples/sales_performance/sql/stg_order_lines.sql) is allowed
    valid_lookup = """
    SELECT l.id, o.cust_id, l.source_modified_ts, l._ingest_ts
    FROM {{ ref('raw_lines') }} AS l
    LEFT JOIN (
      SELECT id, cust_id FROM {{ ref('raw_orders') }}
      WHERE TRUE
      QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) = 1
    ) AS o ON o.id = l.id
    """
    v2 = find_staging_violations(valid_lookup)
    assert v2["where"] == []
    assert v2["qualify_limit"] == []


def test_safe_subpath_blocks_traversal_and_absolute_paths(tmp_path: Path):
    base = tmp_path / "prod"
    base.mkdir()
    assert safe_subpath(base, "sql/a.sql") == (base / "sql/a.sql").resolve()
    with pytest.raises(ValueError):
        safe_subpath(base, "../secret.txt")
    with pytest.raises(ValueError):
        safe_subpath(base, "/etc/passwd")


# ------------------------------------------------------------------ 2. AGF decoupled crash + SELECT * (P0-4)
def test_agf_decoupled_upstream_policy_tags_no_typeerror_and_select_star_fails_closed(tmp_path: Path):
    ws = _make_twin(tmp_path)
    p = ws.product("sales_performance")
    # Build a decoupled product binding sales_performance's policy-tagged dim_customer
    dec_dir = tmp_path / "products/decoupled_agf"
    dec_dir.mkdir(parents=True)
    # Minimal BRD/TDD stubs reused from sales_performance for G1 call
    man = {
        "product_id": "decoupled_agf",
        "version": "1.0.0",
        "status": "draft",
        "owner": "owner@example.com",
        "steward": "steward@example.com",
        "domain": "sales",
        "classification": "CONFIDENTIAL",
        "brd_id": "BRD-SALES-002",
        "tdd_id": "TDD-SALES-002",
        "satisfies": "BRD-SALES-002@1.2.0",
        "registry_overlay": "examples/registry",
        "specs": {"brd": "../../../examples/sales_performance/specs/brd",
                  "tdd": "../../../examples/sales_performance/specs/tdd"},
        "deployment": {"gcp_project": "p-dev", "region": "us-central1",
                       "datasets": {"gold": "gold_dec", "sharing": "share_dec"}},
        "upstream": [{"product": "sales_performance", "models": ["dim_customer"], "brd_requirement_id": ["R-1"]}],
        "layers": {
            "gold": {
                "methodology": "direct",
                "engine": "dataform",
                "models": [{
                    "name": "partner_star_view",
                    "role": "business_view",
                    "materialisation": "view",
                    "grain_statement": "One row per customer",
                    "grain_columns": ["customer_id"],
                    "body": "sql/partner_star_view.sql",
                    "brd_requirement_id": ["R-1"],
                }],
            },
        },
        "output_ports": [{
            "name": "ext_port",
            "model": "partner_star_view",
            "type": "bigquery_sharing_listing",
            "access": "sharing_listing",
            "consumers": ["partner"],
            "brd_requirement_id": ["R-1"],
        }],
        "governance": {
            "register": "knowledge_catalog",
            "registered_via": "knowledge-catalog-mcp",
            "agf": {"enabled": True, "classified_columns": {"dim_customer.customer_email": "RESTRICTED"}},
        },
    }
    write_text(dec_dir / "product.yaml", yaml.safe_dump(man, sort_keys=False))
    write_text(dec_dir / "sql/partner_star_view.sql", "SELECT * FROM {{ ref('dim_customer') }}\n")
    dp = ws.product("decoupled_agf")
    g = ProductGraph(dp)
    rep = Report(quiet=True, stream=io.StringIO())
    from dpf.design import _agf_governance
    # Must NOT raise TypeError: unhashable type: 'dict', and MUST fail closed on SELECT * sharing port
    _agf_governance(dp, g, rep)
    fails = rep.messages(Report.FAIL)
    assert any("SELECT *" in m and "ext_port" in m for m in fails), fails


# ------------------------------------------------------------------ 3. Upstream cycle detection (P0-6)
def test_circular_upstream_products_fail_cleanly_without_recursion_error(tmp_path: Path):
    ws = _make_twin(tmp_path)
    for pid, other in (("cycle_a", "cycle_b"), ("cycle_b", "cycle_a")):
        pdir = tmp_path / "products" / pid
        pdir.mkdir(parents=True)
        write_text(pdir / "product.yaml", yaml.safe_dump({
            "product_id": pid,
            "version": "0.1.0",
            "status": "prototype",
            "owner": "o@example.com",
            "domain": "sales",
            "deployment": {"gcp_project": "p-dev", "region": "us-central1", "datasets": {"gold": f"gold_{pid}"}},
            "upstream": [{"product": other, "models": [f"m_{other}"]}],
            "layers": {"gold": {"methodology": "direct", "engine": "dataform", "models": [{
                "name": f"m_{pid}", "role": "business_view", "materialisation": "view",
                "grain_statement": "One row per id", "grain_columns": ["id"], "body": f"sql/m_{pid}.sql",
            }]}},
            "output_ports": [{"name": f"p_{pid}", "model": f"m_{pid}", "type": "bigquery_view", "access": "dataset_grant"}],
        }, sort_keys=False))
        write_text(pdir / f"sql/m_{pid}.sql", f"SELECT id FROM {{{{ ref('m_{other}') }}}}\n")
    pa = ws.product("cycle_a")
    g = ProductGraph(pa)
    assert any("circular upstream product dependency" in prob for prob in g.problems)
    rep = Report(quiet=True, stream=io.StringIO())
    ok, _ = compose(pa, rep, write=False)
    assert not ok
    assert any("circular upstream product dependency" in m for m in rep.messages(Report.FAIL))


# ------------------------------------------------------------------ 4. ADR-009 provisional + G0 hardening (P0-6)
def test_adr009_provisional_status_and_g0_needs_decision_and_open_question_meta(tmp_path: Path):
    ws = _make_twin(tmp_path)
    brd_yaml = tmp_path / "examples/customer_orders/specs/brd/brd.yaml"
    doc = load_yaml(brd_yaml)
    doc["open_questions"] = [{
        "id": "OQ-1",
        "question": "Should gift cards count in order value?",
        "assumption": "Exclude gift card redemptions until Finance confirms.",
        "owner": "Finance Lead",
        "due": "2026-12-01",
    }]
    write_text(brd_yaml, yaml.safe_dump(doc, sort_keys=False))

    p = ws.product("customer_orders")
    dp = data_product(p)
    cr = catalog_registration(p, ProductGraph(p))
    assert dp["status"] == "provisional"
    assert any("OQ-1" in a for a in dp["assumptions"])
    assert cr["aspects"]["status"] == "provisional"
    assert any("OQ-1" in a for a in cr["aspects"]["assumptions"])

    # Missing owner/due must fail G0 (ADR-009)
    doc["open_questions"][0].pop("due")
    write_text(brd_yaml, yaml.safe_dump(doc, sort_keys=False))
    rep = Report(quiet=True, stream=io.StringIO())
    check_brd(ws.product("customer_orders"), rep, write_gaps=False)
    assert any("missing due" in m for m in rep.messages(Report.FAIL))

    # [NEEDS-DECISION] placeholder must fail G0
    doc["open_questions"] = []
    doc["residency"] = "[NEEDS-DECISION: residency]"
    write_text(brd_yaml, yaml.safe_dump(doc, sort_keys=False))
    rep2 = Report(quiet=True, stream=io.StringIO())
    check_brd(ws.product("customer_orders"), rep2, write_gaps=False)
    assert any("NEEDS-DECISION" in m for m in rep2.messages(Report.FAIL))


# ------------------------------------------------------------------ 5. proto promote schema validity (P0-10)
def test_proto_promote_snake_case_and_decoupled_emits_schema_valid_manifests(tmp_path: Path):
    ws = _make_twin(tmp_path)
    pdir = tmp_path / "products/retail_looker_poc"
    pdir.mkdir(parents=True)
    write_text(pdir / "product.yaml", yaml.safe_dump({
        "product_id": "retail_looker_poc",
        "version": "0.1.0",
        "status": "prototype",
        "owner": "analytics@example.com",
        "domain": "sales",
        "deployment": {"gcp_project": "p-dev", "region": "us-central1", "datasets": {"gold": "gold_rl"}},
        "upstream": [{"product": "sales_performance", "models": ["sales_performance_monthly"]}],
        "output_ports": [{"name": "p1", "model": "sales_performance_monthly", "type": "bigquery_view", "access": "dataset_grant"}],
    }, sort_keys=False))
    rc = main(["proto", "promote", "retail_looker_poc", "--quiet", "--root", str(tmp_path)])
    assert rc == 0
    promoted_man = load_yaml(pdir / "product.yaml")
    assert promoted_man["brd_id"] == "BRD-RETAILLOOKERPOC-001"
    assert "schema_drift" in promoted_man["observability"]
    assert ws.validate(promoted_man, "product-manifest.v1") == []

    brd_path = tmp_path / "openspec/specs" / promoted_man["specs"]["brd"] / "brd.yaml"
    promoted_brd = load_yaml(brd_path)
    assert ws.validate(promoted_brd, "brd.v1") == []


# ------------------------------------------------------------------ 6. NULL-key quarantine & quality SQL (P0-7)
def test_null_key_quarantine_preserves_rows_and_evaluates_both_thresholds(tmp_path: Path):
    rej_sql = staging_view_sql("stg_orders", "rejects", ["order_id", "line_no"])
    assert "(_dpf_row_rank = 1 OR order_id IS NULL OR line_no IS NULL)" in rej_sql

    assert quality_condition({"type": "range", "column": "qty", "min": 0}) == "COALESCE(qty < 0, TRUE)"
    assert quality_condition({"type": "set_membership", "column": "st", "values": ["A", "O'B"]}) == \
        "COALESCE(st NOT IN ('A', 'O\\'B'), TRUE)"
    assert quality_condition({"type": "set_membership", "column": "st", "values": []}) == "TRUE"
    assert sql_escape_str("a\\b'c") == "a\\\\b\\'c"

    # Both max_reject_pct AND max_reject_rows must be checked together
    ws = _make_twin(tmp_path)
    mpath = tmp_path / "examples/sales_performance/product.yaml"
    man = load_yaml(mpath)
    man["quality"]["max_reject_pct"] = 1.0
    man["quality"]["max_reject_rows"] = 50
    write_text(mpath, yaml.safe_dump(man, sort_keys=False))
    b = build(ws.product("sales_performance"))
    rg = next(c for c in b.spec["cases"] if c["id"] == "reject_gate:stg_order_lines")
    assert "order_id IS NULL OR order_line_no IS NULL" in rg["sql"]
    assert "> 1.0" in rg["sql"] and "> 50" in rg["sql"]


# ------------------------------------------------------------------ 7. Orchestration payloads & LookML PII (P0-2, P0-8, P0-9)
def test_cloud_workflows_composer_compilation_step_and_lookml_time_pii_and_metrics(tmp_path: Path):
    ws = _make_twin(tmp_path)
    mpath = tmp_path / "examples/sales_performance/product.yaml"
    man = load_yaml(mpath)
    man["orchestration"]["engine"] = "cloud_workflows"
    # Add a filtered count metric and an average metric
    man["semantic_layer"]["metrics"].append({
        "name": "high_value_orders",
        "model": "fct_order_line",
        "type": "simple",
        "aggregation": "count",
        "filter": "net_amount > 100",
        "brd_requirement_id": ["R-1"],
    })
    man["semantic_layer"]["metrics"].append({
        "name": "avg_net_amount",
        "model": "fct_order_line",
        "type": "simple",
        "measure": "net_amount",
        "aggregation": "avg",
        "brd_requirement_id": ["R-1"],
    })
    write_text(mpath, yaml.safe_dump(man, sort_keys=False))
    p = ws.product("sales_performance")
    b = build(p)
    assert b.ok, b.problems

    orch_tf = b.files["terraform/orchestration.tf"]
    assert "/compilationResults" in orch_tf
    assert "compilationResult:" in orch_tf
    assert "poll_invocation:" in orch_tf
    assert '"Content-Type" = "application/json"' in orch_tf
    assert 'role    = "roles/workflows.invoker"' in orch_tf

    fct_lkml = b.files["semantic_layer/lookml/views/fct_order_line.view.lkml"]
    assert "CASE WHEN (net_amount > 100) THEN 1 ELSE 0 END" in fct_lkml
    assert "measure: avg_net_amount" in fct_lkml and "type: average" in fct_lkml

    # Composer 2-step Dataform operators
    man["orchestration"]["engine"] = "composer"
    write_text(mpath, yaml.safe_dump(man, sort_keys=False))
    b_comp = build(ws.product("sales_performance"))
    dag_py = b_comp.files["airflow/dags/sales_performance_dag.py"]
    assert "DataformCreateCompilationResultOperator" in dag_py
    assert "DataformCreateWorkflowInvocationOperator" in dag_py
    assert "compile_hourly >> run_hourly" in dag_py

    # BQML options quote escaping
    bqml = bqml_model_sql({"attributes": {"model_type": "LINEAR_REG", "options": {"note": "it's ok"}}}, "SELECT 1")
    assert "note='it\\'s ok'" in bqml


# ------------------------------------------------------------------ 8. G4 --env isolation, attest validation, SQL trailing ; (P0-5)
def test_g4_env_isolation_and_attest_validation(tmp_path: Path):
    ws = _make_twin(tmp_path)
    p = ws.product("sales_performance")
    assert not render_live_sql(p, build(p), "SELECT 1;\n").endswith(";")

    # Unknown --only must fail cleanly (exit 1, no empty evidence file)
    rep = Report(quiet=True, stream=io.StringIO())
    rc = run_tests(p, rep, live=False, only=["nonexistent:case"])
    assert rc == 1
    assert any("unknown test case" in m for m in rep.messages(Report.FAIL))

    # attest() with --env prod validates cleanly against test-evidence.v1
    rep_att = Report(quiet=True, stream=io.StringIO())
    rc_att = attest(p, rep_att, "AT-5", by="CFO", role="finance", environment="prod")
    assert rc_att == 0

    # Evidence recorded for 'test' MUST NOT satisfy G4 for 'production'
    b_prod = build(p)
    rep_test_att = Report(quiet=True, stream=io.StringIO())
    assert attest(p, rep_test_att, "AT-8", by="Merch", role="merchandising", environment="test") == 0
    cur_prod, _ = latest_results(p, b_prod.digest, environment="production")
    assert "acceptance:AT-5" in cur_prod
    assert "acceptance:AT-8" not in cur_prod


# ------------------------------------------------------------------ 9. dpf init scrubbing & clean-up.sh CI parity (P0-11)
def test_dpf_init_scrubs_bootstrap_state_and_hydrated_configs(tmp_path: Path):
    ws = _make_twin(tmp_path)
    # Simulate a previously bootstrapped source workspace with live tfstate + hydrated config
    tf_dir = tmp_path / "bootstrap/terraform"
    write_text(tf_dir / "terraform.tfstate", '{"secret": "live-state"}')
    write_text(tf_dir / "tf-output.json", '{"project_id": {"value": "secret-prod-123"}}')
    write_text(tmp_path / "registry/agent-config.json", json.dumps({"gcp_project_id": "secret-prod-123"}))

    target = tmp_path / "fresh_ws"
    rep = Report(quiet=True, stream=io.StringIO())
    assert dpf_init(ws, target, rep) == 0
    assert not (target / "bootstrap/terraform/terraform.tfstate").exists()
    assert not (target / "bootstrap/terraform/tf-output.json").exists()
    cfg = json.loads((target / "registry/agent-config.json").read_text(encoding="utf-8"))
    assert cfg["gcp_project_id"] == "{project_id}"


def test_cleanup_strip_examples_keeps_evidence_and_state_and_passes_ci(tmp_path: Path):
    _make_twin(tmp_path)
    write_text(tmp_path / "bootstrap/terraform/terraform.tfstate", '{"state": "keep"}')
    write_text(tmp_path / "evidence/my_prod/run-1.json", '{"keep": true}')

    res = subprocess.run(
        ["bash", str(tmp_path / "bootstrap/clean-up.sh"), "--strip-examples"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert not (tmp_path / "examples").exists()
    assert (tmp_path / "evidence/my_prod/run-1.json").exists()
    assert (tmp_path / "bootstrap/terraform/terraform.tfstate").exists()
    assert (tmp_path / "tests/evals/README.md").exists()
    assert (tmp_path / "tests/contracts/test_contracts.py").exists()

    # Clean customer workspace passes dpf check --all --gate G3 and dpf eval
    assert main(["check", "--all", "--gate", "G3", "--quiet", "--root", str(tmp_path)]) == 0
    assert main(["eval", "--quiet", "--root", str(tmp_path)]) == 0


# ------------------------------------------------------------------ 10. Looker deploy folder & cockpit security (P0-9)
def test_looker_resolve_folder_does_not_fallback_to_shared_for_custom_folder():
    class FakeCli:
        def run_json(self, args):
            return True, [{"id": "1", "name": "Shared", "is_shared_root": True}], ""

    fid, err = _resolve_folder_id(FakeCli(), "Finance Restricted")
    assert fid is None and "not found" in err
    fid_shared, err_shared = _resolve_folder_id(FakeCli(), "Shared")
    assert fid_shared == "1" and err_shared == ""


def test_cockpit_html_escapes_html_comments_and_uses_headline_and_token():
    html = _render_cockpit_html(
        {"meta": {"note": "<!-- inject -->\u2028"}, "data": {}},
        targets={"net_sales": 1000.0},
        live_token="tok-123",
    )
    assert "<!-- inject -->" not in html
    assert '"tok-123"' in html
    assert "PAYLOAD.data.headline_summary" in html
    assert "X-DPF-Token" in html
