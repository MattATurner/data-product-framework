"""G1 — the TDD resolves the BRD (`dpf check --gate G1`, `dpf tdd ...`, `dpf signoff`).

Checks that the manifest is a faithful, complete and justified resolution of the BRD:
schema-valid, bound to the current BRD version, every requirement realised and every design
element justified, decisions in the TDD matching the manifest, methodology departures backed
by an ADR, history semantics honouring the business answers, ports, protection and capture
consistent with the BRD and the registry, design rules passing, and the business signature
bound to the current semantics.
"""

from __future__ import annotations

import re
from datetime import date

from dpf.core import LAYERS, Product, Report, front_matter, iter_elements, write_text
from dpf.graph import ProductGraph
from dpf.methodology import history_point_in_time, recommend, run_rules
from dpf.specs import split_ids

PORT_MATERIALISATION = {
    "bigquery_view": {"view"},
    "bigquery_table": {"table", "incremental_table"},
    "materialized_view": {"materialized_view"},
    "bigquery_sharing_listing": {"table", "incremental_table", "view"},
}


def _brd_ref(p: Product) -> str:
    return f"{p.brd.get('brd_id')}@{p.brd.get('version')}"


def stale_reasons(p: Product) -> list[str]:
    reasons = []
    current = _brd_ref(p)
    tdd_sat = p.tdd_spec.purpose_meta.get("satisfies")
    if tdd_sat != current:
        reasons.append(f"TDD satisfies {tdd_sat} but the BRD is now {current}")
    if p.manifest.get("satisfies") != current:
        reasons.append(f"product.yaml satisfies {p.manifest.get('satisfies')} but the BRD is now {current}")
    so = p.signoff
    if so is None:
        reasons.append("semantics are not signed (no signoff.yaml)")
    else:
        if so.get("semantic_digest") != p.semantic_digest():
            reasons.append("semantics changed since sign-off (semantic digest differs)")
        if so.get("brd") != current:
            reasons.append(f"sign-off was given against {so.get('brd')}, the BRD is now {current}")
        missing = sorted(set(p.scenario_ids) - set(so.get("covers") or []), key=_idnum)
        if missing:
            reasons.append(f"sign-off does not cover {', '.join(missing)}")
    return reasons


def _idnum(x: str) -> int:
    m = re.search(r"(\d+)$", x or "")
    return int(m.group(1)) if m else 0


def check_design(p: Product, report: Report) -> None:
    report.head(f"G1 · design resolves the BRD — {p.id}", gate="G1")
    ws, man = p.ws, p.manifest

    errs = ws.validate(man, "product-manifest.v1")
    report.check(not errs, "product.yaml conforms to product-manifest.v1",
                 f"product.yaml does not conform: {'; '.join(errs[:6])}")
    if errs:
        return
    if p.acceptance is not None:
        aerr = ws.validate(p.acceptance, "acceptance.v1")
        report.check(not aerr, "acceptance.yaml conforms to acceptance.v1",
                     f"acceptance.yaml does not conform: {'; '.join(aerr[:4])}")
    if not (p.tdd_dir / "spec.md").exists():
        report.fail(f"TDD spec missing: openspec/specs/{man['specs']['tdd']}/spec.md")
        return

    g = ProductGraph(p)
    for prob in g.problems:
        report.fail(prob)
    if g.cycle:
        report.fail(f"model dependency cycle: {' -> '.join(g.cycle)}")
    for model, ref in g.unresolved_inputs():
        report.fail(f"{model} reads '{ref}', which is not declared")

    _binding(p, report)
    _decisions(p, g, report)
    _elements(p, report)
    _roles(p, g, report)
    _ports(p, g, report)
    _references(p, g, report)
    _brd_derivations(p, g, report)
    _methodology(p, g, report)
    _history(p, g, report)
    _capture(p, report)
    _staging(p, g, report)
    _operability(p, g, report)
    _envy(p, g, report)
    report.head(f"G1 · design rules — {p.id}")
    run_rules(p, report, g)
    report.head(f"G1 · semantics sign-off — {p.id}")
    _signoff(p, report)


