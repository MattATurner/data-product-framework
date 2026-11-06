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
from dpf.graph import ProductGraph, strip_sql_comments
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
        signed_digest = so.get("playback_digest") or so.get("semantic_digest")
        if signed_digest != p.semantic_digest():
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


def check_prototype(p: Product, report: Report) -> None:
    """Fast structural and SQL check for status: prototype products (--gate proto)."""
    report.head(f"proto · prototype structural check — {p.id}", gate="proto")
    ws, man = p.ws, p.manifest
    errs = ws.validate(man, "product-manifest.v1")
    report.check(not errs, "product.yaml conforms to product-manifest.v1",
                 f"product.yaml does not conform: {'; '.join(errs[:6])}")
    if errs:
        return
    g = ProductGraph(p)
    for prob in g.problems:
        report.fail(prob)
    if g.cycle:
        report.fail(f"model dependency cycle: {' -> '.join(g.cycle)}")
    for model, ref in g.unresolved_inputs():
        report.fail(f"{model} reads '{ref}', which is not declared")
    _roles(p, g, report)
    _ports(p, g, report)
    _upstream(p, g, report)
    _semantic_layer(p, g, report)
    _references(p, g, report)
    _staging(p, g, report)
    _operability(p, g, report)
    if g.models:
        run_rules(p, report, g)
    if not report.failures:
        from dpf.generate import build
        b = build(p)
        for prob in b.problems:
            report.fail(prob)
        if b.ok:
            report.ok(f"in-memory build succeeded ({len(b.files)} artefacts)")


