"""Machine-readable product documents: the contracts the build emits besides engine code.

data-product.v1, catalog-registration.v1 (Knowledge Catalog entry, aspects, glossary
bindings, lineage), observability-policy.v1, quality-policy.v1, one semantic-model.v1 /
staging-model.v1 / raw-table.v1 per relation, the test specification and a README.
"""

from __future__ import annotations

import json

from dpf.core import Product, canonical, sha256
from dpf.design import stale_reasons
from dpf.graph import ProductGraph
from dpf.generate.plan import Action
from dpf.generate.render import kebab_id, timezone


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def semantics_signed(p: Product) -> bool:
    so = p.signoff
    return bool(so) and so.get("semantic_digest") == p.semantic_digest() and not [
        r for r in stale_reasons(p) if "sign" in r]


def grain_checksum(m: dict) -> str:
    return sha256(canonical({"model": m["name"], "grain_statement": m.get("grain_statement"),
                             "grain_columns": sorted(m.get("grain_columns") or [])}))


def table_ref(p: Product, g: ProductGraph, name: str) -> str:
    from dpf.generate.plan import relation_dataset
    dep = p.manifest.get("deployment") or {}
    ds = (dep.get("datasets") or {}).get(relation_dataset(p, g, name))
    return f"{dep.get('gcp_project')}.{ds}.{name}"


def _reqs(*els: dict) -> list[str]:
    out = sorted({r for e in els for r in (e or {}).get("brd_requirement_id") or []}, key=lambda x: int(x.split("-")[1]))
    return out


def glossary_bindings(p: Product, g: ProductGraph) -> dict[str, dict[str, str]]:
    terms = p.registry.glossary_terms
    index: dict[str, str] = {}
    for t in terms:
        index[t["id"]] = t["id"]
        for a in t.get("aliases") or []:
            index.setdefault(a.lower().replace(" ", "_"), t["id"])
    out: dict[str, dict[str, str]] = {}
    for n in g.models:
        if n.layer == "staging":
            continue
        cols = g.output_columns(n.name) or []
        hits = {c: index[c] for c in cols if c in index}
        if hits:
            out[n.name] = hits
    return out


def data_product(p: Product) -> dict:
    man = p.manifest
    obs = man.get("observability") or {}
    assumptions = [a if isinstance(a, str) else (a.get("text") or a.get("assumption") or json.dumps(a))
                   for a in p.brd.get("assumptions") or []]
    ports = []
    for pt in man.get("output_ports", []) or []:
        found = p.model(pt["model"])
        port = {"name": pt["name"], "type": pt["type"], "model": pt["model"], "access": pt["access"]}
        if found:
            port["grain_statement"] = found[1].get("grain_statement")
        port["consumers"] = list(pt.get("consumers") or [])
        port["brd_requirement_id"] = list(pt.get("brd_requirement_id") or [])
        ports.append(port)
    fresh = []
    for ob in obs.get("freshness", []) or []:
        cal = ob.get("calendar")
        fresh.append(f"{ob['id']} {ob['model']} within {ob['max_staleness']}"
                     + (f" ({','.join(cal['days'])} {cal['start']}-{cal['end']} {cal['timezone']})" if cal else ""))
    slo = {"freshness": "; ".join(fresh) or "not declared",
           "availability": f"{(obs.get('slo') or {}).get('objective', 'n/a')} over {(obs.get('slo') or {}).get('window', 'n/a')}",
           "quality": f"gate {((man.get('quality') or {}).get('gate_behaviour') or 'block')}: blocking checks stop publication"}
    consumers = sorted({c for pt in man.get("output_ports", []) or [] for c in pt.get("consumers") or []})
    return {
        "product_id": p.id, "version": str(man.get("version")), "brd_id": man.get("brd_id"), "tdd_id": man.get("tdd_id"),
        "semantics_signed": semantics_signed(p),
        "status": "provisional" if assumptions else man.get("status", "draft"),
        "owner": man.get("owner"), "domain": man.get("domain"), "output_ports": ports, "slo": slo,
        "classification": man.get("classification"), "consumers": consumers, "assumptions": assumptions,
        "brd_requirement_id": p.requirement_ids,
    }