# ----------------------------------------------------------------- sections
def _binding(p: Product, report: Report) -> None:
    meta, man = p.tdd_spec.purpose_meta, p.manifest
    current = _brd_ref(p)
    report.check(meta.get("tdd") == man.get("tdd_id"), f"TDD id {man.get('tdd_id')} matches the manifest",
                 f"TDD spec says {meta.get('tdd')!r}, product.yaml says {man.get('tdd_id')!r}")
    report.check(meta.get("satisfies") == current, f"TDD is current with {current}",
                 f"TDD is stale: it satisfies {meta.get('satisfies')} but the BRD is {current}")
    report.check(man.get("satisfies") == current, f"manifest is current with {current}",
                 f"manifest is stale: it satisfies {man.get('satisfies')} but the BRD is {current}")
    report.check(man.get("brd_id") == p.brd.get("brd_id"), "manifest names the right BRD",
                 f"manifest brd_id {man.get('brd_id')!r} differs from {p.brd.get('brd_id')!r}")


def _decisions(p: Product, g: ProductGraph, report: Report) -> None:
    reqs = set(p.requirement_ids)
    decided: set[str] = set()
    seen: set[str] = set()
    for d in p.tdd_spec.requirements:
        did = d.meta.get("decision")
        if not did:
            report.fail(f"TDD requirement '{d.name}' has no '**Decision:** D-n' line")
            continue
        if did in seen:
            report.fail(f"decision {did} is used twice")
        seen.add(did)
        sat = d.ids("satisfies")
        if not sat:
            report.fail(f"{did} '{d.name}' cites no BRD requirement")
        bad = [r for r in sat if r not in reqs]
        if bad:
            report.fail(f"{did} cites unknown requirement(s) {', '.join(bad)}")
        decided.update(r for r in sat if r in reqs)
        if not d.normative:
            report.fail(f"{did} '{d.name}' has no SHALL statement")
        if not d.scenarios:
            report.fail(f"{did} '{d.name}' has no scenario")

        model = d.meta.get("model")
        if model:
            node = g.get(model)
            if node is None or node.kind != "model":
                report.fail(f"{did} describes model '{model}', which the manifest does not declare")
            else:
                if d.meta.get("grain"):
                    tdd_grain = split_ids(d.meta["grain"])
                    man_grain = node.model.get("grain_columns") or []
                    report.check(sorted(tdd_grain) == sorted(man_grain), f"{did}: {model} grain matches the TDD",
                                 f"{did}: TDD grain ({', '.join(tdd_grain)}) differs from manifest grain "
                                 f"({', '.join(man_grain)}) for {model}")
                if sat and not set(sat) & set(node.model.get("brd_requirement_id") or []):
                    report.warn(f"{did}: {model} cites none of the requirements the decision satisfies")
        layer, meth = d.meta.get("layer"), d.meta.get("methodology")
        if layer and meth:
            actual = g.layer_pack(layer) if p.layer_cfg(layer).get("models") else None
            report.check(actual == meth, f"{did}: {layer} uses {meth}",
                         f"{did}: TDD says {layer} uses {meth}, manifest uses {actual}")
        for adr in split_ids(d.meta.get("adr")):
            if adr not in p.ws.adrs:
                report.fail(f"{did} cites {adr}, which has no ADR file")
            elif adr not in (p.manifest.get("adrs") or []):
                report.fail(f"{did} cites {adr}, which the manifest does not list in adrs")
    missing = sorted(reqs - decided, key=_idnum)
    report.check(not missing, f"every requirement is addressed by a TDD decision ({len(reqs)})",
                 f"requirement(s) with no TDD decision: {', '.join(missing)}")
    gold_without = [n.name for n in g.models if n.layer == "gold"
                    and not any(d.meta.get("model") == n.name and d.meta.get("grain") for d in p.tdd_spec.requirements)]
    report.check(not gold_without, "every consumption model's grain is decided in the TDD",
                 f"consumption model(s) with no grain decision in the TDD: {', '.join(gold_without)}")
    for adr in p.manifest.get("adrs") or []:
        if adr not in p.ws.adrs:
            report.fail(f"manifest lists {adr}, which has no ADR file")


