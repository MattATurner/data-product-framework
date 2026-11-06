"""LookML semantic model, Explore, and Dashboard renderer & static validator (ADR-018)."""

from __future__ import annotations

import re
from typing import Any

import yaml

from dpf.core import Product
from dpf.graph import ProductGraph
from dpf.generate.render import duration_minutes, is_timestamp, marker, snake_id

DATE_TIMEFRAMES = ["raw", "date", "week", "month", "quarter", "year"]
TS_TIMEFRAMES = ["raw", "time", "date", "week", "month", "quarter", "year"]

TILE_LOOKER_TYPE = {
    "kpi": "single_value",
    "bullet": "looker_bar",
    "time_series": "looker_line",
    "ranked_bar": "looker_bar",
    "column": "looker_column",
    "table": "looker_grid",
    "markdown": "text",
}

DEFAULT_TILE_SIZE = {
    "kpi": (6, 4),
    "bullet": (12, 6),
    "time_series": (12, 8),
    "ranked_bar": (12, 8),
    "column": (12, 8),
    "table": (24, 8),
    "markdown": (24, 3),
}


def _lkml_str(val: str) -> str:
    escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dg_base_and_tfs(col: str, all_cols: set[str]) -> tuple[str, list[str], str]:
    """Return (dimension_group_name, timeframes, datatype) for a time column."""
    if is_timestamp(col):
        for suf in ("_timestamp", "_ts", "_at"):
            if col.endswith(suf):
                stem = col[: -len(suf)]
                if stem and stem not in all_cols:
                    return stem, TS_TIMEFRAMES, "timestamp"
        return col, TS_TIMEFRAMES, "timestamp"
    if col.endswith("_date"):
        stem = col[:-5]
        if stem and stem not in all_cols:
            return stem, DATE_TIMEFRAMES, "date"
    return col, DATE_TIMEFRAMES, "date"


def cube_field_map(cube: dict) -> dict[str, str]:
    """Return {field_name: kind} ('dimension' | 'measure') exposed by the LookML view for a cube."""
    fields: dict[str, str] = {}
    all_cols = {d["name"] for d in cube.get("dimensions") or []}
    sk = cube.get("surrogate_key")
    grain = list(cube.get("grain_columns") or [])
    if sk and sk not in all_cols:
        fields[sk] = "dimension"
    has_single_dim_pk = bool(sk) or (
        len(grain) == 1 and not any(d["name"] == grain[0] and d["type"] == "time" for d in cube.get("dimensions") or [])
    )
    if not has_single_dim_pk:
        fields["_dpf_pk"] = "dimension"
    for d in cube.get("dimensions") or []:
        if d["type"] == "time":
            dg_name, tfs, _ = _dg_base_and_tfs(d["name"], all_cols)
            for tf in tfs:
                fields[f"{dg_name}_{tf}"] = "dimension"
        else:
            fields[d["name"]] = "dimension"
    fields["count"] = "measure"
    for m in cube.get("measures") or []:
        if m["name"] != "row_count":
            fields[m["name"]] = "measure"
    return fields


def explore_field_map(explore: dict, cubes_by_name: dict[str, dict]) -> dict[str, str]:
    """Return {'<view>.<field>': kind} reachable in an Explore."""
    out: dict[str, str] = {}
    base_name = explore.get("from") or ""
    base = cubes_by_name.get(base_name)
    if not base:
        return out
    for fname, fkind in cube_field_map(base).items():
        out[f"{base_name}.{fname}"] = fkind
    joins = explore.get("joins")
    if joins is None or joins == "auto":
        joined_views = [j["to"] for j in base.get("joins") or []]
    else:
        joined_views = [j["view"] for j in joins]
    for jv in joined_views:
        jcube = cubes_by_name.get(jv)
        if not jcube:
            continue
        for fname, fkind in cube_field_map(jcube).items():
            out[f"{jv}.{fname}"] = fkind
    return out