def catalog_registration(p: Product, g: ProductGraph) -> dict:
    man = p.manifest
    dep = man.get("deployment") or {}
    ds = dep.get("datasets") or {}
    obs = man.get("observability") or {}
    bindings = glossary_bindings(p, g)
    edges = sorted({f"{i} -> {n.name}" for n in g.models for i in n.inputs})
    scans = [f"projects/{dep.get('gcp_project')}/locations/{dep.get('region')}/dataScans/{kebab_id('dpf', p.id, m)}"
             for m in (obs.get("quality_scans") or {}).get("models", []) or []]
    grain = {}
    for pt in man.get("output_ports", []) or []:
        found = p.model(pt["model"])
        if found:
            grain[pt["name"]] = {"statement": found[1].get("grain_statement"), "columns": found[1].get("grain_columns")}
    cadence = "; ".join(f"{s['id']}: {s['cron']} ({timezone(p)})" for s in (man.get("orchestration") or {}).get("schedules", []) or [])
    root = p.ws.root
    return {
        "entry_ref": f"bigquery.googleapis.com/projects/{dep.get('gcp_project')}/datasets/{ds.get('gold')}",
        "aspects": {
            "owner": man.get("owner"), "domain": man.get("domain"), "classification": man.get("classification"),
            "service_levels": {"freshness": obs.get("freshness") or [], "slo": obs.get("slo") or {}},
            "grain": grain, "refresh_cadence": cadence or "on demand",
            "status": "provisional" if p.brd.get("assumptions") else man.get("status", "draft"),
            "assumptions": [str(a) for a in p.brd.get("assumptions") or []],
            "glossary_bindings": bindings,
            "data_product": {"product_id": p.id, "version": str(man.get("version")), "brd": man.get("satisfies")},
        },
        "glossary_terms": sorted({t for cols in bindings.values() for t in cols.values()}),
        "steward": man.get("steward"),
        "lineage_edges": edges,
        "quality_scan_ref": ", ".join(scans) or None,
        "brd_link": str((p.brd_dir / "spec.md").relative_to(root)),
        "tdd_link": str((p.tdd_dir / "spec.md").relative_to(root)),
        "semantics_link": str(p.semantics_path.relative_to(root)),
        "registered_via": (man.get("governance") or {}).get("registered_via", "knowledge-catalog-mcp"),
        "brd_requirement_id": p.requirement_ids,
    }


def observability_policy(p: Product) -> dict:
    return {"product_id": p.id, "policy": p.manifest.get("observability") or {}}


def quality_policy(p: Product, g: ProductGraph) -> dict:
    man = p.manifest
    rules = [dict(r) for r in (man.get("quality") or {}).get("rules", []) or []]
    for n in g.models:
        rules.append({"id": f"GR-{n.name}", "model": n.name, "type": "unique",
                      "columns": list(n.model.get("grain_columns") or []), "severity": "block",
                      "on_fail": "fail", "implements": "test-data-product"})
    out = {"product_id": p.id, "rules": rules, "gate_behaviour": (man.get("quality") or {}).get("gate_behaviour", "block")}
    qs = (man.get("observability") or {}).get("quality_scans")
    if qs:
        out["scan_schedule"] = qs.get("schedule")
    return out


def semantic_model(p: Product, g: ProductGraph, name: str) -> dict:
    n = g.nodes[name]
    m = n.model
    lay = p.layer_cfg(n.layer)
    doc = {
        "model_ref": table_ref(p, g, name), "layer": n.layer, "methodology": n.pack, "role": n.role,
        "grain_statement": m.get("grain_statement"), "grain_columns": list(m.get("grain_columns") or []),
        "grain_checksum": grain_checksum(m), "engine": n.engine, "storage_format": lay.get("storage", "bigquery_native"),
        "materialisation": m.get("materialisation", "view"), "history_semantics": m.get("history_semantics"),
        "dataset": m.get("dataset") or n.layer, "inputs": list(n.inputs),
    }
    for k in ("natural_key", "surrogate_key", "partition_by", "cluster_by", "attributes", "brd_requirement_id", "implements"):
        if m.get(k) is not None:
            doc[k] = m[k]
    return doc