def _elements(p: Product, report: Report) -> None:
    reqs = set(p.requirement_ids)
    caps = set(p.ws.platform_specs)
    realised: set[str] = set()
    orphans = []
    for ref, el in iter_elements(p.manifest):
        cites = el.get("brd_requirement_id") or []
        impl = el.get("implements")
        if not cites and not impl:
            orphans.append(ref)
        bad = [r for r in cites if r not in reqs]
        if bad:
            report.fail(f"{ref} cites unknown requirement(s) {', '.join(bad)}")
        if impl and impl not in caps:
            report.fail(f"{ref} implements '{impl}', which is not a platform capability spec")
        realised.update(r for r in cites if r in reqs)
    report.check(not orphans, "every design element is justified by a requirement or a platform capability",
                 f"orphan design element(s) with no requirement or capability: {', '.join(orphans)}")
    unrealised = sorted(reqs - realised, key=_idnum)
    report.check(not unrealised, "every requirement is realised by at least one design element",
                 f"requirement(s) not realised by any design element: {', '.join(unrealised)}")


def _roles(p: Product, g: ProductGraph, report: Report) -> None:
    for n in g.models:
        if n.layer == "staging":
            if n.role != "staging":
                report.fail(f"{n.name}: staging models use the platform role 'staging', not '{n.role}'")
            if not n.model.get("natural_key") or not n.model.get("dedupe_order"):
                report.fail(f"{n.name}: staging models must declare natural_key and dedupe_order")
            continue
        pack = p.ws.packs.get(n.pack)
        if pack is None:
            report.fail(f"{n.name}: layer {n.layer} uses unknown methodology pack '{n.pack}'")
            continue
        planned = {r["id"] for r in pack.get("planned_roles", []) or []}
        rdef = g.role_def(n.pack, n.role)
        if n.role in planned:
            report.fail(f"{n.name}: role '{n.role}' is planned in pack '{n.pack}', not implemented")
        elif rdef is None:
            report.fail(f"{n.name}: role '{n.role}' is not offered by pack '{n.pack}'")
        else:
            if n.layer not in rdef.get("layers", []):
                report.fail(f"{n.name}: role '{n.role}' is not allowed in the {n.layer} layer")
            missing = [a for a in rdef.get("required_attributes", []) or [] if a not in (n.model.get("attributes") or {})]
            if missing:
                report.fail(f"{n.name}: role '{n.role}' requires attributes {', '.join(missing)}")
        if n.layer == "gold" and not n.model.get("materialisation"):
            report.fail(f"{n.name}: consumption models must declare a materialisation")


def _ports(p: Product, g: ProductGraph, report: Report) -> None:
    datasets_used: dict[str, list[str]] = {}
    for n in g.models:
        datasets_used.setdefault(n.model.get("dataset") or n.layer, []).append(n.name)
    for port in p.manifest.get("output_ports", []) or []:
        node = g.get(port.get("model", ""))
        name = port.get("name")
        if node is None or node.kind != "model":
            report.fail(f"port {name}: model '{port.get('model')}' is not declared")
            continue
        if node.layer != "gold":
            report.fail(f"port {name}: exposes {node.name} from the {node.layer} layer; ports expose consumption models")
        mat = node.model.get("materialisation") or "view"
        allowed = PORT_MATERIALISATION.get(port["type"], set())
        if allowed and mat not in allowed:
            report.fail(f"port {name}: type {port['type']} does not fit materialisation '{mat}' of {node.name}")
        access = port.get("access")
        if access == "authorized_view" and mat != "view":
            report.fail(f"port {name}: authorized_view access needs a view, {node.name} is a {mat}")
        if access == "sharing_listing":
            if port["type"] != "bigquery_sharing_listing" or not port.get("sharing"):
                report.fail(f"port {name}: sharing_listing access needs type bigquery_sharing_listing and a sharing block")
            ds = node.model.get("dataset") or node.layer
            others = [m for m in datasets_used.get(ds, []) if m != node.name]
            if ds in LAYERS or others:
                report.fail(f"port {name}: a listed model needs its own sharing dataset (shares '{ds}' with {', '.join(others) or 'its layer'})")
        if port["type"] == "bigquery_sharing_listing" and access != "sharing_listing":
            report.fail(f"port {name}: a sharing listing port must use sharing_listing access")
    report.ok(f"{len(p.manifest.get('output_ports') or [])} output port(s) checked against their models")