def _dataset_constants(
    p: Product, spec: dict, g: ProductGraph
) -> tuple[list[tuple[str, str]], dict[str, tuple[str, str, str]]]:
    """Return (ordered [(const_name, value)], {cube_name: (proj_const, ds_const, table_name)})."""
    dep_proj = ((p.manifest.get("deployment") or {}).get("gcp_project") or "")
    constants: list[tuple[str, str]] = []
    seen_consts: dict[str, str] = {}

    def add_const(cname: str, val: str) -> str:
        if cname not in seen_consts:
            seen_consts[cname] = val
            constants.append((cname, val))
        return cname

    if dep_proj:
        add_const("GCP_PROJECT", dep_proj)

    cube_refs: dict[str, tuple[str, str, str]] = {}
    for c in spec.get("cubes") or []:
        node = g.get(c["name"])
        parts = (c.get("table_ref") or "...").split(".")
        proj = parts[0] if len(parts) == 3 else dep_proj
        ds = parts[1] if len(parts) == 3 else ""
        tbl = parts[2] if len(parts) == 3 else c["name"]
        if proj == dep_proj and dep_proj:
            proj_const = "GCP_PROJECT"
        else:
            proj_const = add_const(f"GCP_PROJECT_{snake_id(proj).upper()}", proj)
        if node and node.kind == "model":
            ds_key = node.model.get("dataset") or node.layer
        else:
            ds_key = ds
        ds_const = f"DATASET_{snake_id(ds_key).upper()}"
        if ds_const in seen_consts and seen_consts[ds_const] != ds:
            ds_const = f"DATASET_{snake_id(ds).upper()}"
        add_const(ds_const, ds)
        cube_refs[c["name"]] = (proj_const, ds_const, tbl)
    return constants, cube_refs


def _cache_age(p: Product, looker_cfg: dict) -> str:
    if looker_cfg.get("datagroup_max_cache_age"):
        return str(looker_cfg["datagroup_max_cache_age"])
    fresh = ((p.manifest.get("observability") or {}).get("freshness") or [])
    if fresh and fresh[0].get("max_staleness"):
        mins = duration_minutes(fresh[0]["max_staleness"])
        if mins % 60 == 0:
            return f"{mins // 60} hours" if mins >= 120 else "1 hour"
        return f"{mins} minutes"
    return "1 hour"


def _hdr(p: Product, version: str, element: str, reqs: list[str] | None = None) -> str:
    fields: dict[str, Any] = {
        "product": p.id,
        "version": version,
        "element": element,
        "target": "lookml",
        "implements": "generate-artefacts",
    }
    if reqs:
        fields["satisfies"] = ",".join(reqs)
    return marker(fields, "#")