def staging_model(p: Product, g: ProductGraph, name: str) -> dict:
    n = g.nodes[name]
    m = n.model
    rules = g.quarantine_rules(name)
    doc = {
        "table_ref": table_ref(p, g, name), "engine": n.engine, "natural_key": list(m.get("natural_key") or []),
        "grain_columns": list(m.get("grain_columns") or []),
        "dedupe_strategy": f"latest version per natural key by {', '.join(m.get('dedupe_order') or [])}",
        "reject_table_ref": table_ref(p, g, f"{name}_rejects") if rules else None,
        "reject_rules": [r["id"] for r in rules],
        "quality_gate": (p.manifest.get("quality") or {}).get("gate_behaviour", "block"),
    }
    if m.get("brd_requirement_id"):
        doc["brd_requirement_id"] = m["brd_requirement_id"]
    return doc


def raw_table(p: Product, g: ProductGraph, name: str) -> dict:
    n = g.nodes[name]
    src = next((s for s in p.manifest.get("sources", []) or [] if s["system_id"] == n.source), {})
    lineage = (p.registry.defaults.get("naming") or {}).get("lineage_columns") or ["_ingest_ts", "_batch_id"]
    doc = {
        "table_ref": table_ref(p, g, name), "is_append_only": True,
        "storage_format": (p.layer_cfg("raw") or {}).get("storage", "bigquery_native"),
        "partition_spec": "DATE(_ingest_ts)", "cluster_spec": ["_source_pk_hash"], "lineage_columns": list(lineage),
        "op_semantics": "cdc_ops" if src.get("capture_mode") == "cdc" else "insert_only",
    }
    if src.get("brd_requirement_id"):
        doc["brd_requirement_id"] = src["brd_requirement_id"]
    return doc


def readme(p: Product, engine: str, actions: list[Action], files: list[str], digest: str) -> str:
    man = p.manifest
    count = lambda kind: sum(1 for a in actions if a.kind == kind)  # noqa: E731
    eng_dir = "dataform/" if engine == "dataform" else "dbt/"
    lines = [
        f"# {p.id} — generated build", "",
        f"Generated by `dpf generate` from `products/{p.id}/product.yaml` ({man.get('satisfies')}, {man.get('tdd_id')}). "
        "Do not edit: change the manifest, the authored SQL bodies or the generators, then regenerate. "
        "`MANIFEST.json` lists every file with its hash and the build digest that test evidence is bound to.", "",
        "| Path | What it is |", "|---|---|",
        f"| `{eng_dir}` | {engine} project: {count('declaration')} raw declarations, "
        f"{sum(1 for a in actions if a.kind not in ('declaration', 'assertion'))} models and helper views, "
        f"{count('assertion')} assertions |",
        "| `terraform/` | Datasets, access, policy tags and masking, sharing, orchestration, checks, alerts, "
        "Knowledge Catalog quality scans, control tables |",
        "| `semantic/`, `staging/`, `raw/` | One contract document per relation |",
        "| `test-spec.json` | Every check the product must pass (test-spec.v1) |",
        "| `data-product.json`, `catalog-registration.json` | Product descriptor and Knowledge Catalog registration |",
        "| `observability-policy.json`, `quality-policy.json` | Runtime service levels and quality rules |",
        "| `dag.json`, `dag.md` | The composed pipeline: skills per stage and typed edges |", "",
        "## Deploy", "",
        "1. `terraform apply` the `terraform/` module from a wrapper that configures the `google` and `google-beta` "
        "providers (see `examples/<product>/terraform`). Apply it before the first extract: it creates the control tables.",
    ]
    if engine == "dataform":
        lines.append("2. Push `dataform/` to the default branch of the Dataform repository named in "
                     "`dataform_repository`. The release configuration compiles it hourly; one workflow configuration per "
                     "schedule runs the actions tagged with that schedule.")
    else:
        lines.append("2. Run the schedules in `dbt/orchestration.md` with `dbt build` (policy tag vars from "
                     "`terraform output policy_tags`).")
    lines += ["3. Load the fixture, build, then `dpf test run --live` to record evidence against this build digest.", "",
              f"Build digest: `{digest}`", ""]
    return "\n".join(lines)
