"""Import an interactive Dataform / Data Engineering Agent workspace into a `status: prototype` DPF product."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from dpf.core import Report, Workspace, load_yaml, write_text
from dpf.design import _blank_literals_and_parens
from dpf.generate.plan import INCREMENTAL_MARKER, MODEL_TARGET_MARKER
from dpf.generate.render import snake_id
from dpf.graph import body_refs, select_columns, strip_sql_comments

DF_REF = re.compile(
    r"\$\{\s*ref\(\s*(?:['\"`][A-Za-z0-9_-]+['\"`]\s*,\s*)?['\"`]([A-Za-z0-9_]+)['\"`]\s*\)\s*\}"
)
DF_VAR = re.compile(r"\$\{\s*dataform\.projectConfig\.vars\.([A-Za-z0-9_]+)\s*\}")
DF_SELF = re.compile(r"\$\{\s*self\(\s*\)\s*\}")
DF_WHEN_INC = re.compile(r"\$\{\s*when\(\s*incremental\(\s*\)\s*,.*?\)\s*\}", re.S)


def _extract_block(text: str, keyword: str) -> tuple[str | None, str]:
    """Extract the first top-level `<keyword> { ... }` block and return `(inner, remaining_text)`."""
    m = re.search(rf"(?:^|\n)\s*{keyword}\s*\{{", text)
    if not m:
        return None, text
    brace_open = text.find("{", m.start())
    depth, i, n = 1, brace_open + 1, len(text)
    while i < n and depth > 0:
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
            i = j + 1
            continue
        if text[i:i + 2] == "//":
            nl = text.find("\n", i + 2)
            i = n if nl < 0 else nl + 1
            continue
        if text[i:i + 2] == "/*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    inner = text[brace_open + 1:i - 1]
    rest = (text[:m.start()] + "\n" + text[i:]).strip()
    return inner, rest


def _js_str(cfg: str, key: str) -> str | None:
    m = re.search(rf"\b{key}\s*:\s*(['\"`])(.*?)\1", cfg, re.S)
    return m.group(2).strip() if m else None


def _js_bool(cfg: str, key: str) -> bool:
    m = re.search(rf"\b{key}\s*:\s*(true|false)\b", cfg, re.I)
    return bool(m and m.group(1).lower() == "true")


def _js_list(cfg: str, key: str) -> list[str]:
    m = re.search(rf"\b{key}\s*:\s*\[(.*?)\]", cfg, re.S)
    if m:
        return [s.strip() for _, s in re.findall(r"(['\"`])(.*?)\1", m.group(1)) if s.strip()]
    single = _js_str(cfg, key)
    return [single] if single else []


def _parse_sqlx(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    cfg_text, body = _extract_block(raw, "config")
    cfg_text = cfg_text or ""
    stripped_blocks = []
    for blk in ("js", "pre_operations", "post_operations"):
        while True:
            inner, body = _extract_block(body, blk)
            if inner is None:
                break
            if inner.strip():
                stripped_blocks.append(blk)
    bq_inner, _ = _extract_block("bigquery " + ("{" + cfg_text.split("bigquery", 1)[1].split("{", 1)[1]
                                                if re.search(r"\bbigquery\s*:\s*\{", cfg_text) else ""), "bigquery")
    assert_inner, _ = _extract_block("assertions " + ("{" + cfg_text.split("assertions", 1)[1].split("{", 1)[1]
                                                      if re.search(r"\bassertions\s*:\s*\{", cfg_text) else ""), "assertions")
    kind = (_js_str(cfg_text, "type") or "view").lower()
    name = _js_str(cfg_text, "name") or path.stem
    part = _js_str(bq_inner or "", "partitionBy")
    if part:
        dm = re.match(r"^(?:DATE|TIMESTAMP_TRUNC)\(\s*([A-Za-z_][A-Za-z0-9_]*)", part, re.I)
        if dm:
            part = dm.group(1)
    unique_key = _js_list(cfg_text, "uniqueKey") or _js_list(assert_inner or "", "uniqueKey")
    non_null = _js_list(assert_inner or "", "nonNull")
    return {
        "path": path,
        "name": snake_id(name),
        "orig_name": name,
        "kind": kind,
        "description": _js_str(cfg_text, "description"),
        "materialized": _js_bool(cfg_text, "materialized"),
        "unique_key": unique_key,
        "non_null": non_null,
        "partition_by": part,
        "cluster_by": _js_list(bq_inner or "", "clusterBy"),
        "body": body.strip(),
        "stripped_blocks": stripped_blocks,
    }


def _neutralise_sql(sql: str, ref_map: dict[str, str]) -> str:
    out = DF_REF.sub(lambda m: f"{{{{ ref('{ref_map.get(m.group(1), snake_id(m.group(1)))}') }}}}", sql)
    out = DF_VAR.sub(lambda m: f"{{{{ var('{m.group(1)}') }}}}", out)
    out = DF_SELF.sub(MODEL_TARGET_MARKER, out)
    out = DF_WHEN_INC.sub(INCREMENTAL_MARKER, out)
    return out.strip() + "\n"


def _ensure_staging_columns(sql: str, nk: list[str]) -> tuple[str, list[str]]:
    """Ensure a staging SELECT produces natural_key, source_modified_ts and _ingest_ts."""
    cols = select_columns(sql)
    if cols is None:
        # Unreadable projection (e.g. SELECT *): wrap in explicit minimal staging columns if needed.
        key = nk[0] if nk else "id"
        wrapped = (
            "-- TODO(dpf-import): replace explicit key projection with typed source columns\n"
            f"SELECT\n  {key},\n  CURRENT_TIMESTAMP() AS source_modified_ts,\n  CURRENT_TIMESTAMP() AS _ingest_ts\n"
            f"FROM (\n  {sql.strip()}\n)\n"
        )
        return wrapped, [key]
    extras = []
    for k in nk:
        if k not in cols:
            extras.append(f"  {k}")
            cols.append(k)
    if "source_modified_ts" not in cols:
        ts_cand = next((c for c in cols if c in ("updated_at", "last_modified_ts", "modified_at", "created_at")), None)
        expr = f"CAST({ts_cand} AS TIMESTAMP)" if ts_cand else "CURRENT_TIMESTAMP()"
        extras.append(f"  {expr} AS source_modified_ts")
    if "_ingest_ts" not in cols:
        extras.append("  CURRENT_TIMESTAMP() AS _ingest_ts")
    if extras:
        # Insert extra columns immediately before top-level FROM.
        text = strip_sql_comments(sql)
        depth, i, n, from_pos = 0, 0, len(text), -1
        while i < n:
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth = max(0, depth - 1)
            elif c in ("'", '"', "`"):
                j = text.find(c, i + 1)
                i = n if j < 0 else j
            elif depth == 0 and text[i:i + 4].upper() == "FROM" and (i == 0 or not text[i - 1].isalnum()) \
                    and (i + 4 >= n or not text[i + 4].isalnum()):
                from_pos = i
            i += 1
        if from_pos > 0:
            # Locate corresponding FROM in original sql from the end.
            m = list(re.finditer(r"\bFROM\b", sql, re.I))
            if m:
                pos = m[-1].start()
                head = sql[:pos].rstrip()
                tail = sql[pos:]
                sql = head + ",\n" + ",\n".join(extras) + "\n" + tail
    if not nk:
        nk = [next((c for c in cols if c not in ("source_modified_ts", "_ingest_ts", "_batch_id")), cols[0])]
    top = _blank_literals_and_parens(sql)
    where_m = re.search(r"\bWHERE\b(.*)$", top, re.I | re.S)
    if where_m and not re.match(r"^\s*TRUE\s*;?\s*$", where_m.group(1), re.I):
        sql = "-- dpf: allow_staging_filter=true reason=imported_from_dataform\n" + sql
    return sql.strip() + "\n", nk


def _infer_columns_from_consumers(entity_ref: str, sql_bodies: list[str]) -> list[str]:
    """Guess referenced columns in consumer SQL bodies when synthesising a pass-through staging model."""
    cols: list[str] = []
    for sql in sql_bodies:
        if entity_ref not in sql:
            continue
        for c in select_columns(sql) or []:
            if c not in cols and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", c):
                cols.append(c)
    return cols or ["id"]


def import_dataform(
    ws: Workspace,
    pid: str,
    src: Path,
    report: Report,
    *,
    domain: str | None = None,
    project: str | None = None,
    region: str | None = None,
    source_id: str | None = None,
) -> None:
    report.head(f"proto · import-dataform — {pid}", gate="proto")
    pdir = ws.root / "products" / pid
    if (pdir / "product.yaml").exists():
        report.fail(f"products/{pid}/product.yaml already exists")
        return
    src = src.resolve()
    if not src.exists():
        report.fail(f"source directory {src} does not exist")
        return
    defs_dir = (src / "definitions") if (src / "definitions").is_dir() else src
    sqlx_files = sorted(defs_dir.rglob("*.sqlx"))
    if not sqlx_files:
        report.fail(f"no .sqlx files found under {defs_dir}")
        return

    wf = load_yaml(src / "workflow_settings.yaml") if (src / "workflow_settings.yaml").exists() else {}
    if not wf and (src / "dataform.json").exists():
        wf = json.loads((src / "dataform.json").read_text(encoding="utf-8"))
    gcp_project = project or wf.get("defaultProject") or wf.get("defaultDatabase") or "example-dpf-dev"
    gcp_region = region or wf.get("defaultLocation") or "europe-west2"
    sys_id = snake_id(source_id or f"{pid}_src")

    parsed = [_parse_sqlx(f) for f in sqlx_files]
    for item in parsed:
        if item["stripped_blocks"]:
            report.warn(f"{item['path'].name}: stripped {', '.join(item['stripped_blocks'])} block(s) during import")

    declarations = [x for x in parsed if x["kind"] == "declaration"]
    models = [x for x in parsed if x["kind"] in ("view", "table", "incremental")]
    if not models:
        report.fail(f"no table, view or incremental .sqlx actions found under {defs_dir}")
        return

    entities: list[str] = []
    ref_map: dict[str, str] = {}
    for d in declarations:
        ent = d["name"].removeprefix("raw_")
        if ent not in entities:
            entities.append(ent)
        ref_map[d["orig_name"]] = f"raw_{ent}"
        ref_map[d["name"]] = f"raw_{ent}"
    model_names = {m["orig_name"]: m["name"] for m in models}
    ref_map.update(model_names)

    # Discover undeclared ${ref("...")} targets as raw entities.
    for m in models:
        for r in DF_REF.findall(m["body"]):
            if r not in ref_map:
                ent = snake_id(r).removeprefix("raw_")
                if ent not in entities:
                    entities.append(ent)
                ref_map[r] = f"raw_{ent}"
    if not entities:
        entities = ["records"]

    staging_items = []
    gold_items = []
    for m in models:
        neutral = _neutralise_sql(m["body"], ref_map)
        refs = body_refs(neutral)
        in_stg_dir = "staging" in {p.lower() for p in m["path"].relative_to(defs_dir).parts[:-1]}
        reads_only_raw = bool(refs) and all(r.startswith("raw_") for r in refs)
        if (m["name"].startswith("stg_") or in_stg_dir) and reads_only_raw:
            staging_items.append((m, neutral))
        else:
            gold_items.append((m, neutral))

    staging_by_raw: dict[str, str] = {}
    staging_models: list[dict] = []
    quality_rules: list[dict] = []
    q_idx = 1

    for m, neutral in staging_items:
        fixed_sql, nk = _ensure_staging_columns(neutral, list(m["unique_key"]))
        write_text(pdir / "sql" / f"{m['name']}.sql", fixed_sql)
        for r in body_refs(fixed_sql):
            if r.startswith("raw_"):
                staging_by_raw.setdefault(r, m["name"])
        s_entry = {
            "name": m["name"],
            "role": "staging",
            "grain_statement": m["description"] if m["description"] and len(m["description"]) >= 10
            else f"One row per {', '.join(nk)} in {m['name']}",
            "grain_columns": nk,
            "natural_key": nk,
            "dedupe_order": ["source_modified_ts DESC", "_ingest_ts DESC"],
            "history_semantics": "current_only",
            "materialisation": "view",
            "body": f"sql/{m['name']}.sql",
        }
        staging_models.append(s_entry)
        for col in m["non_null"]:
            quality_rules.append({
                "id": f"QR-{q_idx}",
                "model": m["name"],
                "type": "not_null",
                "column": col,
                "severity": "warn",
                "on_fail": "quarantine",
            })
            q_idx += 1

    # Synthesise staging pass-throughs for any raw_* read directly by a gold model (methodology rule:
    # only staging models may read raw relations).
    gold_neutral_bodies = [sql for _, sql in gold_items]
    for ent in entities:
        raw_name = f"raw_{ent}"
        if raw_name in staging_by_raw:
            continue
        if not gold_items or any(raw_name in body_refs(sql) for _, sql in gold_items):
            stg_name = f"stg_{ent}"
            cols = _infer_columns_from_consumers(raw_name, gold_neutral_bodies)
            nk = [cols[0]]
            proj = ",\n".join([f"  {c}" for c in cols] + [
                "  CURRENT_TIMESTAMP() AS source_modified_ts",
                "  CURRENT_TIMESTAMP() AS _ingest_ts",
            ])
            stg_sql = (
                "-- Synthesised staging projection from Dataform import (ADR-017).\n"
                f"SELECT\n{proj}\nFROM {{{{ ref('{raw_name}') }}}}\n"
            )
            write_text(pdir / "sql" / f"{stg_name}.sql", stg_sql)
            staging_by_raw[raw_name] = stg_name
            staging_models.append({
                "name": stg_name,
                "role": "staging",
                "grain_statement": f"One row per {nk[0]} in {ent}",
                "grain_columns": nk,
                "natural_key": nk,
                "dedupe_order": ["source_modified_ts DESC", "_ingest_ts DESC"],
                "history_semantics": "current_only",
                "materialisation": "view",
                "body": f"sql/{stg_name}.sql",
            })

    gold_models: list[dict] = []
    for m, neutral in gold_items:
        for raw_name, stg_name in staging_by_raw.items():
            neutral = re.sub(
                rf"\{{\{{\s*ref\(\s*['\"]{re.escape(raw_name)}['\"]\s*\)\s*\}}\}}",
                f"{{{{ ref('{stg_name}') }}}}",
                neutral,
            )
        cols = select_columns(neutral) or []
        grain = list(m["unique_key"]) or ([cols[0]] if cols else ["id"])
        if m["kind"] == "view" and m["materialized"]:
            role, mat = "materialised_view", "materialized_view"
        elif m["kind"] == "incremental":
            role, mat = "business_view", "incremental_table"
        elif m["kind"] == "table":
            role, mat = "business_view", "table"
        else:
            role, mat = "business_view", "view"
        write_text(pdir / "sql" / f"{m['name']}.sql", neutral)
        g_entry: dict = {
            "name": m["name"],
            "role": role,
            "grain_statement": m["description"] if m["description"] and len(m["description"]) >= 10
            else f"One row per {', '.join(grain)} in {m['name']}",
            "grain_columns": grain,
            "history_semantics": "current_only",
            "materialisation": mat,
            "body": f"sql/{m['name']}.sql",
        }
        if m["partition_by"] and (not cols or m["partition_by"] in cols):
            g_entry["partition_by"] = m["partition_by"]
        if m["cluster_by"]:
            g_entry["cluster_by"] = m["cluster_by"]
        if mat == "incremental_table":
            g_entry["natural_key"] = grain
        gold_models.append(g_entry)
        for col in m["non_null"]:
            quality_rules.append({
                "id": f"QR-{q_idx}",
                "model": m["name"],
                "type": "not_null",
                "column": col,
                "severity": "warn",
                "on_fail": "fail",
            })
            q_idx += 1

    # If the workspace only contained stg_* models, scaffold a minimal gold consumption view over the first one.
    if not gold_models:
        first_stg = staging_models[0]
        obt_name = f"obt_{pid}"
        nk_cols = ",\n  ".join(first_stg["grain_columns"])
        write_text(pdir / "sql" / f"{obt_name}.sql",
                   f"SELECT\n  {nk_cols},\n  source_modified_ts\nFROM {{{{ ref('{first_stg['name']}') }}}}\n")
        gold_models.append({
            "name": obt_name,
            "role": "business_view",
            "grain_statement": f"One row per {', '.join(first_stg['grain_columns'])} in {pid}",
            "grain_columns": list(first_stg["grain_columns"]),
            "history_semantics": "current_only",
            "materialisation": "view",
            "body": f"sql/{obt_name}.sql",
        })

    referenced_in_gold = {
        r for gm in gold_models
        for r in body_refs((pdir / gm["body"]).read_text(encoding="utf-8"))
    }
    leaf_gold = [gm for gm in gold_models if gm["name"] not in referenced_in_gold] or gold_models
    port_type_map = {
        "view": "bigquery_view",
        "table": "bigquery_table",
        "incremental_table": "bigquery_table",
        "materialized_view": "materialized_view",
    }
    output_ports = [{
        "name": f"{gm['name']}_port",
        "model": gm["name"],
        "type": port_type_map.get(gm["materialisation"], "bigquery_view"),
        "access": "dataset_grant",
    } for gm in leaf_gold]

    man = {
        "product_id": pid,
        "version": "0.1.0",
        "status": "prototype",
        "owner": f"{pid}-owner@example.com",
        "domain": domain or "commerce",
        "classification": "INTERNAL",
        "deployment": {
            "gcp_project": gcp_project,
            "region": gcp_region,
            "datasets": {
                "raw": f"{pid}_raw",
                "staging": f"{pid}_staging",
                "gold": f"{pid}_gold",
                "assertions": f"{pid}_assertions",
                "control": f"{pid}_control",
            },
        },
        "sources": [{
            "system_id": sys_id,
            "engine": "postgres",
            "capture_mode": "watermark",
            "watermark_column": "updated_at",
            "schedule": "0 * * * *",
            "entities": entities,
        }],
        "layers": {
            "raw": {"storage": "bigquery_native"},
            "staging": {
                "methodology": None,
                "engine": "dataform",
                "storage": "bigquery_native",
                "models": staging_models,
            },
            "gold": {
                "methodology": "direct",
                "engine": "dataform",
                "storage": "bigquery_native",
                "models": gold_models,
            },
        },
        "output_ports": output_ports,
        "quality": {"gate_behaviour": "warn", "rules": quality_rules},
        "orchestration": {
            "engine": "dataform",
            "timezone": "UTC",
            "schedules": [{"id": "hourly", "cron": "15 * * * *"}],
        },
    }
    write_text(pdir / "product.yaml", yaml.safe_dump(man, sort_keys=False))
    report.ok(
        f"imported {len(staging_models)} staging and {len(gold_models)} gold model(s) from {src} into "
        f"products/{pid}/ (run `dpf check {pid} --gate proto` and `dpf proto promote {pid}`)"
    )