def _render_manifest_lkml(p: Product, spec: dict, constants: list[tuple[str, str]]) -> str:
    looker_cfg = spec.get("looker") or {}
    proj_name = looker_cfg.get("project_name") or p.id
    lines = [
        _hdr(p, spec["version"], "semantic_layer", spec.get("brd_requirement_id")),
        f"project_name: {_lkml_str(proj_name)}",
        "",
    ]
    hub = looker_cfg.get("import_views_from")
    if hub:
        lines += [
            "local_dependency: {",
            f"  project: {_lkml_str(hub)}",
            "}",
            "",
        ]
    for cname, cval in constants:
        lines += [
            f"constant: {cname} {{",
            f"  value: {_lkml_str(cval)}",
            "  export: override_optional",
            "}",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def _render_model_lkml(p: Product, spec: dict, cube_refs: dict[str, tuple[str, str, str]]) -> str:
    looker_cfg = spec.get("looker") or {}
    conn = looker_cfg.get("connection") or f"bigquery_{p.id}"
    dg_name = f"{p.id}_default_datagroup"
    max_age = _cache_age(p, looker_cfg)
    reqs = sorted({
        *(spec.get("brd_requirement_id") or []),
        *(r for e in (spec.get("explores") or []) for r in (e.get("brd_requirement_id") or [])),
        *(r for d in (spec.get("dashboards") or []) for r in (d.get("brd_requirement_id") or [])),
    }, key=lambda x: int(x.split("-")[1]) if "-" in x and x.split("-")[1].isdigit() else 0)
    lines = [
        _hdr(p, spec["version"], "semantic_layer", reqs),
        f"connection: {_lkml_str(conn)}",
        "",
        'include: "/views/*.view.lkml"',
    ]
    if spec.get("explores"):
        lines.append('include: "/explores/*.explore.lkml"')
    if spec.get("dashboards"):
        lines.append('include: "/dashboards/*.dashboard.lookml"')
    lines.append("")

    # Pick a deterministic datagroup trigger from the primary partitioned cube when available.
    trigger_sql = "SELECT CURRENT_DATE()"
    for c in spec.get("cubes") or []:
        part = c.get("partition_by")
        if part and c["name"] in cube_refs:
            p_const, d_const, tbl = cube_refs[c["name"]]
            trigger_sql = f"SELECT MAX({part}) FROM `@{{{p_const}}}.@{{{d_const}}}.{tbl}`"
            break

    lines += [
        f"datagroup: {dg_name} {{",
        f"  sql_trigger: {trigger_sql} ;;",
        f"  max_cache_age: {_lkml_str(max_age)}",
        "}",
        "",
        f"persist_with: {dg_name}",
    ]

    if looker_cfg.get("auth_mode") == "service_account":
        seen_tags: set[str] = set()
        for c in spec.get("cubes") or []:
            for pt in c.get("policy_tags") or []:
                tag = pt.get("tag")
                if tag and tag not in seen_tags:
                    seen_tags.add(tag)
                    lines += [
                        "",
                        f"access_grant: {snake_id('can_view', tag)} {{",
                        f"  user_attribute: {snake_id('dpf', tag, 'access')}",
                        '  allowed_values: ["unmasked"]',
                        "}",
                    ]
    return "\n".join(lines).rstrip() + "\n"


def _parse_measure_filter(flt: str, bool_dims: set[str]) -> tuple[list[tuple[str, str]], str | None]:
    """Convert simple SQL predicates into idiomatic LookML measure filters when possible."""
    s = flt.strip()
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(FALSE|TRUE)$", s, re.I)
    if m and m.group(1) in bool_dims:
        return [(m.group(1), "yes" if m.group(2).upper() == "TRUE" else "no")], None
    m = re.match(r"^NOT\s+([A-Za-z_][A-Za-z0-9_]*)$", s, re.I)
    if m and m.group(1) in bool_dims:
        return [(m.group(1), "no")], None
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'([^']*)'$", s)
    if m:
        return [(m.group(1), m.group(2))], None
    return [], s


