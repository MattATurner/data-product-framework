"""Versioned BI Semantic Layer generator (semantic-layer.v1): Cube, MetricFlow, AtScale, OSI, and LookML."""

from __future__ import annotations

import yaml

from dpf.core import Product
from dpf.graph import ProductGraph
from dpf.generate import lookml
from dpf.generate.docs import dumps, table_ref
from dpf.generate.render import is_timestamp, marker

MEASURE_TYPE = {
    "additive": "sum",
    "semi_additive": "avg",
    "non_additive": "number",
}


def _is_time_col(col: str, m: dict | None = None) -> bool:
    if m:
        if col == m.get("partition_by") or col == (m.get("attributes") or {}).get("event_date"):
            return True
    return is_timestamp(col) or col.endswith("_date") or col == "calendar_date"


def _bq_to_sem_type(col: str, bq_type: str | None, m: dict | None = None) -> str:
    if bq_type:
        u = bq_type.upper()
        if u in ("DATE", "DATETIME", "TIMESTAMP"):
            return "time"
        if u in ("BOOL", "BOOLEAN"):
            return "boolean"
        if u in ("INT64", "INTEGER", "FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC"):
            return "number"
    if _is_time_col(col, m):
        return "time"
    if col.startswith("is_") or col.startswith("has_"):
        return "boolean"
    return "string"


def _glossary_index(p: Product) -> dict[str, str]:
    idx: dict[str, str] = {}
    for t in p.registry.glossary_terms:
        defn = (t.get("definition") or "").strip()
        if not defn:
            continue
        idx[t["id"]] = defn
        for alias in t.get("aliases") or []:
            idx.setdefault(alias.lower().replace(" ", "_"), defn)
    return idx