def _references(p: Product, g: ProductGraph, report: Report) -> None:
    man = p.manifest
    ds = (man.get("deployment") or {}).get("datasets") or {}
    sched = {s["id"] for s in (man.get("orchestration") or {}).get("schedules", []) or []}
    if p.layer_cfg("silver").get("models") and "silver" not in ds:
        report.fail("silver models are declared but deployment.datasets has no 'silver' dataset")
    for n in g.models:
        key = n.model.get("dataset")
        if key and key not in ds:
            report.fail(f"{n.name}: dataset key '{key}' is not in deployment.datasets")
        if n.model.get("schedule") and n.model["schedule"] not in sched:
            report.fail(f"{n.name}: schedule '{n.model['schedule']}' is not an orchestration schedule")
        if n.model.get("partition_by"):
            cols = g.output_columns(n.name)
            if cols is not None and n.model["partition_by"] not in cols:
                report.fail(f"{n.name}: partition column '{n.model['partition_by']}' is not produced by the model")
    for r in (man.get("quality") or {}).get("rules", []) or []:
        node = g.get(r.get("model", ""))
        if node is None or node.kind != "model":
            report.fail(f"quality rule {r['id']}: model '{r.get('model')}' is not declared")
            continue
        if r.get("on_fail") == "quarantine" and node.layer != "staging":
            report.fail(f"quality rule {r['id']}: quarantine is implemented in staging; {node.name} is {node.layer}")
        cols = g.output_columns(node.name)
        for c in ([r["column"]] if r.get("column") else []) + list(r.get("columns") or []):
            if cols is not None and c not in cols:
                report.fail(f"quality rule {r['id']}: column '{c}' is not produced by {node.name}")
    obs = man.get("observability") or {}
    for kind in ("freshness", "volume"):
        for o in obs.get(kind, []) or []:
            if o.get("model") not in g.nodes:
                report.fail(f"{o['id']}: model '{o.get('model')}' is not declared")
            elif kind == "volume" and o.get("date_column"):
                cols = g.output_columns(o["model"])
                if cols is not None and o["date_column"] not in cols:
                    report.fail(f"{o['id']}: date column '{o['date_column']}' is not produced by {o['model']}")
    for m in (obs.get("quality_scans") or {}).get("models", []) or []:
        if m not in g.nodes:
            report.fail(f"quality scan model '{m}' is not declared")
    gov = man.get("governance") or {}
    for a in gov.get("access", []) or []:
        for key in a.get("datasets", []) or []:
            if key not in ds:
                report.fail(f"access grant {a['principal_var']}: dataset key '{key}' is not in deployment.datasets")
    for t in gov.get("policy_tags", []) or []:
        node = g.get(t.get("model", ""))
        if node is None:
            report.fail(f"{t['id']}: model '{t.get('model')}' is not declared")
            continue
        cols = g.output_columns(node.name)
        bad = [c for c in t["columns"] if cols is not None and c not in cols]
        if bad:
            report.fail(f"{t['id']}: {node.name} does not produce {', '.join(bad)}")
        else:
            report.ok(f"{t['id']}: {node.name} produces every tagged column")