def _render_view_lkml(
    p: Product,
    g: ProductGraph,
    spec: dict,
    cube: dict,
    ref_consts: tuple[str, str, str],
) -> str:
    looker_cfg = spec.get("looker") or {}
    hub = looker_cfg.get("import_views_from")
    auth_mode = looker_cfg.get("auth_mode", "oauth")
    cname = cube["name"]
    node = g.get(cname)
    reqs = (node.model.get("brd_requirement_id") if node else None) or spec.get("brd_requirement_id")
    if node and node.kind == "model":
        elem = f"model:{cname}"
    elif node and node.kind == "upstream":
        elem = f"upstream:{node.source}"
    else:
        elem = "semantic_layer"
    hdr = _hdr(p, spec["version"], elem, reqs)

    bool_dims = {d["name"] for d in cube.get("dimensions") or [] if d["type"] == "boolean"}
    cube_metrics = [m for m in (spec.get("metrics") or []) if m.get("model") == cname]

    if hub:
        lines = [
            hdr,
            f'include: "//{hub}/views/{cname}.view.lkml"',
            "",
            f"view: +{cname} {{",
        ]
        for mt in cube_metrics:
            lines.extend(_render_metric_measure(mt, bool_dims))
        lines.append("}")
        return "\n".join(lines).rstrip() + "\n"

    p_const, d_const, tbl = ref_consts
    lines = [
        hdr,
        f"view: {cname} {{",
        f"  sql_table_name: `@{{{p_const}}}.@{{{d_const}}}.{tbl}` ;;",
    ]

    all_cols = {d["name"] for d in cube.get("dimensions") or []}
    sk = cube.get("surrogate_key")
    grain = list(cube.get("grain_columns") or [])
    tagged_cols: dict[str, str] = {}
    if auth_mode == "service_account":
        for pt in cube.get("policy_tags") or []:
            for col in pt.get("columns") or []:
                tagged_cols[col] = snake_id("can_view", pt["tag"])

    pk_col: str | None = None
    if sk:
        pk_col = sk
    elif len(grain) == 1 and not any(d["name"] == grain[0] and d["type"] == "time" for d in cube.get("dimensions") or []):
        pk_col = grain[0]

    if pk_col is None:
        concat_parts = ", '|', ".join(f"CAST(${{TABLE}}.{c} AS STRING)" for c in (grain or ["1"]))
        pk_sql = f"CONCAT({concat_parts})" if len(grain) > 1 else f"CAST(${{TABLE}}.{grain[0]} AS STRING)"
        lines += [
            "",
            "  dimension: _dpf_pk {",
            "    primary_key: yes",
            "    hidden: yes",
            "    type: string",
            f"    sql: {pk_sql} ;;",
            "  }",
        ]
    elif sk and sk not in all_cols:
        lines += [
            "",
            f"  dimension: {sk} {{",
            "    primary_key: yes",
            "    hidden: yes",
            "    type: number",
            f"    sql: ${{TABLE}}.{sk} ;;",
            "  }",
        ]

    for d in cube.get("dimensions") or []:
        dname = d["name"]
        desc = d.get("description")
        if d["type"] == "time":
            dg_name, tfs, dtype = _dg_base_and_tfs(dname, all_cols)
            lines += [
                "",
                f"  dimension_group: {dg_name} {{",
                "    type: time",
                f"    timeframes: [{', '.join(tfs)}]",
                f"    datatype: {dtype}",
            ]
            if desc:
                lines.append(f"    description: {_lkml_str(desc)}")
            lines += [
                f"    sql: ${{TABLE}}.{dname} ;;",
                "  }",
            ]
        else:
            ltype = {"boolean": "yesno", "number": "number"}.get(d["type"], "string")
            if dname == sk or dname == "date_key":
                ltype = "number"
            lines += ["", f"  dimension: {dname} {{"]
            if dname == pk_col:
                lines.append("    primary_key: yes")
            if d.get("hidden"):
                lines.append("    hidden: yes")
            lines.append(f"    type: {ltype}")
            if desc:
                lines.append(f"    description: {_lkml_str(desc)}")
            if dname in tagged_cols:
                lines.append(f"    required_access_grants: [{tagged_cols[dname]}]")
            lines += [
                f"    sql: ${{TABLE}}.{dname} ;;",
                "  }",
            ]

    lines += [
        "",
        "  measure: count {",
        "    type: count",
        f"    description: {_lkml_str(f'Row count of {cname}')}",
        "  }",
    ]

    explicit_names = {mt["name"] for mt in cube_metrics}
    for ms in cube.get("measures") or []:
        mname = ms["name"]
        if mname == "row_count" or mname in explicit_names:
            continue
        mtype = {"sum": "sum", "avg": "average", "count": "count", "number": "number"}.get(ms["type"], "sum")
        lines += [
            "",
            f"  measure: {mname} {{",
            f"    type: {mtype}",
        ]
        if ms.get("description"):
            lines.append(f"    description: {_lkml_str(ms['description'])}")
        lines += [
            f"    sql: ${{TABLE}}.{ms['sql']} ;;",
            "  }",
        ]

    for mt in cube_metrics:
        lines.extend(_render_metric_measure(mt, bool_dims))

    lines.append("}")
    return "\n".join(lines).rstrip() + "\n"


def _render_metric_measure(mt: dict, bool_dims: set[str]) -> list[str]:
    mname = mt["name"]
    mtype_in = mt.get("type", "simple")
    col = mt.get("expr") or mt.get("measure") or mname
    desc = mt.get("description") or mt.get("label")
    label = mt.get("label")
    lines = ["", f"  measure: {mname} {{"]
    if label:
        lines.append(f"    label: {_lkml_str(label)}")
    if desc:
        lines.append(f"    description: {_lkml_str(desc)}")
    if mtype_in in ("derived", "ratio"):
        lines.append("    type: number")
        sql_expr = col if "${" in col else f"${{TABLE}}.{col}"
        lines.append(f"    sql: {sql_expr} ;;")
    else:
        lines.append("    type: sum")
        if mt.get("filter"):
            kv_filters, raw_pred = _parse_measure_filter(mt["filter"], bool_dims)
            if kv_filters:
                for fk, fv in kv_filters:
                    lines.append(f"    filters: [{fk}: {_lkml_str(fv)}]")
                lines.append(f"    sql: ${{TABLE}}.{col} ;;")
            elif raw_pred:
                lines.append(f"    sql: CASE WHEN ({raw_pred}) THEN ${{TABLE}}.{col} END ;;")
            else:
                lines.append(f"    sql: ${{TABLE}}.{col} ;;")
        else:
            lines.append(f"    sql: ${{TABLE}}.{col} ;;")
    lines.append("  }")
    return lines