def build_semantic_spec(p: Product, g: ProductGraph, digest: str, targets_override: list[str] | None = None) -> dict | None:
    man = p.manifest
    sl_cfg = man.get("semantic_layer") or {}
    targets = list(targets_override or sl_cfg.get("targets") or [])
    if not targets:
        return None

    glossary = _glossary_index(p)
    local_pts = (man.get("governance") or {}).get("policy_tags") or []
    cubes: list[dict] = []
    metrics: list[dict] = []
    explicit_metrics = list(sl_cfg.get("metrics") or [])

    for n in g.semantic_nodes:
        name = n.name
        m = n.model
        attrs = m.get("attributes") or {}
        grain = list(m.get("grain_columns") or [])
        sk = m.get("surrogate_key")
        tref = table_ref(p, g, name)
        col_meta = {c["name"]: c for c in (m.get("columns") or []) if isinstance(c, dict) and c.get("name")}
        dims: list[dict] = []
        seen_dims: set[str] = set()
        measures: list[dict] = []
        joins: list[dict] = []

        def add_dim(col: str, dtype: str | None = None, pk: bool = False, hidden: bool = False) -> None:
            if not col or col in seen_dims:
                return
            seen_dims.add(col)
            cinfo = col_meta.get(col) or {}
            resolved_type = dtype or _bq_to_sem_type(col, cinfo.get("type"), m)
            d_obj: dict = {"name": col, "sql": col, "type": resolved_type}
            if pk:
                d_obj["primary_key"] = True
            if hidden:
                d_obj["hidden"] = True
            desc = cinfo.get("description") or glossary.get(col)
            if desc:
                d_obj["description"] = desc
            dims.append(d_obj)

        if sk:
            add_dim(sk, dtype="number", pk=True, hidden=True)
        for col in grain:
            add_dim(col, pk=(not sk and len(grain) == 1))

        if n.role == "dimension":
            for col in list(attrs.get("tracked") or []) + list(attrs.get("current") or []):
                add_dim(col)
            for col in col_meta:
                add_dim(col)
            if int(attrs.get("scd_type", 1) or 1) == 2 or m.get("history_semantics") == "scd2":
                add_dim("valid_from", dtype="time")
                add_dim("valid_to", dtype="time")
                add_dim("is_current", dtype="boolean")
                add_dim("version_no", dtype="number")
        elif n.role == "fact":
            for ref in list(attrs.get("dim_refs") or []):
                dim_node = g.get(ref.get("dimension") or "")
                if dim_node is None:
                    continue
                if dim_node.role == "calendar":
                    add_dim("date_key", dtype="number", hidden=True)
                    if ref.get("from"):
                        add_dim(ref["from"], dtype="time")
                    joins.append({
                        "to": dim_node.name,
                        "relationship": "many_to_one",
                        "on": f"{name}.date_key = {dim_node.name}.date_key",
                    })
                else:
                    d_sk = dim_node.model.get("surrogate_key")
                    if d_sk:
                        add_dim(d_sk, dtype="number", hidden=True)
                    if ref.get("natural_key"):
                        add_dim(ref["natural_key"])
                    join_key = d_sk or ref.get("natural_key")
                    joins.append({
                        "to": dim_node.name,
                        "relationship": "many_to_one",
                        "on": f"{name}.{join_key} = {dim_node.name}.{join_key}",
                    })
            ev_date = attrs.get("event_date")
            if ev_date:
                add_dim(ev_date, dtype="time")
            for col in list(attrs.get("degenerate") or []):
                add_dim(col)
            for f in list(attrs.get("flags") or []):
                if f.get("name"):
                    add_dim(f["name"], dtype="boolean")
            measure_names = {ms["name"] for ms in (attrs.get("measures") or [])}
            for col in col_meta:
                if col not in measure_names:
                    add_dim(col)
            for ms in list(attrs.get("measures") or []):
                mname = ms["name"]
                mtype = MEASURE_TYPE.get(ms.get("additivity", "additive"), "sum")
                desc = glossary.get(mname) or f"{mname} ({ms.get('additivity', 'additive')}) on {name}"
                measures.append({
                    "name": mname,
                    "sql": mname,
                    "type": mtype,
                    "additivity": ms.get("additivity", "additive"),
                    "description": desc,
                })
                if not any(em.get("name") == mname for em in explicit_metrics):
                    metrics.append({
                        "name": mname,
                        "label": mname.replace("_", " ").title(),
                        "type": "simple",
                        "model": name,
                        "measure": mname,
                        "time_grain": ["day", "week", "month", "quarter", "year"],
                    })
        else:
            out_cols = g.output_columns(name) or list(col_meta)
            attr_measures = {ms["name"]: ms for ms in (attrs.get("measures") or [])}
            for col in out_cols:
                if col not in attr_measures:
                    dtype = "number" if n.role == "calendar" and col in ("date_key", "year", "quarter", "month", "day_of_week") else None
                    add_dim(col, dtype=dtype)
            for mname, ms in attr_measures.items():
                mtype = MEASURE_TYPE.get(ms.get("additivity", "additive"), "sum")
                measures.append({
                    "name": mname,
                    "sql": mname,
                    "type": mtype,
                    "additivity": ms.get("additivity", "additive"),
                    "description": glossary.get(mname) or f"{mname} ({ms.get('additivity', 'additive')}) on {name}",
                })
            measures.append({
                "name": "row_count",
                "sql": grain[0] if grain else "*",
                "type": "count",
                "additivity": "additive",
                "description": f"Row count of {name} at declared grain",
            })

        pts = list(m.get("_policy_tags") or [pt for pt in local_pts if pt.get("model") == name])
        cube_obj: dict = {
            "name": name,
            "model": name,
            "table_ref": tref,
            "description": m.get("grain_statement") or name,
            "grain_columns": grain,
            "dimensions": dims,
            "measures": measures,
            "joins": joins,
        }
        if sk:
            cube_obj["surrogate_key"] = sk
        if m.get("partition_by"):
            cube_obj["partition_by"] = m["partition_by"]
        if m.get("history_semantics"):
            cube_obj["history_semantics"] = m["history_semantics"]
        elif n.role == "dimension" and int(attrs.get("scd_type", 1) or 1) == 2:
            cube_obj["history_semantics"] = "scd2"
        if pts:
            cube_obj["policy_tags"] = pts
        cubes.append(cube_obj)

    for em in explicit_metrics:
        em_copy = dict(em)
        if not em_copy.get("description") and em_copy.get("name") in glossary:
            em_copy["description"] = glossary[em_copy["name"]]
        metrics.append(em_copy)
        target_cube = next((c for c in cubes if c["model"] == em.get("model")), None)
        if target_cube:
            mname = em["name"]
            if not any(ms["name"] == mname for ms in target_cube["measures"]):
                target_cube["measures"].append({
                    "name": mname,
                    "sql": em.get("expr") or em.get("measure") or mname,
                    "type": "sum" if em.get("type", "simple") == "simple" else "number",
                    "additivity": "additive" if em.get("type", "simple") == "simple" else "non_additive",
                    "description": em_copy.get("description") or em.get("label") or mname,
                })

    spec: dict = {
        "product_id": p.id,
        "version": str(man.get("version", "0.1.0")),
        "artefact_digest": digest,
        "targets": targets,
        "cubes": cubes,
        "metrics": metrics,
    }
    for extra_key in ("looker", "explores", "dashboards", "files"):
        if sl_cfg.get(extra_key) is not None:
            spec[extra_key] = sl_cfg[extra_key]
    if sl_cfg.get("brd_requirement_id"):
        spec["brd_requirement_id"] = list(sl_cfg["brd_requirement_id"])
    return spec