def _brd_derivations(p: Product, g: ProductGraph, report: Report) -> None:
    brd, man = p.brd, p.manifest
    ports = man.get("output_ports") or []
    listing = [x for x in ports if x.get("access") == "sharing_listing"]
    ext = brd.get("external_readers") or {}
    if ext.get("required"):
        report.check(bool(listing), "external readers are served by a sharing listing",
                     "BRD requires external readers but no port uses sharing_listing access")
    elif listing:
        report.fail("a sharing listing port exists but the BRD has no external readers")
    prot = brd.get("protection") or {}
    tags = (man.get("governance") or {}).get("policy_tags") or []
    if prot.get("restricted_attributes"):
        report.check(bool(tags), "restricted attributes are protected by policy tags",
                     f"BRD restricts {', '.join(prot['restricted_attributes'])} but no policy tag is declared")
    if prot.get("who_may_access"):
        report.check(bool((man.get("governance") or {}).get("access")), "access grants are declared",
                     "BRD names who may access the data but governance.access is empty")
    on_bad = ((brd.get("fitness") or {}).get("on_bad_data") or "").lower()
    if "stop" in on_bad or "not publish" in on_bad:
        q = man.get("quality") or {}
        blocking = [r for r in q.get("rules", []) or [] if r.get("severity") == "block"]
        report.check(q.get("gate_behaviour") == "block" and bool(blocking),
                     "bad data stops publication (blocking quality gate)",
                     "BRD says bad data must stop publication but the quality gate does not block")
        unrouted = [r["id"] for r in blocking if r.get("on_fail") != "quarantine"]
        if unrouted:
            report.warn(f"blocking rule(s) {', '.join(unrouted)} fail the run without quarantining rows; "
                        "the business asked to see the unusable rows and the reason")
    for exc in brd.get("exceptions", []) or []:
        m = re.search(r"within (\d+) days", exc, re.I)
        if m:
            days = int(m.group(1))
            facts = [n for n in g.models if n.model.get("materialisation") == "incremental_table"]
            ok = any(int((n.model.get("attributes") or {}).get("restatement_window_days", -1)) == days for n in facts)
            report.check(ok, f"restatement window of {days} days is declared",
                         f"BRD restates corrections within {days} days but no incremental model declares "
                         f"restatement_window_days: {days}")


def _methodology(p: Product, g: ProductGraph, report: Report) -> None:
    layer = "silver" if p.layer_cfg("silver").get("models") else "gold"
    chosen = g.layer_pack(layer)
    default = ((p.registry.defaults.get("defaults") or {}).get("methodology") or {}).get(layer, "direct")
    rec, reasons = recommend(p)
    if chosen != default:
        adrs = [a for a in p.manifest.get("adrs") or [] if a in p.ws.adrs
                and front_matter(p.ws.adrs[a])[0].get("decides") == "methodology"]
        report.check(bool(adrs), f"departure from the '{default}' default is recorded ({', '.join(adrs)})",
                     f"{layer} uses '{chosen}' instead of the '{default}' default with no ADR deciding methodology")
    if chosen == rec:
        report.ok(f"{layer} methodology '{chosen}' matches the BRD signals"
                  + (f" ({'; '.join(reasons)})" if reasons else " (no shared definitions or history needs)"))
    elif rec == "kimball":
        report.warn(f"BRD signals recommend 'kimball' for {layer} but the design uses '{chosen}': {'; '.join(reasons)}")
    else:
        report.warn(f"no BRD signal needs '{chosen}' in {layer}; '{rec}' would be cheaper (a methodology is a cost paid for a benefit)")


def _history(p: Product, g: ProductGraph, report: Report) -> None:
    for hb in history_point_in_time(p.brd):
        rids = set(hb.get("satisfies") or [])
        models = [n for n in g.models if n.layer != "staging" and rids & set(n.model.get("brd_requirement_id") or [])]
        current = [n.name for n in models if n.model.get("history_semantics") == "current_only"]
        pit = [n.name for n in models if n.model.get("history_semantics") in ("point_in_time", "full_history")]
        if current:
            report.fail(f"{hb['id']} asks that {hb.get('attribute')} stay as it was, but {', '.join(current)} "
                        "declare current_only history")
        if not pit:
            report.fail(f"{hb['id']} asks that {hb.get('attribute')} stay as it was, but no model citing "
                        f"{', '.join(sorted(rids))} keeps point-in-time history")
        if pit and not current:
            report.ok(f"{hb['id']}: {hb.get('attribute')} keeps point-in-time history in {', '.join(pit)}")


