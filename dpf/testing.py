"""Test plane (`dpf test plan|run|attest`) and the G4 evidence gate.

Automated cases run as SQL against a deployed build (`--live`) and are recorded as
test-evidence.v1 bound to the build digest; static cases are evaluated by inspecting the
manifest and the generated artefacts; attestations are recorded human confirmations. G4
passes only when every case has passing evidence for the *current* build digest: change an
input, regenerate, and the old evidence is stale.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from dpf.core import Product, Report, write_json
from dpf.generate import Build, build
from dpf.generate.plan import relation_dataset
from dpf.generate.render import dts_schedule, duration_minutes, project_vars, sub_refs, sub_vars
from dpf.graph import select_columns


# ----------------------------------------------------------------- static checks
def _element(case: dict) -> tuple[str, str]:
    kind, _, name = (case.get("element") or ":").partition(":")
    return kind, name


def _action(b: Build, name: str):
    return next((a for a in b.actions if a.name == name), None)


def _file(b: Build, suffix: str) -> str:
    return next((c for path, c in b.files.items() if path.endswith(suffix)), "")


def _engine(b: Build) -> str:
    return "dbt" if any(p.startswith("dbt/") for p in b.files) else "dataform"


def _resource(tf: str, rtype: str, name: str) -> str | None:
    m = re.search(rf'^resource "{rtype}" "{re.escape(name)}" \{{\n(.*?)^\}}', tf, re.M | re.S)
    return m.group(1) if m else None


def check_restatement_window(b: Build, case: dict) -> list[str]:
    _, model = _element(case)
    found = b.product.model(model)
    if not found:
        return [f"{model} is not declared"]
    window = (found[1].get("attributes") or {}).get("restatement_window_days")
    if not window:
        return [f"{model} declares no restatement_window_days"]
    a = _action(b, model)
    probs = []
    if a is None or a.kind != "incremental":
        return [f"{model} is not rendered as an incremental table"]
    needle = f"INTERVAL {int(window)} DAY"
    if needle not in (a.incremental_predicate or ""):
        probs.append(f"{model}: incremental predicate does not limit rewrites to {window} days")
    if _engine(b) == "dataform":
        text = _file(b, f"/{model}.sqlx")
        if "updatePartitionFilter" not in text or needle not in text.split("updatePartitionFilter", 1)[1].split("\n")[0]:
            probs.append(f"{model}: updatePartitionFilter does not bound the merge to {window} days")
        if "when(incremental()" not in text:
            probs.append(f"{model}: source rows are not filtered on incremental runs")
    else:
        text = _file(b, f"models/silver/{model}.sql") or _file(b, f"/{model}.sql")
        if "incremental_predicates" not in text or "is_incremental()" not in text:
            probs.append(f"{model}: dbt incremental predicates or is_incremental() filter missing")
    return probs


def check_freshness_policy(b: Build, case: dict) -> list[str]:
    _, ob_id = _element(case)
    obs = (b.product.manifest.get("observability") or {}).get("freshness", []) or []
    ob = next((o for o in obs if o["id"] == ob_id), None)
    if ob is None:
        return [f"{ob_id} is not declared in observability.freshness"]
    tf = _file(b, "terraform/monitoring.tf")
    res = _resource(tf, "google_bigquery_data_transfer_config", f"freshness_{ob_id.lower().replace('-', '_')}")
    if res is None:
        return [f"no scheduled freshness check is generated for {ob_id}"]
    probs = []
    want = dts_schedule(ob.get("check_every") or "PT1H")
    if f'schedule             = "{want}"' not in res:
        probs.append(f"{ob_id}: check does not run {want}")
    if f"max_minutes={duration_minutes(ob['max_staleness'])}" not in res:
        probs.append(f"{ob_id}: threshold is not {ob['max_staleness']}")
    cal = ob.get("calendar")
    if cal and f"BETWEEN TIME '{cal['start']}:00' AND TIME '{cal['end']}:00'" not in res:
        probs.append(f"{ob_id}: business calendar {cal['start']}-{cal['end']} is not applied")
    if _resource(tf, "google_monitoring_alert_policy", "monitor_check_failed") is None:
        probs.append("no alert policy fires when a check fails")
    return probs


def check_reject_gate(b: Build, case: dict) -> list[str]:
    g = b.graph
    probs = []
    gated = [n for n in g.models if n.layer == "staging" and g.quarantine_rules(n.name)]
    if not gated:
        return ["no staging model quarantines rows, so nothing can block publication"]
    _, target = _element(case)
    gold = sorted({d for s in gated for d in g.downstream(s.name) if g.nodes[d].layer == "gold"} | {target})
    eng = _engine(b)
    for s in gated:
        gate = f"assert_{s.name}_no_rejects"
        a = _action(b, gate)
        if a is None or a.severity != "block":
            probs.append(f"{s.name}: no blocking reject gate ({gate})")
            continue
        if _action(b, f"{s.name}_rejects") is None:
            probs.append(f"{s.name}: rejected rows are not kept with their reason ({s.name}_rejects)")
        if "_reject_reason IS NULL" not in (_action(b, s.name).sql if _action(b, s.name) else ""):
            probs.append(f"{s.name}: the staging view does not exclude rejected rows")
        if eng == "dbt":
            if f"-- depends_on: {{{{ ref('{s.name}') }}}}" not in _file(b, f"tests/{gate}.sql"):
                probs.append(f"{gate}: dbt test is not attached to {s.name}, so dbt build would not skip downstream models")
        for model in gold:
            if s.name not in g.upstream(model):
                continue
            ga = _action(b, model)
            if eng == "dataform" and (ga is None or gate not in ga.dependencies):
                probs.append(f"{model} does not depend on {gate}: a rejected row would not block its refresh")
    return probs


def _exposed(b: Build, model: str) -> list[str] | None:
    return b.graph.output_columns(model)


def check_policy_tag_masking(b: Build, case: dict) -> list[str]:
    _, pt_id = _element(case)
    tags = (b.product.manifest.get("governance") or {}).get("policy_tags", []) or []
    t = next((x for x in tags if x["id"] == pt_id), None)
    if t is None:
        return [f"{pt_id} is not declared in governance.policy_tags"]
    probs = []
    tf = _file(b, "terraform/governance.tf")
    pid = pt_id.lower().replace("-", "_")
    dp = _resource(tf, "google_bigquery_datapolicy_data_policy", pid)
    want = {"always_null": "ALWAYS_NULL", "sha256": "SHA256", "default_masking_value": "DEFAULT_MASKING_VALUE"}[t["masking"]]
    if dp is None or want not in dp:
        probs.append(f"{pt_id}: no {want} data masking policy")
    for r in t.get("masked_readers") or []:
        if _resource(tf, "google_bigquery_datapolicy_data_policy_iam_member", f"{pid}_masked_{r}") is None:
            probs.append(f"{pt_id}: {r} is not a masked reader")
    for r in t.get("fine_grained_readers") or []:
        if _resource(tf, "google_data_catalog_policy_tag_iam_member", f"{t['tag']}_reader_{r}") is None:
            probs.append(f"{pt_id}: {r} cannot read unmasked values")
    a = _action(b, t["model"])
    for c in t["columns"]:
        if a is None or c not in a.columns:
            probs.append(f"{pt_id}: {t['model']}.{c} carries no policy tag")
    if _engine(b) == "dataform":
        if f"policy_tag_{t['tag']} = google_data_catalog_policy_tag.{t['tag']}.name" not in \
                re.sub(r"\s+=", " =", _file(b, "terraform/orchestration.tf")):
            probs.append(f"{pt_id}: the release configuration does not inject policy_tag_{t['tag']}")
    for n in b.graph.models:
        if n.layer != "gold":
            continue
        cols = _exposed(b, n.name)
        if cols is None:
            probs.append(f"{n.name}: cannot prove it hides {', '.join(t['columns'])} (select list not readable)")
        elif set(cols) & set(t["columns"]):
            probs.append(f"{n.name} exposes {', '.join(sorted(set(cols) & set(t['columns'])))}")
    return probs


def _identifying(b: Build) -> set[str]:
    out: set[str] = set()
    for n in b.graph.models:
        if n.role == "dimension":
            out |= set(n.model.get("natural_key") or []) | {n.model.get("surrogate_key")}
    for t in (b.product.manifest.get("governance") or {}).get("policy_tags", []) or []:
        out |= set(t["columns"])
    return {c for c in out if c}


def check_sharing_listing_only(b: Build, case: dict) -> list[str]:
    _, port_name = _element(case)
    port = next((pt for pt in b.product.manifest.get("output_ports", []) or [] if pt["name"] == port_name), None)
    if port is None or port.get("access") != "sharing_listing" or not port.get("sharing"):
        return [f"{port_name} is not a sharing-listing port"]
    sh = port["sharing"]
    tf = _file(b, "terraform/sharing.tf")
    probs = []
    if _resource(tf, "google_bigquery_analytics_hub_data_exchange", sh["exchange_id"]) is None:
        probs.append(f"exchange {sh['exchange_id']} is not generated")
    listing = _resource(tf, "google_bigquery_analytics_hub_listing", sh["listing_id"])
    if listing is None:
        probs.append(f"listing {sh['listing_id']} is not generated")
    elif "restrict_query_result = true" not in listing:
        probs.append(f"listing {sh['listing_id']} does not restrict export of query results")
    sv = sh.get("subscriber_var")
    if sv:
        if _resource(tf, "google_bigquery_analytics_hub_listing_iam_member", f"{sh['listing_id']}_subscriber") is None:
            probs.append("the partner is not granted subscriber on the listing")
        if f"var.{sv}" in _file(b, "terraform/access.tf"):
            probs.append(f"the partner ({sv}) is granted dataset access: it must receive the listing only")
    cols = _exposed(b, port["model"])
    if cols is None:
        probs.append(f"{port['model']}: cannot prove which columns are shared (select list not readable)")
    else:
        bad = sorted(set(cols) & _identifying(b))
        if bad:
            probs.append(f"{port['model']} shares identifying or restricted columns: {', '.join(bad)}")
    return probs


def check_current_state_only(b: Build, case: dict) -> list[str]:
    _, model = _element(case)
    g = b.graph
    probs = []
    for name in [model, *g.upstream(model)]:
        n = g.get(name)
        if n is None or n.kind != "model":
            continue
        if n.model.get("history_semantics") != "current_only":
            probs.append(f"{name} keeps history ({n.model.get('history_semantics')})")
        a = _action(b, name)
        if a and any(r.endswith("_history") for r in a.refs):
            probs.append(f"{name} reads a history view")
    return probs


def check_access_limited(b: Build, case: dict) -> list[str]:
    _, port_name = _element(case)
    man = b.product.manifest
    port = next((pt for pt in man.get("output_ports", []) or [] if pt["name"] == port_name), None)
    if port is None:
        return [f"{port_name} is not declared"]
    probs = []
    allowed = {a["principal_var"] for a in (man.get("governance") or {}).get("access", []) or []}
    access = _file(b, "terraform/access.tf")
    for v in re.findall(r"group_by_email = var\.([a-z0-9_]+)", access):
        if v not in allowed:
            probs.append(f"{v} is granted access but is not in governance.access")
    for bad in ("special_group", "allUsers", "allAuthenticatedUsers", "domain ", "iam_member"):
        if bad in access:
            probs.append(f"access.tf grants {bad.strip()}")
    if any(pt.get("access") == "sharing_listing" for pt in man.get("output_ports", []) or []):
        probs.append("the product publishes a sharing listing")
    if not access:
        probs.append("no dataset access is generated")
    return probs


STATIC_CHECKS = {
    "restatement_window": check_restatement_window,
    "freshness_policy": check_freshness_policy,
    "reject_gate_blocks_publication": check_reject_gate,
    "policy_tag_masking": check_policy_tag_masking,
    "sharing_listing_only": check_sharing_listing_only,
    "current_state_only": check_current_state_only,
    "access_limited": check_access_limited,
}


def run_static(b: Build) -> dict[str, list[str]]:
    out = {}
    for case in b.spec.get("cases", []):
        if case["method"] == "static":
            fn = STATIC_CHECKS.get(case.get("check"))
            out[case["id"]] = fn(b, case) if fn else [f"unknown static check '{case.get('check')}'"]
    return out


# ----------------------------------------------------------------- evidence
def load_evidence(p: Product) -> list[dict]:
    out = []
    for f in sorted(p.evidence_dir.glob("*.json")) if p.evidence_dir.exists() else []:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        doc["_file"] = f.name
        out.append(doc)
    return out


def latest_results(p: Product, digest: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """(current, stale): latest result per test id for this digest, and for other digests."""
    current: dict[str, dict] = {}
    stale: dict[str, dict] = {}
    for doc in sorted(load_evidence(p), key=lambda d: d.get("recorded_at", "")):
        if p.ws.validate({k: v for k, v in doc.items() if not k.startswith("_")}, "test-evidence.v1"):
            continue
        target = current if doc.get("artefact_digest") == digest else stale
        for r in doc.get("results", []):
            target[r["test_id"]] = {**r, "recorded_at": doc.get("recorded_at"), "file": doc["_file"]}
    return current, stale


def case_status(case: dict, current: dict, stale: dict, static: dict[str, list[str]]) -> str:
    if case["method"] == "static":
        return "passed" if not static.get(case["id"]) else "failed"
    r = current.get(case["id"])
    if r:
        return r["status"]
    return "stale" if case["id"] in stale else "missing"


def check_evidence(p: Product, report: Report, b: Build | None = None) -> None:
    report.head(f"G4 · evidence — {p.id}", gate="G4")
    b = b or build(p)
    if not b.ok:
        report.fail("the build does not generate; evidence cannot be evaluated")
        return
    static = run_static(b)
    current, stale = latest_results(p, b.digest)
    counts: dict[str, int] = {}
    for case in b.spec["cases"]:
        st = case_status(case, current, stale, static)
        counts[st] = counts.get(st, 0) + 1
        label = f"{case['id']} ({case['method']})"
        if st == "passed":
            report.ok(f"{label} passed")
        elif case["severity"] == "warn" and st not in ("missing", "stale"):
            report.warn(f"{label} {st} (warn-level)")  # it ran on this build and failed
        elif case["method"] == "static":
            report.fail(f"{label} failed: {'; '.join(static[case['id']])}")
        elif st == "stale":
            report.fail(f"{label}: evidence is for an older build digest; re-run against the current build")
        elif st == "missing":
            how = (f"`dpf test attest {p.id} {case['id'].split(':', 1)[1]} --by <name> --role {case.get('attested_by_role')}`"
                   if case["method"] == "attestation" else f"`dpf test run {p.id} --live`")
            report.fail(f"{label}: no evidence for build {b.digest[:19]}… ({how})")
        else:
            report.fail(f"{label} {st}" + (f" ({current[case['id']].get('failing_rows')} failing rows)"
                                            if case["id"] in current else ""))
    report.info("evidence: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))


# ----------------------------------------------------------------- commands
def plan_table(b: Build) -> str:
    lines = [f"Test specification — {b.product.id} ({len(b.spec['cases'])} cases, build {b.digest[:19]}…)", "",
             f"{'case':58} {'method':11} {'sev':5} satisfies / verifies"]
    for c in b.spec["cases"]:
        lines.append(f"{c['id']:58} {c['method']:11} {c['severity']:5} "
                     f"{','.join(c.get('satisfies') or []) or '-'}"
                     + (f" / {','.join(c['verifies'])}" if c.get("verifies") else ""))
    return "\n".join(lines)


def render_live_sql(p: Product, b: Build, sql: str) -> str:
    dep = p.manifest.get("deployment") or {}
    ds = dep.get("datasets") or {}
    vals = project_vars(p)
    out = sub_refs(sql, lambda n: f"`{dep.get('gcp_project')}.{ds.get(relation_dataset(p, b.graph, n))}.{n}`")
    return sub_vars(out, lambda v: vals.get(v, ""))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_tests(p: Product, report: Report, live: bool = False, environment: str = "test",
              only: list[str] | None = None) -> int:
    b = build(p)
    report.head(f"test run — {p.id}", gate="G4")
    if not b.ok:
        for prob in b.problems:
            report.fail(prob)
        return 1
    static = run_static(b)
    results = []
    for case in b.spec["cases"]:
        if only and case["id"] not in only:
            continue
        if case["method"] == "static":
            probs = static[case["id"]]
            report.check(not probs, f"{case['id']} passed", f"{case['id']} failed: {'; '.join(probs)}")
            results.append({"test_id": case["id"], "status": "failed" if probs else "passed",
                            "note": "; ".join(probs) or "static check passed", "finished_at": now_iso()})
    if not live:
        report.info("static checks only; add --live to run the automated SQL cases against the deployed build")
        return 1 if report.failures else 0
    try:
        from google.cloud import bigquery  # type: ignore
    except ImportError:
        report.fail("--live needs google-cloud-bigquery (pip install google-cloud-bigquery)")
        return 1
    client = bigquery.Client(project=(p.manifest.get("deployment") or {}).get("gcp_project"))
    for case in b.spec["cases"]:
        if case["method"] != "automated" or (only and case["id"] not in only):
            continue
        sql = render_live_sql(p, b, case["sql"])
        try:
            rows = list(client.query(f"SELECT COUNT(*) AS n FROM (\n{sql}\n)").result())
            n = int(rows[0]["n"])
            status = "passed" if n == 0 else "failed"
            results.append({"test_id": case["id"], "status": status, "failing_rows": n, "finished_at": now_iso()})
            (report.ok if n == 0 else report.warn if case["severity"] == "warn" else report.fail)(
                f"{case['id']}: {n} failing row(s)")
        except Exception as exc:  # noqa: BLE001 - recorded as a failed result
            results.append({"test_id": case["id"], "status": "failed", "note": str(exc)[:500], "finished_at": now_iso()})
            report.fail(f"{case['id']}: {exc}")
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    doc = {"product_id": p.id, "artefact_digest": b.digest, "run_id": run_id, "environment": environment,
           "recorded_at": now_iso(), "results": results}
    errs = p.ws.validate(doc, "test-evidence.v1")
    if errs:
        report.fail(f"evidence does not conform to test-evidence.v1: {errs[0]}")
        return 1
    write_json(p.evidence_dir / f"{run_id}.json", doc)
    report.info(f"recorded evidence/{p.id}/{run_id}.json")
    return 1 if report.failures else 0


def attest(p: Product, report: Report, test: str, by: str, role: str, note: str | None = None,
           environment: str = "test") -> int:
    b = build(p)
    report.head(f"attest — {p.id} {test}", gate="G4")
    case_id = test if test.startswith("acceptance:") else f"acceptance:{test}"
    case = next((c for c in b.spec.get("cases", []) if c["id"] == case_id), None)
    if case is None or case["method"] != "attestation":
        report.fail(f"{test} is not an attestation in products/{p.id}/acceptance.yaml")
        return 1
    if role != case.get("attested_by_role"):
        report.fail(f"{test} must be attested by role '{case.get('attested_by_role')}', not '{role}'")
        return 1
    run_id = datetime.now(timezone.utc).strftime(f"attest-{test.split(':')[-1]}-%Y%m%dT%H%M%SZ")
    doc = {"product_id": p.id, "artefact_digest": b.digest, "run_id": run_id, "environment": environment,
           "recorded_at": now_iso(),
           "results": [{"test_id": case_id, "status": "passed", "attested_by": f"{by} ({role})",
                        "note": note or case["description"], "finished_at": now_iso()}]}
    write_json(p.evidence_dir / f"{run_id}.json", doc)
    report.ok(f"recorded attestation of {test} by {by} ({role}) for build {b.digest[:19]}…")
    return 0


def select_list(sql: str | None) -> list[str] | None:
    return select_columns(sql)