def _render_explore_lkml(p: Product, g: ProductGraph, spec: dict, explore: dict,
                         cubes_by_name: dict[str, dict]) -> str:
    ename = explore["name"]
    base_name = explore["from"]
    base = cubes_by_name[base_name]
    reqs = explore.get("brd_requirement_id") or spec.get("brd_requirement_id")
    lines = [
        _hdr(p, spec["version"], f"explore:{ename}", reqs),
        'include: "/views/*.view.lkml"',
        "",
        f"explore: {ename} {{",
        f"  view_name: {base_name}",
    ]
    if explore.get("label"):
        lines.append(f"  label: {_lkml_str(explore['label'])}")
    if explore.get("description"):
        lines.append(f"  description: {_lkml_str(explore['description'])}")

    sql_where = explore.get("sql_always_where")
    if not sql_where and base.get("history_semantics") == "scd2":
        sql_where = f"${{{base_name}.is_current}} = TRUE"
    if sql_where:
        lines.append(f"  sql_always_where: {sql_where} ;;")

    part_col = base.get("partition_by")
    if part_col and explore.get("always_filter_partition", True):
        all_cols = {d["name"] for d in base.get("dimensions") or []}
        if any(d["name"] == part_col and d["type"] == "time" for d in base.get("dimensions") or []):
            dg_name, _, _ = _dg_base_and_tfs(part_col, all_cols)
            filter_field = f"{base_name}.{dg_name}_date"
        else:
            filter_field = f"{base_name}.{part_col}"
        default_val = explore.get("partition_default_filter") or explore.get("partition_filter_default") or "90 days"
        unless_fields: list[str] = []
        joins_cfg = explore.get("joins")
        joined_names = [j["to"] for j in base.get("joins") or []] if (joins_cfg is None or joins_cfg == "auto") else [
            j["view"] for j in joins_cfg
        ]
        for jn in joined_names:
            jcube = cubes_by_name.get(jn)
            jnode = g.get(jn)
            if jcube and jnode and jnode.role == "calendar":
                cfields = cube_field_map(jcube)
                for cand in ("year_month", "year_quarter", "year", "calendar_date"):
                    if cand in cfields:
                        unless_fields.append(f"{jn}.{cand}")
        lines += [
            "",
            "  conditionally_filter: {",
            f"    filters: [{filter_field}: {_lkml_str(default_val)}]",
        ]
        if unless_fields:
            lines.append(f"    unless: [{', '.join(unless_fields)}]")
        lines.append("  }")

    joins_cfg = explore.get("joins")
    if joins_cfg is None or joins_cfg == "auto":
        for j in base.get("joins") or []:
            lhs, rhs = j["on"].split(" = ", 1)
            lines += [
                "",
                f"  join: {j['to']} {{",
                "    type: left_outer",
                f"    relationship: {j['relationship']}",
                f"    sql_on: ${{{lhs.strip()}}} = ${{{rhs.strip()}}} ;;",
                "  }",
            ]
    else:
        for j in joins_cfg:
            lines += [
                "",
                f"  join: {j['view']} {{",
                f"    type: {j.get('type', 'left_outer')}",
                f"    relationship: {j['relationship']}",
                f"    sql_on: {j['sql_on']} ;;",
                "  }",
            ]

    dg_name = f"{p.id}_default_datagroup"
    exp_fields = explore_field_map(explore, cubes_by_name)
    for agg in explore.get("aggregate_tables") or []:
        if isinstance(agg, str):
            agg_cube = cubes_by_name.get(agg)
            if not agg_cube:
                continue
            agg_dims: list[str] = []
            for gcol in agg_cube.get("grain_columns") or []:
                match = next((qf for qf, fk in exp_fields.items() if fk == "dimension" and qf.split(".")[-1] == gcol), None)
                if match:
                    agg_dims.append(match)
            agg_measures = [
                f"{base_name}.{fname}"
                for fname, fk in cube_field_map(base).items()
                if fk == "measure" and (fname == "count" or any(d["name"] == fname for d in (agg_cube.get("dimensions") or [])))
            ]
            if agg_dims and agg_measures:
                lines += [
                    "",
                    f"  aggregate_table: {agg} {{",
                    "    query: {",
                    f"      dimensions: [{', '.join(agg_dims)}]",
                    f"      measures: [{', '.join(agg_measures)}]",
                    "    }",
                    "    materialization: {",
                    f"      datagroup_trigger: {dg_name}",
                    "    }",
                    "  }",
                ]
        elif isinstance(agg, dict):
            lines += [
                "",
                f"  aggregate_table: {agg['name']} {{",
                "    query: {",
                f"      dimensions: [{', '.join(agg['dimensions'])}]",
                f"      measures: [{', '.join(agg['measures'])}]",
                "    }",
                "    materialization: {",
                f"      datagroup_trigger: {dg_name}",
                "    }",
                "  }",
            ]

    lines.append("}")
    return "\n".join(lines).rstrip() + "\n"