def _capture(p: Product, report: Report) -> None:
    systems = p.registry.systems
    for s in p.manifest.get("sources", []) or []:
        sysd = systems.get(s["system_id"])
        if sysd is None:
            report.fail(f"source {s['system_id']} is not in the source-system registry")
            continue
        cap = sysd.get("capture") or {}
        supported = cap.get("supported_now") or []
        if s["capture_mode"] not in supported:
            needs = " (requires connectivity)" if s["capture_mode"] in (cap.get("requires_connectivity") or []) else ""
            report.fail(f"source {s['system_id']}: capture mode '{s['capture_mode']}' is not supported now{needs}; "
                        f"supported: {', '.join(supported) or 'none'}")
        else:
            report.ok(f"source {s['system_id']}: capture mode '{s['capture_mode']}' is supported")
        unknown = [e for e in s.get("entities", []) if e not in (sysd.get("entities") or [])]
        if unknown:
            report.fail(f"source {s['system_id']}: entities {', '.join(unknown)} are not held by the system")
        if sysd.get("engine") and sysd["engine"] != s["engine"]:
            report.fail(f"source {s['system_id']}: engine '{s['engine']}' differs from the registry ('{sysd['engine']}')")


ROW_LEVEL_RULES = {"not_null", "range", "set_membership", "custom_sql"}
FRESHNESS_MATERIALISED = {"table", "incremental_table", "materialized_view"}


def _staging(p: Product, g: ProductGraph, report: Report) -> None:
    """Staging deduplicates on the source change time, so both must be produced by the body."""
    for n in g.models:
        if n.layer != "staging":
            continue
        cols = g.output_columns(n.name)
        if cols is None:
            report.fail(f"{n.name}: cannot read the select list, so the dedupe columns cannot be checked")
            continue
        order_cols = [x.split()[0] for x in n.model.get("dedupe_order") or []]
        missing = [c for c in [*(n.model.get("natural_key") or []), *order_cols] if c not in cols]
        if "source_modified_ts" not in cols:
            missing.append("source_modified_ts")
        if missing:
            report.fail(f"{n.name}: the body does not produce {', '.join(sorted(set(missing)))} "
                        "(natural key, dedupe order and source_modified_ts must be selected)")
        else:
            report.ok(f"{n.name}: deduplicates on ({', '.join(n.model['natural_key'])}) by {', '.join(order_cols)}")


def _operability(p: Product, g: ProductGraph, report: Report) -> None:
    for r in (p.manifest.get("quality") or {}).get("rules", []) or []:
        if r.get("on_fail") == "quarantine" and r.get("type") not in ROW_LEVEL_RULES:
            report.fail(f"quality rule {r['id']}: '{r.get('type')}' is a set-level rule and cannot quarantine rows; "
                        "use on_fail: fail_run, or a row-level rule")
    for o in (p.manifest.get("observability") or {}).get("freshness", []) or []:
        node = g.get(o.get("model", ""))
        if node is None or node.kind != "model":
            continue
        mat = node.model.get("materialisation") or "view"
        report.check(mat in FRESHNESS_MATERIALISED, f"{o['id']}: {node.name} is a {mat}, so its build time is observable",
                     f"{o['id']}: {node.name} is a {mat}; a view's modified time does not move when data refreshes, "
                     "so freshness must target a table, incremental table or materialized view")