def _hdr(p: Product, spec: dict, target: str) -> str:
    fields = {
        "product": p.id,
        "version": spec["version"],
        "element": "semantic_layer",
        "target": target,
        "implements": "generate-artefacts",
    }
    if spec.get("brd_requirement_id"):
        fields["satisfies"] = ",".join(spec["brd_requirement_id"])
    return marker(fields, "#")


def render_cube(p: Product, spec: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    hdr = _hdr(p, spec, "cube")
    for c in spec["cubes"]:
        cube_doc = {
            "cubes": [{
                "name": c["name"],
                "sql_table": f"`{c['table_ref']}`",
                "description": c["description"],
                "joins": [
                    {"name": j["to"], "sql": f"{{{c['name']}}}.{j['on'].split(' = ')[0].split('.')[-1]} = {{{j['to']}}}.{j['on'].split(' = ')[1].split('.')[-1]}",
                     "relationship": j["relationship"]}
                    for j in c.get("joins") or []
                ],
                "dimensions": [
                    {k: v for k, v in {
                        "name": d["name"],
                        "sql": d["sql"],
                        "type": d["type"],
                        "primary_key": True if d.get("primary_key") else None,
                    }.items() if v is not None}
                    for d in c["dimensions"]
                ],
                "measures": [
                    {k: v for k, v in {
                        "name": m["name"],
                        "sql": m["sql"] if m["type"] != "count" else None,
                        "type": m["type"],
                        "description": m.get("description", ""),
                    }.items() if v is not None}
                    for m in c["measures"]
                ],
            }]
        }
        out[f"semantic_layer/cube/{c['name']}.yml"] = hdr + "\n" + yaml.safe_dump(cube_doc, sort_keys=False, width=1000)
    return out


def render_metricflow(p: Product, spec: dict) -> dict[str, str]:
    hdr = _hdr(p, spec, "metricflow")
    sem_models = []
    for c in spec["cubes"]:
        pk = (c["grain_columns"] or ["id"])[0]
        time_dims = [d["name"] for d in c["dimensions"] if d["type"] == "time"]
        entities = [{"name": pk, "type": "primary", "expr": pk}]
        for j in c.get("joins") or []:
            fk = j["on"].split(" = ")[0].split(".")[-1]
            entities.append({"name": j["to"], "type": "foreign", "expr": fk})
        sm = {
            "name": c["name"],
            "description": c["description"],
            "model": f"ref('{c['model']}')",
            "entities": entities,
            "dimensions": [
                {
                    "name": d["name"],
                    "type": "time" if d["type"] == "time" else "categorical",
                    **({"type_params": {"time_granularity": "day"}} if d["type"] == "time" else {}),
                }
                for d in c["dimensions"] if d["name"] != pk
            ],
            "measures": [
                {
                    "name": m["name"],
                    "agg": "sum" if m["type"] == "sum" else ("average" if m["type"] == "avg" else "count"),
                    "expr": m["sql"],
                    "description": m.get("description", ""),
                }
                for m in c["measures"] if m["type"] in ("sum", "avg", "count")
            ],
        }
        if time_dims:
            sm["defaults"] = {"agg_time_dimension": time_dims[0]}
        sem_models.append(sm)
    mf_metrics = [
        {
            "name": m["name"],
            "label": m["label"],
            "type": m["type"],
            "type_params": {"measure": m.get("measure") or m["name"]},
            **({"filter": f"{{{{ Dimension('{m['filter']}') }}}}"} if m.get("filter") else {}),
        }
        for m in spec["metrics"]
    ]
    doc = {"semantic_models": sem_models, "metrics": mf_metrics}
    return {"semantic_layer/metricflow/semantic_models.yml": hdr + "\n" + yaml.safe_dump(doc, sort_keys=False, width=1000)}


def render_atscale(p: Product, spec: dict) -> dict[str, str]:
    hdr = _hdr(p, spec, "atscale")
    doc = {
        "schema_version": "2.0",
        "unique_name": p.id,
        "label": f"{p.id} (v{spec['version']})",
        "datasets": [
            {
                "unique_name": c["name"],
                "table_ref": c["table_ref"],
                "key_columns": c["grain_columns"],
                "dimensions": [d["name"] for d in c["dimensions"]],
                "metrics": [{"name": m["name"], "calculation_method": m["type"], "column": m["sql"]} for m in c["measures"]],
            }
            for c in spec["cubes"]
        ],
        "relationships": [
            {"from_dataset": c["name"], "to_dataset": j["to"], "condition": j["on"]}
            for c in spec["cubes"] for j in c.get("joins") or []
        ],
    }
    return {f"semantic_layer/atscale/{p.id}.atscale.yml": hdr + "\n" + yaml.safe_dump(doc, sort_keys=False, width=1000)}


def render_osi(p: Product, spec: dict) -> dict[str, str]:
    hdr = _hdr(p, spec, "osi")
    doc = {
        "osi_version": "0.1.0",
        "semantic_model": {
            "name": p.id,
            "version": spec["version"],
            "build_digest": spec["artefact_digest"],
            "entities": [
                {
                    "name": c["name"],
                    "source_table": c["table_ref"],
                    "grain": c["grain_columns"],
                    "attributes": [{"name": d["name"], "data_type": d["type"]} for d in c["dimensions"]],
                    "measures": [{"name": m["name"], "aggregation": m["type"], "expression": m["sql"]} for m in c["measures"]],
                    "relationships": c.get("joins") or [],
                }
                for c in spec["cubes"]
            ],
            "metrics": spec["metrics"],
        },
    }
    return {f"semantic_layer/osi/{p.id}.osi.yaml": hdr + "\n" + yaml.safe_dump(doc, sort_keys=False, width=1000)}


TARGET_RENDERERS = {
    "cube": render_cube,
    "metricflow": render_metricflow,
    "atscale": render_atscale,
    "osi": render_osi,
}


def render(p: Product, g: ProductGraph, digest: str, targets_override: list[str] | None = None) -> tuple[dict[str, str], list[str]]:
    spec = build_semantic_spec(p, g, digest, targets_override)
    if spec is None:
        return {}, []
    files: dict[str, str] = {"semantic-layer.json": dumps(spec)}
    problems: list[str] = []
    for t in spec["targets"]:
        if t == "lookml":
            lfiles = lookml.render(p, spec, g)
            files.update(lfiles)
            problems += lookml.validate_lookml_files(lfiles, spec)
        else:
            fn = TARGET_RENDERERS.get(t)
            if fn:
                files.update(fn(p, spec))
    return files, problems