def _render_dashboard_lkml(p: Product, spec: dict, dash: dict, explores_by_name: dict[str, dict],
                           cubes_by_name: dict[str, dict]) -> str:
    dname = dash["name"]
    reqs = dash.get("brd_requirement_id") or spec.get("brd_requirement_id")
    hdr = _hdr(p, spec["version"], f"dashboard:{dname}", reqs)

    if dash.get("file"):
        fpath = p.dir / dash["file"]
        raw = fpath.read_text(encoding="utf-8") if fpath.exists() else ""
        stripped = "\n".join(ln for ln in raw.splitlines() if not ln.strip().startswith("# dpf:"))
        return hdr + "\n" + stripped.strip() + "\n"

    default_explore = dash.get("explore") or ""
    filters_out: list[dict[str, Any]] = []
    for flt in dash.get("filters") or []:
        filters_out.append({
            "name": flt["name"],
            "title": flt["title"],
            "type": "field_filter",
            "model": p.id,
            "explore": default_explore,
            "field": flt["field"],
            "default_value": flt.get("default_value", ""),
            "allow_multiple_values": True,
            "required": False,
        })

    elements: list[dict[str, Any]] = []
    cur_row, cur_col, row_h = 0, 0, 0
    for tile in dash.get("tiles") or []:
        kind = tile["kind"]
        ltype = TILE_LOOKER_TYPE[kind]
        def_w, def_h = DEFAULT_TILE_SIZE[kind]
        w = int(tile.get("width") or def_w)
        h = int(tile.get("height") or def_h)
        if tile.get("row") is not None and tile.get("col") is not None:
            t_row, t_col = int(tile["row"]), int(tile["col"])
        else:
            if cur_col + w > 24:
                cur_row += row_h
                cur_col = 0
                row_h = 0
            t_row, t_col = cur_row, cur_col
            cur_col += w
            row_h = max(row_h, h)

        tname = tile.get("name") or tile.get("id")
        if kind == "markdown":
            elements.append({
                "name": tname,
                "title": tile["title"],
                "type": "text",
                "body_text": tile.get("body") or tile.get("body_text") or tile.get("note") or "",
                "row": t_row,
                "col": t_col,
                "width": w,
                "height": h,
            })
            continue

        texplore = tile.get("explore") or default_explore
        exp_obj = explores_by_name.get(texplore) or {}
        reach = explore_field_map(exp_obj, cubes_by_name) if exp_obj else {}
        fields = list(tile.get("dimensions") or []) + list(tile.get("measures") or [])
        elem: dict[str, Any] = {
            "name": tname,
            "title": tile["title"],
            "model": p.id,
            "explore": texplore,
            "type": ltype,
            "fields": fields,
        }
        if tile.get("pivots"):
            elem["pivots"] = list(tile["pivots"])
        if tile.get("sorts"):
            elem["sorts"] = list(tile["sorts"])
        if tile.get("limit"):
            elem["limit"] = int(tile["limit"])
        if tile.get("filters"):
            elem["filters"] = dict(tile["filters"])
        if kind in ("bullet", "ranked_bar", "column"):
            elem["y_axes"] = [{"unpinAxis": not bool(tile.get("y_axis_zero", True))}]
            elem["x_axis_gridlines"] = False
            elem["y_axis_gridlines"] = True
        if kind == "bullet" and tile.get("target") is not None:
            elem["reference_lines"] = [{"reference_type": "line", "line_value": str(tile["target"]), "label_position": "right"}]
        if tile.get("note"):
            elem["note_display"] = "below"
            elem["note_text"] = tile["note"]

        listen = {
            flt["name"]: flt["field"]
            for flt in (dash.get("filters") or [])
            if not reach or flt["field"] in reach
        }
        if listen:
            elem["listen"] = listen
        elem.update({"row": t_row, "col": t_col, "width": w, "height": h})
        elements.append(elem)

    doc = [{
        "dashboard": dname,
        "title": dash["title"],
        "layout": "newspaper",
        "preferred_viewer": "dashboards-next",
        "description": dash.get("description") or f"{dash['title']} ({p.id})",
        "filters": filters_out,
        "elements": elements,
    }]
    return hdr + "\n" + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def _render_gemini_md(p: Product, spec: dict) -> str:
    lines = [
        _hdr(p, spec["version"], "semantic_layer", spec.get("brd_requirement_id")),
        f"# Looker Agent Guardrails — `{p.id}`",
        "",
        "Generated by the Data Product Framework (`dpf generate`, ADR-018). Any AI agent operating in the Looker IDE",
        "or through `looker-mcp` on this project MUST follow these workspace invariants:",
        "",
        "1. **Source of truth:** `products/" + p.id + "/product.yaml` owns view grains, surrogate-key joins, metric",
        "   definitions, Explores, and Stephen Few dashboard layouts. Do not hand-edit generated `.lkml` files without",
        "   importing changes back via `dpf proto import-looker " + p.id + " --from <dir>`.",
        "2. **No Persistent Derived Tables (PDTs):** Never add `derived_table`, `sql_trigger_value`, or",
        "   `datagroup_trigger` inside LookML views. Materializations belong in governed BigQuery layers (`silver`/`gold`)",
        "   or Explore-level `aggregate_table` blocks.",
        "3. **Symmetric aggregates & Kimball keys:** Keep `primary_key: yes` on every joined view and join Kimball",
        "   dimensions on surrogate keys (`sk_*`), never on mutable natural keys.",
        "4. **Visual discipline:** Dashboards follow Stephen Few perceptual rules — zero pie/donut charts, zero dual",
        "   Y-axes, and zero-anchored quantitative bars (`unpinAxis: false`).",
        "",
    ]
    return "\n".join(lines)