def check_design(p: Product, report: Report) -> None:
    report.head(f"G1 · design resolves the BRD — {p.id}", gate="G1")
    ws, man = p.ws, p.manifest

    if p.is_prototype:
        report.fail(f"{p.id} has status: prototype; use `dpf check {p.id} --gate proto` or promote with `dpf proto promote {p.id}` before G1")
        return

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
    _upstream(p, g, report)
    _semantic_layer(p, g, report)
    _references(p, g, report)
    _brd_derivations(p, g, report)
    _agf_governance(p, g, report)
    _methodology(p, g, report)
    _history(p, g, report)
    _capture(p, report)
    _staging(p, g, report)
    _operability(p, g, report)
    _envy(p, g, report)
    if g.models:
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
            if node is None or node.kind not in ("model", "upstream"):
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
    gold_without = [n.name for n in g.models if n.layer == "gold" and n.role != "ml_model"
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
        mat = n.model.get("materialisation")
        if n.layer == "gold" and not mat:
            report.fail(f"{n.name}: consumption models must declare a materialisation")
        elif n.role == "ml_model" and mat != "bqml_model":
            report.fail(f"{n.name}: role 'ml_model' requires materialisation 'bqml_model', not '{mat}'")
        elif n.role != "ml_model" and mat == "bqml_model":
            report.fail(f"{n.name}: materialisation 'bqml_model' is only valid for role 'ml_model', not '{n.role}'")


def _ports(p: Product, g: ProductGraph, report: Report) -> None:
    datasets_used: dict[str, list[str]] = {}
    for n in g.models:
        datasets_used.setdefault(n.model.get("dataset") or n.layer, []).append(n.name)
    sl = p.manifest.get("semantic_layer") or {}
    known_explores = {e["name"] for e in (sl.get("explores") or [])}
    known_dashboards = {d["name"] for d in (sl.get("dashboards") or [])}
    for port in p.manifest.get("output_ports", []) or []:
        name = port.get("name")
        ptype = port.get("type")
        access = port.get("access")
        if ptype == "looker_explore":
            exp_name = port.get("explore")
            if exp_name not in known_explores:
                report.fail(f"port {name}: explore '{exp_name}' is not declared in semantic_layer.explores")
            if access != "looker_model_set":
                report.fail(f"port {name}: looker_explore ports must use access 'looker_model_set', not '{access}'")
            continue
        if ptype == "looker_dashboard":
            dash_name = port.get("dashboard")
            if dash_name not in known_dashboards:
                report.fail(f"port {name}: dashboard '{dash_name}' is not declared in semantic_layer.dashboards")
            if access not in ("looker_folder_grant", "looker_model_set"):
                report.fail(
                    f"port {name}: looker_dashboard ports must use access 'looker_folder_grant' or 'looker_model_set', "
                    f"not '{access}'"
                )
            continue
        if access in ("looker_model_set", "looker_folder_grant"):
            report.fail(f"port {name}: access '{access}' is only valid on looker_explore or looker_dashboard ports")
        node = g.get(port.get("model", ""))
        if node is None or node.kind != "model":
            report.fail(f"port {name}: model '{port.get('model')}' is not declared")
            continue
        if node.layer != "gold":
            report.fail(f"port {name}: exposes {node.name} from the {node.layer} layer; ports expose consumption models")
        mat = node.model.get("materialisation") or "view"
        allowed = PORT_MATERIALISATION.get(port["type"], set())
        if allowed and mat not in allowed:
            report.fail(f"port {name}: type {port['type']} does not fit materialisation '{mat}' of {node.name}")
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


def _semver_tuple(ver: str | None) -> tuple[int, int, int]:
    if not ver:
        return (0, 0, 0)
    parts = str(ver).split("-", 1)[0].split("+")[0].split(".")
    nums = [int(x) if x.isdigit() else 0 for x in (parts + ["0", "0", "0"])[:3]]
    return (nums[0], nums[1], nums[2])


def _upstream(p: Product, g: ProductGraph, report: Report) -> None:
    upstreams = p.manifest.get("upstream") or []
    if not upstreams:
        return
    from dpf.generate.render import duration_minutes

    down_fresh = {
        ob.get("model"): ob for ob in ((p.manifest.get("observability") or {}).get("freshness") or [])
    }
    for u in upstreams:
        if u.get("product"):
            up_id = u["product"]
            up_path = p.ws.root / "products" / up_id / "product.yaml"
            if not up_path.exists():
                continue
            up_prod = p.ws.product(up_id)
            min_v = u.get("min_version")
            act_v = str(up_prod.manifest.get("version") or "0.0.0")
            if min_v and _semver_tuple(act_v) < _semver_tuple(min_v):
                report.fail(
                    f"upstream product '{up_id}' is at version {act_v}, below required min_version {min_v}"
                )
            else:
                report.ok(f"upstream product '{up_id}' ({act_v}) satisfies binding")
            up_obs = {
                ob.get("model"): ob.get("max_staleness")
                for ob in ((up_prod.manifest.get("observability") or {}).get("freshness") or [])
            }
            default_up_stale = u.get("max_staleness") or next(iter(up_obs.values()), None)
            for mname in u.get("models") or []:
                up_iso = up_obs.get(mname) or default_up_stale
                dob = down_fresh.get(mname)
                if up_iso and dob and dob.get("max_staleness"):
                    if duration_minutes(dob["max_staleness"]) < duration_minutes(up_iso):
                        report.fail(
                            f"{dob['id']}: downstream freshness {dob['max_staleness']} on '{mname}' is tighter "
                            f"than upstream '{up_id}' guarantees ({up_iso})"
                        )
        else:
            fid = u.get("foundation") or "unknown"
            reg_f = p.registry.foundations.get(fid) or {}
            up_iso = u.get("max_staleness") or reg_f.get("max_staleness")
            tables = u.get("tables") if u.get("tables") is not None else (reg_f.get("tables") or [])
            for t in tables:
                tname = t["name"]
                dob = down_fresh.get(tname)
                if up_iso and dob and dob.get("max_staleness"):
                    if duration_minutes(dob["max_staleness"]) < duration_minutes(up_iso):
                        report.fail(
                            f"{dob['id']}: downstream freshness {dob['max_staleness']} on '{tname}' is tighter "
                            f"than upstream foundation '{fid}' guarantees ({up_iso})"
                        )
                if t.get("columns"):
                    known_cols = {c["name"] for c in t["columns"]}
                    missing_g = [c for c in (t.get("grain_columns") or []) if c not in known_cols]
                    if missing_g:
                        report.fail(
                            f"upstream foundation '{fid}' table '{tname}': grain column(s) {', '.join(missing_g)} "
                            "are not in declared columns"
                        )
                    if t.get("surrogate_key") and t["surrogate_key"] not in known_cols:
                        report.fail(
                            f"upstream foundation '{fid}' table '{tname}': surrogate_key '{t['surrogate_key']}' "
                            "is not in declared columns"
                        )


def _semantic_layer(p: Product, g: ProductGraph, report: Report) -> None:
    sl = p.manifest.get("semantic_layer")
    if not sl:
        return
    from dpf.generate.lookml import explore_field_map
    from dpf.generate.semantic_layer import build_semantic_spec

    looker_cfg = sl.get("looker") or {}
    if looker_cfg.get("allow_pdt"):
        sem_adrs = [
            a for a in (p.manifest.get("adrs") or [])
            if a != "ADR-018" and a in p.ws.adrs and front_matter(p.ws.adrs[a])[0].get("decides") == "semantic_layer"
        ]
        report.check(
            bool(sem_adrs),
            f"Looker PDT exception is backed by ADR ({', '.join(sem_adrs)})",
            "semantic_layer.looker.allow_pdt: true requires a product ADR deciding semantic_layer beyond ADR-018",
        )

    measure_additivity: dict[tuple[str, str], str] = {}
    sem_names = {n.name for n in g.semantic_nodes}
    for n in g.semantic_nodes:
        for ms in ((n.model.get("attributes") or {}).get("measures") or []):
            measure_additivity[(n.name, ms["name"])] = ms.get("additivity", "additive")

    for mt in sl.get("metrics") or []:
        mmodel = mt.get("model")
        if mmodel not in sem_names:
            report.fail(f"metric '{mt['name']}': model '{mmodel}' is not a consumption, silver or upstream model")
            continue
        src_col = mt.get("expr") or mt.get("measure") or mt.get("name")
        if mt.get("type", "simple") == "simple" and measure_additivity.get((mmodel, src_col)) == "non_additive":
            report.fail(
                f"metric '{mt['name']}': cannot aggregate non_additive measure '{src_col}' on {mmodel} as type "
                "'simple' (sum); use type 'derived' or 'ratio'"
            )

    spec = build_semantic_spec(p, g, "sha256:" + "0" * 64) or {}
    cubes_by_name = {c["name"]: c for c in spec.get("cubes") or []}
    explores_by_name = {e["name"]: e for e in (sl.get("explores") or [])}
    field_ref_re = re.compile(r"\$\{([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\}")

    for exp in sl.get("explores") or []:
        ename = exp["name"]
        base_name = exp.get("from")
        if base_name not in cubes_by_name:
            report.fail(f"explore '{ename}': base model '{base_name}' is not a declared semantic model")
            continue
        reach = explore_field_map(exp, cubes_by_name)
        joins = exp.get("joins")
        if isinstance(joins, list):
            for j in joins:
                jview = j.get("view")
                if jview not in cubes_by_name:
                    report.fail(f"explore '{ename}': joined view '{jview}' is not a declared semantic model")
                    continue
                jnode = g.get(jview)
                if jnode:
                    is_scd2 = (
                        int((jnode.model.get("attributes") or {}).get("scd_type", 1) or 1) == 2
                        or jnode.model.get("history_semantics") == "scd2"
                    )
                    sk = jnode.model.get("surrogate_key")
                    nks = list(jnode.model.get("natural_key") or [])
                    sql_on = j.get("sql_on") or ""
                    if is_scd2 and sk and f".{sk}" not in sql_on and any(f".{nk}" in sql_on for nk in nks):
                        report.fail(
                            f"explore '{ename}' join '{jview}': joins SCD2 dimension on natural key instead of "
                            f"surrogate key '{sk}' (causes fanout across historical versions)"
                        )
                    for vr, fr in field_ref_re.findall(sql_on):
                        if vr != "TABLE" and f"{vr}.{fr}" not in reach:
                            report.fail(
                                f"explore '{ename}' join '{jview}': unresolved field '${{{vr}.{fr}}}' in sql_on"
                            )
        for agg in exp.get("aggregate_tables") or []:
            if isinstance(agg, str) and agg not in cubes_by_name:
                report.fail(f"explore '{ename}': aggregate_table '{agg}' is not a declared semantic model")

    for dash in sl.get("dashboards") or []:
        dname = dash["name"]
        if dash.get("file"):
            fpath = p.dir / dash["file"]
            if not fpath.exists():
                report.fail(f"dashboard '{dname}': LookML file '{dash['file']}' does not exist under products/{p.id}/")
            continue
        dexp = dash.get("explore")
        if dexp and dexp not in explores_by_name:
            report.fail(f"dashboard '{dname}': explore '{dexp}' is not declared in semantic_layer.explores")
            continue
        base_reach = explore_field_map(explores_by_name[dexp], cubes_by_name) if dexp else {}
        for flt in dash.get("filters") or []:
            if base_reach and flt["field"] not in base_reach:
                report.fail(
                    f"dashboard '{dname}' filter '{flt['name']}': field '{flt['field']}' does not exist in explore '{dexp}'"
                )
        for tile in dash.get("tiles") or []:
            tid, tkind = tile.get("name") or tile.get("id"), tile["kind"]
            if tkind in ("pie", "donut"):
                report.fail(f"dashboard '{dname}' tile '{tid}': chart kind '{tkind}' violates Stephen Few visual rules")
                continue
            if tkind in ("ranked_bar", "column") and tile.get("y_axis_zero") is False:
                report.fail(
                    f"dashboard '{dname}' tile '{tid}': bar and column charts must anchor Y-axis at zero (y_axis_zero: true)"
                )
            if tkind == "markdown":
                continue
            texp_name = tile.get("explore") or dexp
            if not texp_name or texp_name not in explores_by_name:
                report.fail(f"dashboard '{dname}' tile '{tid}': unknown explore '{texp_name}'")
                continue
            treach = explore_field_map(explores_by_name[texp_name], cubes_by_name)
            for df in tile.get("dimensions") or []:
                if df not in treach:
                    report.fail(
                        f"dashboard '{dname}' tile '{tid}': dimension '{df}' does not exist in explore '{texp_name}'"
                    )
                elif treach[df] != "dimension":
                    report.fail(f"dashboard '{dname}' tile '{tid}': '{df}' is a {treach[df]}, not a dimension")
            for mf in tile.get("measures") or []:
                if mf not in treach:
                    report.fail(
                        f"dashboard '{dname}' tile '{tid}': measure '{mf}' does not exist in explore '{texp_name}'"
                    )
                elif treach[mf] != "measure":
                    report.fail(f"dashboard '{dname}' tile '{tid}': '{mf}' is a {treach[mf]}, not a measure")
                else:
                    vp, fp = mf.split(".", 1)
                    if measure_additivity.get((vp, fp)) == "non_additive":
                        report.fail(
                            f"dashboard '{dname}' tile '{tid}': references raw non_additive measure '{mf}' directly; "
                            "define a derived or ratio metric instead"
                        )


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
    has_upstream_tags = any(n.model.get("_policy_tags") for n in g.upstream_nodes)
    if prot.get("restricted_attributes"):
        report.check(bool(tags or has_upstream_tags), "restricted attributes are protected by policy tags",
                     f"BRD restricts {', '.join(prot['restricted_attributes'])} but no policy tag is declared")
    if prot.get("who_may_access"):
        has_looker_grants = not g.models and any(
            pt.get("access") in ("looker_model_set", "looker_folder_grant") for pt in ports
        )
        report.check(bool((man.get("governance") or {}).get("access")) or has_looker_grants,
                     "access grants are declared",
                     "BRD names who may access the data but governance.access is empty")
    on_bad = ((brd.get("fitness") or {}).get("on_bad_data") or "").lower()
    if "stop" in on_bad or "not publish" in on_bad:
        q = man.get("quality") or {}
        blocking = [r for r in q.get("rules", []) or [] if r.get("severity") == "block"]
        report.check(q.get("gate_behaviour") == "block" and bool(blocking),
                     "bad data stops publication (blocking quality gate)",
                     "BRD says bad data must stop publication but the quality gate does not block")
        if q.get("max_reject_pct") or q.get("max_reject_rows"):
            report.warn("BRD says bad data must stop publication, but quality declares a non-zero reject threshold "
                        f"(max_reject_pct={q.get('max_reject_pct')}, max_reject_rows={q.get('max_reject_rows')}) "
                        "that allows rejected rows through without stopping publication")
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


def _agf_governance(p: Product, g: ProductGraph, report: Report) -> None:
    """ADR-019 — compile-time AGF (ADG-00) sensitivity, sharing-port leak, CDE and residency checks."""
    gov = p.manifest.get("governance") or {}
    agf = gov.get("agf")
    if not agf or agf.get("enabled") is False:
        return
    dep = p.manifest.get("deployment") or {}
    allowed_regions = agf.get("allowed_regions") or []
    if allowed_regions:
        reg = dep.get("region")
        if reg and reg not in allowed_regions:
            report.fail(f"AGF C10: deployment.region '{reg}' is outside governance.agf.allowed_regions "
                        f"({', '.join(allowed_regions)})")
        for env_name, env_cfg in (dep.get("environments") or {}).items():
            ereg = (env_cfg or {}).get("region")
            if ereg and ereg not in allowed_regions:
                report.fail(f"AGF C10: deployment.environments.{env_name}.region '{ereg}' is outside "
                            f"governance.agf.allowed_regions ({', '.join(allowed_regions)})")

    terms = p.registry.glossary_terms
    known_term_ids = {t["id"] for t in terms}
    if agf.get("cde_terms") and known_term_ids:
        bad_cde = [c for c in agf["cde_terms"] if c not in known_term_ids]
        if bad_cde:
            report.fail(f"AGF DC-2: unknown cde_terms {', '.join(bad_cde)} (not in registry glossary)")

    restricted_term_cols: set[str] = set()
    for t in terms:
        if str(t.get("classification") or "").lower() == "restricted":
            restricted_term_cols.add(t["id"])
            for a in t.get("aliases") or []:
                restricted_term_cols.add(a.lower().replace(" ", "_"))

    tagged_cols: set[tuple[str, str]] = {
        (t["model"], c) for t in (gov.get("policy_tags") or []) for c in (t.get("columns") or [])
    }
    for un in g.upstream_nodes:
        for c in un.model.get("_policy_tags") or []:
            tagged_cols.add((un.name, c))

    semantic_names = {n.name for n in g.semantic_nodes}
    restricted_cols: set[tuple[str, str]] = set()
    for ref, tier in sorted((agf.get("classified_columns") or {}).items()):
        if "." not in ref:
            report.fail(f"AGF C6: classified_columns key '{ref}' must be '<model>.<column>'")
            continue
        mname, cname = ref.split(".", 1)
        node = g.get(mname)
        if node is None:
            report.fail(f"AGF C6: classified_columns references undeclared model '{mname}'")
            continue
        cols = g.output_columns(mname)
        if cols is not None and cname not in cols:
            report.fail(f"AGF C6: {mname} does not produce classified column '{cname}'")
            continue
        if tier == "RESTRICTED":
            restricted_cols.add((mname, cname))

    for n in g.semantic_nodes:
        for c in g.output_columns(n.name) or []:
            if c in restricted_term_cols:
                restricted_cols.add((n.name, c))

    untagged = sorted((m, c) for (m, c) in restricted_cols if m in semantic_names and (m, c) not in tagged_cols)
    if untagged:
        report.fail("AGF C6: restricted column(s) "
                    + ", ".join(f"{m}.{c}" for m, c in untagged)
                    + " must be protected by governance.policy_tags")

    def _ancestors(start: str) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            nd = g.get(cur)
            if nd:
                stack.extend(nd.inputs)
        return seen

    for port in p.manifest.get("output_ports") or []:
        if port.get("access") != "sharing_listing" or not port.get("model"):
            continue
        pm = port["model"]
        pcols = set(g.output_columns(pm) or [])
        anc = _ancestors(pm)
        anc_restricted_names = {c for (m, c) in restricted_cols if m in anc} | restricted_term_cols
        leaked = sorted(pcols & anc_restricted_names)
        if leaked:
            report.fail(f"AGF C6: external sharing_listing port '{port['name']}' exposes restricted column(s) "
                        f"{', '.join(leaked)} on {pm}")
    if not report.failures:
        report.ok("AGF (ADG-00) governance contract checks passed")


def _methodology(p: Product, g: ProductGraph, report: Report) -> None:
    if not g.models:
        report.ok("decoupled semantic product: methodology is inherited from upstream bindings")
        return
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
        models = [n for n in (*g.upstream_nodes, *g.models)
                  if n.layer != "staging" and rids & set(n.model.get("brd_requirement_id") or [])]
        current = [n.name for n in models if n.model.get("history_semantics") == "current_only"]
        pit = [n.name for n in models if n.model.get("history_semantics") in ("point_in_time", "full_history", "scd2")]
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
DATAFORM_JS = re.compile(r"\$\{\s*(?:ref|self|when)\s*\(|\bdataform\.projectConfig\b")


def _blank_literals_and_parens(sql: str) -> str:
    """Strip SQL comments, string literals and parenthesised subqueries, leaving depth-0 SQL."""
    text = strip_sql_comments(sql)
    out: list[str] = []
    depth, i, n = 0, 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"', "`"):
            j = i + 1
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if text[j] == c:
                    break
                j += 1
            if depth == 0:
                out.append(" '' ")
            i = j + 1
            continue
        if c == "(":
            depth += 1
            if depth == 1:
                out.append(" () ")
        elif c == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(c)
        i += 1
    return "".join(out)


def _strip_literals(sql: str) -> str:
    text = strip_sql_comments(sql)
    return re.sub(r"'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\"", "''", text)


def _staging(p: Product, g: ProductGraph, report: Report) -> None:
    """Staging deduplicates on the source change time, never silently drops rows, and stays engine-neutral."""
    tdd_decisions = {d.meta.get("decision") for d in p.tdd_spec.requirements if d.meta.get("decision")}
    for n in g.models:
        raw_body = p.body(n.model) or ""
        if raw_body and DATAFORM_JS.search(_strip_literals(raw_body)):
            report.fail(f"{n.name}: body contains Dataform-specific '${{...}}' syntax; use engine-neutral "
                        "{{ ref('...') }} / {{ var('...') }} (or import with `dpf proto import-dataform`)")
        if n.layer != "staging":
            continue
        top = _blank_literals_and_parens(raw_body)
        if re.search(r"\b(QUALIFY|LIMIT)\b", top, re.I):
            report.fail(f"{n.name}: top-level QUALIFY or LIMIT in a staging body bypasses dpf deduplication and "
                        "quarantine; declare natural_key and dedupe_order in product.yaml instead")
        where_m = re.search(r"\bWHERE\b(.*)$", top, re.I | re.S)
        if where_m and not re.match(r"^\s*TRUE\s*;?\s*$", where_m.group(1), re.I):
            from dpf.generate.render import parse_markers
            allow = next((mk for mk in parse_markers(raw_body)
                          if str(mk.get("allow_staging_filter", "")).lower() in ("true", "1", "yes")), None)
            if allow is None:
                report.fail(f"{n.name}: top-level WHERE in a staging body silently drops rows before quarantine; "
                            "move row validation to quality.rules (on_fail: quarantine), or mark an intentional "
                            "source-scope filter with '-- dpf: allow_staging_filter=true decision=D-n'")
            elif p.is_prototype:
                report.warn(f"{n.name}: staging body uses an allowed top-level WHERE filter; convert row validation "
                            "to quality.rules (on_fail: quarantine) or bind decision=D-n before G1")
            elif allow.get("decision") not in tdd_decisions:
                report.fail(f"{n.name}: '-- dpf: allow_staging_filter=true' must cite a valid TDD decision=D-n at G1 "
                            f"(got decision={allow.get('decision')!r})")
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
    signed_digest = so.get("playback_digest") or so.get("semantic_digest")
    report.check(signed_digest == digest, f"signature matches current semantics ({digest[:19]}…)",
                 "signature is invalid: semantics.md / playback.md or a model's grain/history changed since sign-off")
    report.check(so.get("brd") == _brd_ref(p), f"signed against {_brd_ref(p)}",
                 f"signed against {so.get('brd')}, the BRD is now {_brd_ref(p)}")
    missing = sorted(set(p.scenario_ids) - set(so.get("covers") or []), key=_idnum)
    report.check(not missing, f"signature covers all {len(p.scenario_ids)} acceptance scenarios",
                 f"signature does not cover {', '.join(missing)}")


# ----------------------------------------------------------------- commands
def write_signoff(p: Product, by: str, role: str, when: str | None = None, note: str | None = None,
                  links: list[str] | None = None) -> dict:
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
    if (p.tdd_dir / "playback.md").exists():
        so["playback_digest"] = p.playback_digest()
    if note:
        so["note"] = note
    if links:
        so["links"] = list(links)
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