def _envy(p: Product, g: ProductGraph, report: Report) -> None:
    if any(g.layer_pack(layer) == "kimball" for layer in ("silver", "gold") if p.layer_cfg(layer).get("models")):
        return
    envy = [n.name for n in g.models if re.match(r"^(dim|fct|fact)_", n.name)
            or re.search(r"\bvalid_from\b|\bsurrogate\b|FARM_FINGERPRINT", p.body(n.model) or "", re.I)]
    report.check(not envy, "no hand-rolled dimensional structures in a direct product",
                 f"methodology-envy: {', '.join(envy)} hand-roll dimensional structures; adopt the kimball pack instead")


def _signoff(p: Product, report: Report) -> None:
    so = p.signoff
    if so is None:
        report.fail("semantics are not signed: run `dpf signoff` once the business owner has accepted semantics.md")
        return
    errs = p.ws.validate(so, "signoff.v1")
    report.check(not errs, "signoff.yaml conforms to signoff.v1", f"signoff.yaml invalid: {'; '.join(errs[:3])}")
    digest = p.semantic_digest()
    report.check(so.get("semantic_digest") == digest, f"signature matches current semantics ({digest[:19]}…)",
                 "signature is invalid: semantics.md or a model's grain/history changed since sign-off")
    report.check(so.get("brd") == _brd_ref(p), f"signed against {_brd_ref(p)}",
                 f"signed against {so.get('brd')}, the BRD is now {_brd_ref(p)}")
    missing = sorted(set(p.scenario_ids) - set(so.get("covers") or []), key=_idnum)
    report.check(not missing, f"signature covers all {len(p.scenario_ids)} acceptance scenarios",
                 f"signature does not cover {', '.join(missing)}")


# ----------------------------------------------------------------- commands
def write_signoff(p: Product, by: str, role: str, when: str | None = None, note: str | None = None) -> dict:
    so = {
        "product_id": p.id,
        "signed_by": by,
        "role": role,
        "date": when or date.today().isoformat(),
        "brd": _brd_ref(p),
        "tdd": p.manifest.get("tdd_id"),
        "covers": sorted(p.scenario_ids, key=_idnum),
        "semantic_digest": p.semantic_digest(),
    }
    if note:
        so["note"] = note
    import yaml
    header = ("# Business signature on semantics.md (contract signoff.v1), written by `dpf signoff`.\n"
              "# Bound to the semantic digest: editing semantics.md or any model's grain or history\n"
              "# declaration invalidates it until it is signed again.\n")
    write_text(p.tdd_dir / "signoff.yaml", header + yaml.safe_dump(so, sort_keys=False, allow_unicode=True))
    return so


def resolution_report(p: Product) -> str:
    """Derivations from the BRD answers, printed by `dpf tdd resolve` to guide TDD authoring."""
    brd = p.brd
    rec, reasons = recommend(p)
    lines = [f"# Resolution guide — {brd.get('brd_id')} → {p.manifest.get('tdd_id', 'TDD')}", "",
             "How each business answer drives a design decision (registry/brd-rubric.yaml derivations).", "",
             "| BRD answer | Value | Derives |", "|---|---|---|"]
    for d in p.registry.rubric.get("derivations", []) or []:
        src = d["from"]
        key = src.split("[")[0].split(".")[0]
        val = brd.get(key)
        if isinstance(val, dict):
            sub = src.split(".", 1)[1] if "." in src else None
            val = val.get(sub) if sub else val
        if isinstance(val, list):
            val = "; ".join(v.get("answer") or v.get("must_agree_on") or str(v) if isinstance(v, dict) else str(v)
                            for v in val)
        elif isinstance(val, dict):
            val = ", ".join(f"{k}: {v}" for k, v in val.items() if k != "satisfies")
        lines.append(f"| `{src}` | {str(val or '—').replace('|', '/')} | {d['derives']} |")
    lines += ["", f"**Methodology recommendation:** `{rec}`", ""]
    lines += [f"- {r}" for r in reasons] or ["- No shared definitions with other teams and no point-in-time history: the `direct` default suffices."]
    stale = stale_reasons(p) if (p.tdd_dir / "spec.md").exists() else []
    if stale:
        lines += ["", "**Stale:**", ""] + [f"- {s}" for s in stale]
    return "\n".join(lines) + "\n"