def render(p: Product, spec: dict, g: ProductGraph | None = None) -> dict[str, str]:
    g = g or ProductGraph(p)
    files: dict[str, str] = {}
    constants, cube_refs = _dataset_constants(p, spec, g)
    cubes_by_name = {c["name"]: c for c in spec.get("cubes") or []}
    explores_by_name = {e["name"]: e for e in spec.get("explores") or []}

    root = "semantic_layer/lookml"
    files[f"{root}/manifest.lkml"] = _render_manifest_lkml(p, spec, constants)
    files[f"{root}/{p.id}.model.lkml"] = _render_model_lkml(p, spec, cube_refs)
    for c in spec.get("cubes") or []:
        files[f"{root}/views/{c['name']}.view.lkml"] = _render_view_lkml(p, g, spec, c, cube_refs[c["name"]])
    for e in spec.get("explores") or []:
        if e.get("from") in cubes_by_name:
            files[f"{root}/explores/{e['name']}.explore.lkml"] = _render_explore_lkml(p, g, spec, e, cubes_by_name)
    for d in spec.get("dashboards") or []:
        files[f"{root}/dashboards/{d['name']}.dashboard.lookml"] = _render_dashboard_lkml(
            p, spec, d, explores_by_name, cubes_by_name
        )
    files[f"{root}/GEMINI.md"] = _render_gemini_md(p, spec)
    return files


