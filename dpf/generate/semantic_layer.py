"""Versioned BI Semantic Layer generator (semantic-layer.v1): Cube, MetricFlow, AtScale, and OSI."""

from __future__ import annotations

import yaml

from dpf.core import Product
from dpf.graph import ProductGraph
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


def build_semantic_spec(p: Product, g: ProductGraph, digest: str, targets_override: list[str] | None = None) -> dict | None:
    man = p.manifest
    sl_cfg = man.get("semantic_layer") or {}
    targets = list(targets_override or sl_cfg.get("targets") or [])
    if not targets:
        return None

    cubes: list[dict] = []
    metrics: list[dict] = []
    explicit_metrics = list(sl_cfg.get("metrics") or [])

    for name in [x for x in g.topo() if g.nodes[x].kind == "model"]:
        n = g.nodes[name]
        if n.layer == "staging" or n.role == "ml_model":
            continue
        m = n.model
        attrs = m.get("attributes") or {}
        grain = list(m.get("grain_columns") or [])
        tref = table_ref(p, g, name)
        dims: list[dict] = []
        measures: list[dict] = []
        joins: list[dict] = []

        for col in grain:
            dims.append({
                "name": col,
                "sql": col,
                "type": "time" if _is_time_col(col, m) else "string",
                "primary_key": True,
            })

        if n.role == "dimension":
            for col in list(attrs.get("tracked") or []) + list(attrs.get("current") or []):
                if col not in grain:
                    dims.append({"name": col, "sql": col, "type": "time" if _is_time_col(col, m) else "string"})
        elif n.role == "fact":
            ev_date = attrs.get("event_date")
            if ev_date and ev_date not in grain:
                dims.append({"name": ev_date, "sql": ev_date, "type": "time"})
            for col in list(attrs.get("degenerate") or []):
                if col not in grain:
                    dims.append({"name": col, "sql": col, "type": "string"})
            for f in list(attrs.get("flags") or []):
                fname = f.get("name")
                if fname and fname not in grain:
                    dims.append({"name": fname, "sql": fname, "type": "boolean"})
            for ms in list(attrs.get("measures") or []):
                mname = ms["name"]
                mtype = MEASURE_TYPE.get(ms.get("additivity", "additive"), "sum")
                measures.append({
                    "name": mname,
                    "sql": mname,
                    "type": mtype,
                    "additivity": ms.get("additivity", "additive"),
                    "description": f"{mname} ({ms.get('additivity', 'additive')}) on {name}",
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
            for ref in list(attrs.get("dim_refs") or []):
                dim_node = g.get(ref.get("dimension") or "")
                if dim_node is None:
                    continue
                if dim_node.role == "calendar":
                    joins.append({
                        "to": dim_node.name,
                        "relationship": "many_to_one",
                        "on": f"{name}.date_key = {dim_node.name}.date_key",
                    })
                else:
                    sk = dim_node.model.get("surrogate_key") or ref.get("natural_key")
                    joins.append({
                        "to": dim_node.name,
                        "relationship": "many_to_one",
                        "on": f"{name}.{sk} = {dim_node.name}.{sk}",
                    })
        else:
            out_cols = g.output_columns(name) or []
            for col in out_cols:
                if col not in grain:
                    dims.append({
                        "name": col,
                        "sql": col,
                        "type": "time" if _is_time_col(col, m) else "string",
                    })
            measures.append({
                "name": "row_count",
                "sql": grain[0] if grain else "*",
                "type": "count",
                "additivity": "additive",
                "description": f"Row count of {name} at declared grain",
            })

        cubes.append({
            "name": name,
            "model": name,
            "table_ref": tref,
            "description": m.get("grain_statement") or name,
            "grain_columns": grain,
            "dimensions": dims,
            "measures": measures,
            "joins": joins,
        })

    for em in explicit_metrics:
        metrics.append(dict(em))
        target_cube = next((c for c in cubes if c["model"] == em.get("model")), None)
        if target_cube and em.get("measure"):
            if not any(ms["name"] == em["measure"] for ms in target_cube["measures"]):
                target_cube["measures"].append({
                    "name": em["measure"],
                    "sql": em.get("expr") or em["measure"],
                    "type": "sum" if em.get("type", "simple") == "simple" else "number",
                    "additivity": "additive",
                    "description": em.get("description") or em.get("label") or em["name"],
                })

    spec = {
        "product_id": p.id,
        "version": str(man.get("version", "0.1.0")),
        "artefact_digest": digest,
        "targets": targets,
        "cubes": cubes,
        "metrics": metrics,
    }
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


def render(p: Product, g: ProductGraph, digest: str, targets_override: list[str] | None = None) -> dict[str, str]:
    spec = build_semantic_spec(p, g, digest, targets_override)
    if spec is None:
        return {}
    files: dict[str, str] = {"semantic-layer.json": dumps(spec)}
    for t in spec["targets"]:
        fn = TARGET_RENDERERS.get(t)
        if fn:
            files.update(fn(p, spec))
    return files
