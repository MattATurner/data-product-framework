"""Import an existing LookML project directory into a prototype DPF Looker data product (`dpf proto import-looker`)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from dpf.core import Report, Workspace, write_text

_CONST_RE = re.compile(r'constant\s*:\s*([A-Za-z0-9_]+)\s*\{([^}]*)\}', re.S)
_CONN_RE = re.compile(r'connection\s*:\s*"([^"]+)"')
_VIEW_HDR_RE = re.compile(r'\bview\s*:\s*\+?([A-Za-z0-9_]+)\s*\{')
_EXPLORE_HDR_RE = re.compile(r'\bexplore\s*:\s*\+?([A-Za-z0-9_]+)\s*\{')
_DIM_HDR_RE = re.compile(r'\b(dimension|dimension_group|measure)\s*:\s*([A-Za-z0-9_]+)\s*\{')
_JOIN_HDR_RE = re.compile(r'\bjoin\s*:\s*([A-Za-z0-9_]+)\s*\{')


def _extract_block(text: str, open_brace_idx: int) -> tuple[str, int]:
    depth = 0
    in_str = False
    i = open_brace_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and in_str:
            i += 2
            continue
        if ch == '"':
            in_str = not in_str
        elif not in_str and ch == "#":
            nl = text.find("\n", i)
            i = n if nl < 0 else nl
            continue
        elif not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[open_brace_idx + 1 : i], i + 1
        i += 1
    return text[open_brace_idx + 1 :], n


def _iter_blocks(text: str, hdr_re: re.Pattern) -> list[tuple[tuple[str, ...], str]]:
    out: list[tuple[tuple[str, ...], str]] = []
    pos = 0
    while True:
        m = hdr_re.search(text, pos)
        if not m:
            break
        brace_idx = m.end() - 1
        body, end_pos = _extract_block(text, brace_idx)
        out.append((m.groups(), body))
        pos = end_pos
    return out


def _sub_constants(val: str, consts: dict[str, str]) -> str:
    return re.sub(r"@\{([A-Za-z0-9_]+)\}", lambda m: consts.get(m.group(1), m.group(1)), val)


def _lkml_to_bq_type(ltype: str | None, is_dg: bool) -> str:
    if is_dg:
        return "DATE"
    return {
        "number": "NUMERIC",
        "yesno": "BOOL",
        "zipcode": "STRING",
        "string": "STRING",
    }.get((ltype or "string").lower(), "STRING")


def import_looker(
    ws: Workspace,
    pid: str,
    src_dir: Path,
    report: Report,
    *,
    domain: str | None = None,
    project: str | None = None,
    region: str | None = None,
    dataset: str | None = None,
) -> None:
    report.head(f"proto · import-looker — {pid}", gate="proto")
    pdir = ws.root / "products" / pid
    if (pdir / "product.yaml").exists():
        report.fail(f"products/{pid}/product.yaml already exists")
        return
    if not src_dir.exists() or not src_dir.is_dir():
        report.fail(f"source directory '{src_dir}' does not exist")
        return

    consts: dict[str, str] = {}
    for mf in sorted(src_dir.rglob("manifest.lkml")):
        txt = mf.read_text(encoding="utf-8")
        for cm in _CONST_RE.finditer(txt):
            vm = re.search(r'value\s*:\s*"([^"]*)"', cm.group(2))
            if vm:
                consts[cm.group(1)] = vm.group(1)

    connection: str | None = None
    model_explores: list[tuple[str, str]] = []
    for modf in sorted(src_dir.rglob("*.model.lkml")):
        txt = modf.read_text(encoding="utf-8")
        cm = _CONN_RE.search(txt)
        if cm and not connection:
            connection = cm.group(1)
        for (ename,), ebody in _iter_blocks(txt, _EXPLORE_HDR_RE):
            model_explores.append((ename, ebody))

    view_files = sorted(src_dir.rglob("*.view.lkml"))
    explore_files = sorted(src_dir.rglob("*.explore.lkml"))
    dash_files = sorted(src_dir.rglob("*.dashboard.lookml"))
    if not view_files and not dash_files:
        report.fail(f"no .view.lkml or .dashboard.lookml files found in '{src_dir}'")
        return

    resolved_project = project or consts.get("GCP_PROJECT") or "example-dpf-dev"
    resolved_dataset = dataset or f"{pid}_gold"
    resolved_region = region or "europe-west2"

    tables: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []

    for vf in view_files:
        txt = vf.read_text(encoding="utf-8")
        for (vname,), vbody in _iter_blocks(txt, _VIEW_HDR_RE):
            if re.search(r"^\s*derived_table\s*:", vbody, re.M):
                report.warn(
                    f"view '{vname}' uses a LookML derived_table (PDT); materialise it as a governed BigQuery "
                    "view or table before promoting to G1 (ADR-018)"
                )
            sql_tm = re.search(r"sql_table_name\s*:\s*([^;]+);;", vbody)
            t_proj, t_ds, t_phys = resolved_project, resolved_dataset, vname
            if sql_tm:
                raw_ref = _sub_constants(sql_tm.group(1).strip().strip("`\"' "), consts)
                parts = [x.strip("`\"' ") for x in raw_ref.split(".") if x.strip("`\"' ")]
                if len(parts) == 3:
                    t_proj, t_ds, t_phys = parts[0], parts[1], parts[2]
                elif len(parts) == 2:
                    t_ds, t_phys = parts[0], parts[1]
                elif len(parts) == 1 and " " not in parts[0]:
                    t_phys = parts[0]
            if not project and t_proj != "example-dpf-dev":
                resolved_project = t_proj
            if not dataset and t_ds != f"{pid}_gold":
                resolved_dataset = t_ds

            cols: list[dict[str, Any]] = []
            seen_cols: set[str] = set()
            pk_cols: list[str] = []
            view_measures: list[dict[str, str]] = []

            for (fkind, fname), fbody in _iter_blocks(vbody, _DIM_HDR_RE):
                tm = re.search(r"^\s*type\s*:\s*([A-Za-z0-9_]+)", fbody, re.M)
                ftype = tm.group(1) if tm else None
                dm = re.search(r'description\s*:\s*"([^"]*)"', fbody)
                fdesc = dm.group(1) if dm else None
                sm = re.search(r"\bsql\s*:\s*\$\{TABLE\}\.([A-Za-z0-9_]+)\s*;;", fbody)
                phys_col = sm.group(1) if sm else fname

                if fkind in ("dimension", "dimension_group"):
                    if re.search(r"primary_key\s*:\s*yes", fbody) and fname != "_dpf_pk":
                        pk_cols.append(phys_col)
                    if fname == "_dpf_pk":
                        for c_m in re.finditer(r"\$\{TABLE\}\.([A-Za-z0-9_]+)", fbody):
                            if c_m.group(1) not in pk_cols:
                                pk_cols.append(c_m.group(1))
                        continue
                    if phys_col not in seen_cols:
                        seen_cols.add(phys_col)
                        cobj: dict[str, Any] = {
                            "name": phys_col,
                            "type": _lkml_to_bq_type(ftype, fkind == "dimension_group"),
                        }
                        if fdesc:
                            cobj["description"] = fdesc
                        cols.append(cobj)
                elif fkind == "measure" and ftype != "count":
                    if phys_col not in seen_cols and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", phys_col):
                        seen_cols.add(phys_col)
                        cols.append({"name": phys_col, "type": "NUMERIC"})
                    additivity = "additive" if ftype in ("sum", None) else (
                        "semi_additive" if ftype == "average" else "non_additive"
                    )
                    if ftype in ("sum", "average") and phys_col == fname:
                        view_measures.append({"name": fname, "additivity": additivity})
                    else:
                        mobj: dict[str, Any] = {
                            "name": fname,
                            "label": fname.replace("_", " ").title(),
                            "type": "simple" if ftype == "sum" else "derived",
                            "model": vname,
                            "expr": phys_col,
                        }
                        if fdesc:
                            mobj["description"] = fdesc
                        metrics.append(mobj)

            if not pk_cols:
                fallback_pk = cols[0]["name"] if cols else "id"
                pk_cols = [fallback_pk]
                report.warn(
                    f"view '{vname}' has no 'primary_key: yes' dimension; defaulting grain_columns to [{fallback_pk}]"
                )
            for pkc in pk_cols:
                if pkc not in seen_cols:
                    cols.insert(0, {"name": pkc, "type": "STRING"})
                    seen_cols.add(pkc)

            inferred_role = "fact" if vname.startswith("fct_") else (
                "dimension" if vname.startswith("dim_") else "business_view"
            )
            tobj: dict[str, Any] = {
                "name": vname,
                "role": inferred_role,
                "grain_statement": f"One row per {', '.join(pk_cols)} in {vname}",
                "grain_columns": pk_cols,
                "history_semantics": "current_only",
                "columns": cols,
            }
            if t_phys != vname:
                tobj["table_name"] = t_phys
            if t_ds != resolved_dataset:
                tobj["dataset"] = t_ds
            if view_measures:
                tobj["attributes"] = {"measures": view_measures}
            tables.append(tobj)

    all_raw_explores = list(model_explores)
    for ef in explore_files:
        txt = ef.read_text(encoding="utf-8")
        for (ename,), ebody in _iter_blocks(txt, _EXPLORE_HDR_RE):
            all_raw_explores.append((ename, ebody))

    known_views = {t["name"] for t in tables}
    explores: list[dict[str, Any]] = []
    seen_explores: set[str] = set()
    for ename, ebody in all_raw_explores:
        if ename in seen_explores:
            continue
        seen_explores.add(ename)
        vm = re.search(r"\b(?:view_name|from)\s*:\s*([A-Za-z0-9_]+)", ebody)
        base_view = vm.group(1) if vm else (ename if ename in known_views else (tables[0]["name"] if tables else ename))
        if base_view not in known_views:
            continue
        joins: list[dict[str, Any]] = []
        for (jname,), jbody in _iter_blocks(ebody, _JOIN_HDR_RE):
            if jname not in known_views:
                continue
            tm = re.search(r"\btype\s*:\s*([A-Za-z0-9_]+)", jbody)
            rm = re.search(r"\brelationship\s*:\s*([A-Za-z0-9_]+)", jbody)
            om = re.search(r"\bsql_on\s*:\s*([^;]+);;", jbody, re.S)
            if om:
                joins.append({
                    "view": jname,
                    "type": tm.group(1) if tm else "left_outer",
                    "relationship": rm.group(1) if rm else "many_to_one",
                    "sql_on": " ".join(om.group(1).split()),
                })
        eobj: dict[str, Any] = {
            "name": ename,
            "from": base_view,
            "label": ename.replace("_", " ").title(),
        }
        if joins:
            eobj["joins"] = joins
        explores.append(eobj)

    if not explores and tables:
        first_v = tables[0]["name"]
        explores.append({
            "name": first_v,
            "from": first_v,
            "label": first_v.replace("_", " ").title(),
        })

    dashboards: list[dict[str, Any]] = []
    for df in dash_files:
        raw_dash = df.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw_dash)
        if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
            report.warn(f"skipping invalid LookML dashboard '{df.name}'")
            continue
        d0 = parsed[0]
        dname = str(d0.get("dashboard") or df.name.removesuffix(".dashboard.lookml")).replace("-", "_")
        dtitle = str(d0.get("title") or dname.replace("_", " ").title())
        for elem in d0.get("elements") or []:
            if elem.get("model"):
                elem["model"] = pid
        for flt in d0.get("filters") or []:
            if flt.get("model"):
                flt["model"] = pid
        rel_path = f"lookml/{dname}.dashboard.lookml"
        write_text(pdir / rel_path, yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True, width=1000))
        dashboards.append({
            "name": dname,
            "title": dtitle,
            "file": rel_path,
        })

    ports: list[dict[str, Any]] = []
    for exp in explores:
        ports.append({
            "name": f"{exp['name']}_explore",
            "type": "looker_explore",
            "explore": exp["name"],
            "access": "looker_model_set",
        })
    for dsh in dashboards:
        ports.append({
            "name": f"{dsh['name']}_dashboard",
            "type": "looker_dashboard",
            "dashboard": dsh["name"],
            "access": "looker_folder_grant",
        })

    sl_block: dict[str, Any] = {
        "targets": ["lookml"],
        "looker": {
            "connection": connection or f"bigquery_{pid}",
            "project_name": pid,
            "auth_mode": "oauth",
        },
        "explores": explores,
    }
    if metrics:
        sl_block["metrics"] = metrics
    if dashboards:
        sl_block["dashboards"] = dashboards

    man: dict[str, Any] = {
        "product_id": pid,
        "version": "0.1.0",
        "status": "prototype",
        "owner": f"{pid}-owner@example.com",
        "domain": domain or "analytics",
        "classification": "INTERNAL",
        "deployment": {
            "gcp_project": resolved_project,
            "region": resolved_region,
            "datasets": {},
        },
        "upstream": [{
            "foundation": f"{pid}_foundation",
            "gcp_project": resolved_project,
            "dataset": resolved_dataset,
            "max_staleness": "PT24H",
            "tables": tables,
        }],
        "output_ports": ports,
        "semantic_layer": sl_block,
    }
    write_text(pdir / "product.yaml", yaml.safe_dump(man, sort_keys=False, allow_unicode=True))
    report.ok(
        f"imported {len(tables)} LookML view(s), {len(explores)} explore(s) and {len(dashboards)} dashboard(s) "
        f"into products/{pid}/product.yaml (run `dpf check {pid} --gate proto` and `dpf generate {pid}`)"
    )