# ----------------------------------------------------------------- validation
_SQL_ATTR_RE = re.compile(r"^\s*(?:sql|sql_table_name|sql_on|sql_always_where|sql_trigger)\s*:")
_PDT_RE = re.compile(r"^\s*(derived_table|sql_trigger_value|datagroup_trigger|persist_for)\s*:", re.M)
_FIELD_REF_RE = re.compile(r"\$\{([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\}")


def _check_braces(path: str, text: str) -> list[str]:
    depth = 0
    in_str = False
    escape = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        for i, ch in enumerate(line):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_str:
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str and ch == "#":
                break
            if not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth < 0:
                        return [f"{path}: unmatched closing '}}'"]
    if in_str:
        return [f"{path}: unterminated string literal"]
    if depth != 0:
        return [f"{path}: unbalanced '{{' / '}}' braces (net depth {depth})"]
    return []


def _check_sql_terminators(path: str, text: str) -> list[str]:
    errs: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip().startswith("#") and _SQL_ATTR_RE.match(ln):
            found = ";;" in ln
            j = i + 1
            while not found and j < len(lines):
                if ";;" in lines[j]:
                    found = True
                    break
                j += 1
            if not found:
                errs.append(f"{path}:{i + 1}: LookML SQL attribute is missing ';;' terminator")
            i = j
        i += 1
    return errs


def validate_lookml_files(files: dict[str, str], spec: dict) -> list[str]:
    """Static syntax, anti-PDT, and symbol-resolution check across generated LookML & Dashboards."""
    problems: list[str] = []
    allow_pdt = bool((spec.get("looker") or {}).get("allow_pdt"))
    cubes_by_name = {c["name"]: c for c in spec.get("cubes") or []}
    explores_by_name = {e["name"]: e for e in spec.get("explores") or []}

    for path, content in sorted(files.items()):
        if not path.startswith("semantic_layer/lookml/"):
            continue
        if path.endswith(".lkml") and not path.endswith(".dashboard.lookml"):
            problems += _check_braces(path, content)
            problems += _check_sql_terminators(path, content)
        if path.endswith(".view.lkml") and not allow_pdt:
            m = _PDT_RE.search(content)
            if m:
                problems.append(
                    f"{path}: LookML view contains '{m.group(1)}:' (PDTs are banned by default per ADR-018)"
                )
        if path.endswith(".explore.lkml"):
            ename = path.rsplit("/", 1)[-1].removesuffix(".explore.lkml")
            exp = explores_by_name.get(ename)
            if exp and exp.get("from") in cubes_by_name:
                reach = explore_field_map(exp, cubes_by_name)
                for vname, fname in _FIELD_REF_RE.findall(content):
                    if vname == "TABLE":
                        continue
                    if f"{vname}.{fname}" not in reach:
                        problems.append(f"{path}: unresolved LookML field reference '${{{vname}.{fname}}}'")
        if path.endswith(".dashboard.lookml"):
            try:
                parsed = yaml.safe_load(content)
            except yaml.YAMLError as exc:
                problems.append(f"{path}: invalid YAML in LookML dashboard: {exc}")
                continue
            if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
                problems.append(f"{path}: LookML dashboard must be a non-empty YAML list of dashboard objects")
                continue
            dobj = parsed[0]
            for elem in dobj.get("elements") or []:
                etype = elem.get("type")
                if etype in ("looker_pie", "looker_donut_multiples", "pie", "donut"):
                    problems.append(f"{path}: element '{elem.get('name')}' uses banned chart type '{etype}'")
                if etype == "text":
                    continue
                ename = elem.get("explore")
                exp = explores_by_name.get(ename or "")
                if not exp:
                    problems.append(f"{path}: element '{elem.get('name')}' references unknown explore '{ename}'")
                    continue
                reach = explore_field_map(exp, cubes_by_name)
                for fld in elem.get("fields") or []:
                    if fld not in reach:
                        problems.append(
                            f"{path}: element '{elem.get('name')}' references unknown field '{fld}' in explore '{ename}'"
                        )
    return problems
