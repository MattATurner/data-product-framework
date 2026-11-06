"""Dataform adapter: renders the engine-neutral plan as a Dataform core 3 repository."""

from __future__ import annotations

from dpf.core import Product
from dpf.graph import ProductGraph
from dpf.generate.plan import INCREMENTAL_MARKER, MODEL_TARGET_MARKER, Action
from dpf.generate.render import is_timestamp, js, marker, project_vars, snake_id, sub_refs, sub_vars, timezone

ROOT = "dataform"


def _sql(a: Action) -> str:
    sql = sub_refs(a.sql, lambda n: f'${{ref("{n}")}}')
    sql = sub_vars(sql, lambda v: f"${{dataform.projectConfig.vars.{v}}}")
    if MODEL_TARGET_MARKER in sql:
        sql = sql.replace(MODEL_TARGET_MARKER, "${self()}")
    if INCREMENTAL_MARKER in sql:
        pred = sub_vars(a.incremental_predicate or "", lambda v: f"${{dataform.projectConfig.vars.{v}}}")
        sql = sql.replace(INCREMENTAL_MARKER, f"${{when(incremental(), `WHERE {pred}`)}}" if pred else "")
    return sql.rstrip() + "\n"


def _config(a: Action, p: Product | None = None) -> str:
    lines: list[str] = []
    kind = {"materialized_view": "view"}.get(a.kind, a.kind)
    lines.append(f"  type: {js(kind)},")
    if a.kind == "declaration":
        if a.database:
            lines.append(f"  database: {js(a.database)},")
        schema_expr = js(a.schema_literal) if a.schema_literal else f"dataform.projectConfig.vars.{a.dataset}_dataset"
        lines.append(f"  schema: {schema_expr},")
        lines.append(f"  name: {js(a.phys_name or a.name)},")
    elif a.kind != "assertion":
        lines.append(f"  schema: dataform.projectConfig.vars.{a.dataset}_dataset,")
    if a.kind == "operations":
        lines.append("  hasOutput: true,")
    if a.kind == "materialized_view":
        lines.append("  materialized: true,")
    lines.append(f"  description: {js(a.description)},")
    if a.tags:
        lines.append(f"  tags: {js(a.tags)},")
    if a.dependencies:
        lines.append(f"  dependencies: {js(a.dependencies)},")
    if a.kind == "incremental" and a.unique_key:
        lines.append(f"  uniqueKey: {js(a.unique_key)},")
    bq = []
    if a.partition_by and a.kind in ("table", "incremental", "materialized_view"):
        part = f"DATE({a.partition_by})" if is_timestamp(a.partition_by) else a.partition_by
        bq.append(f"    partitionBy: {js(part)}")
    if a.cluster_by and a.kind in ("table", "incremental", "materialized_view"):
        bq.append(f"    clusterBy: {js(a.cluster_by)}")
    if a.kind == "incremental" and a.incremental_predicate and a.partition_by:
        bq.append(f"    updatePartitionFilter: {js(a.incremental_predicate)}")
    if p is not None and a.kind in ("table", "incremental"):
        status = snake_id(str(p.manifest.get("status") or "draft"))[:63]
        layer = snake_id(a.layer or a.dataset)[:63]
        prod = snake_id(p.id)[:63]
        bq.append(
            "    labels: {\n"
            f"      dpf_product: {js(prod)},\n"
            f"      dpf_layer: {js(layer)},\n"
            f"      dpf_status: {js(status)}\n"
            "    }"
        )
    if bq:
        lines.append("  bigquery: {\n" + ",\n".join(bq) + "\n  },")
    if a.columns and a.kind in ("table", "incremental"):
        cols = []
        for col, spec in a.columns.items():
            var = f"dataform.projectConfig.vars.{spec['policy_tag_var']}"
            cols.append(f"    {col}: {{\n      description: {js(spec['description'])},\n"
                        f"      bigqueryPolicyTags: {var} ? [{var}] : []\n    }}")
        lines.append("  columns: {\n" + ",\n".join(cols) + "\n  },")
    lines[-1] = lines[-1].rstrip(",")
    return "config {\n" + "\n".join(lines) + "\n}\n"


def sqlx(a: Action, p: Product | None = None) -> str:
    if a.kind == "declaration":
        cfg = _config(a, p).replace("config {\n", "config {\n  " + marker(a.header, "//") + "\n", 1)
        return cfg
    hdr = dict(a.header)
    if a.kind == "assertion" and a.severity != "block":
        hdr["severity"] = a.severity
    return _config(a, p) + "\n" + marker(hdr) + "\n" + _sql(a)


def workflow_settings(p: Product) -> str:
    dep = p.manifest.get("deployment") or {}
    ds = dep.get("datasets") or {}
    lines = [
        marker({"product": p.id, "engine": "dataform", "implements": "generate-artefacts"}, "#"),
        "# Compilation variables are strings. policy_tag_* are injected by the release configuration",
        "# (Terraform output); left empty, a developer workspace compiles without column policy tags.",
        f"defaultProject: {dep.get('gcp_project')}",
        f"defaultLocation: {dep.get('region')}",
        f"defaultDataset: {ds.get('staging')}",
        f"defaultAssertionDataset: {ds.get('assertions', 'dpf_assertions')}",
        "dataformCoreVersion: 3.0.0",
        "vars:",
    ]
    for k, v in project_vars(p).items():
        lines.append(f"  {k}: {js(v)}")
    return "\n".join(lines) + "\n"


def gemini_md(p: Product, g: ProductGraph) -> str:
    man = p.manifest
    tz = timezone(p)
    lines = [
        f"<!-- dpf: product={p.id} engine=dataform implements=generate-artefacts adr=ADR-017 -->",
        f"# Data Engineering Agent Instructions — `{p.id}`",
        "",
        f"This Dataform repository is deterministically generated by the **Data Product Framework (`dpf`)** "
        f"from `products/{p.id}/product.yaml` (`version: {man.get('version')}`, `status: {man.get('status')}`, "
        f"`domain: {man.get('domain')}`, `business_timezone: {tz}`).",
        "",
        "## Mandatory Guardrails (ADR-017)",
        "",
        "1. **Do not hand-edit `definitions/` or `workflow_settings.yaml`.** Every `.sqlx` file here is compiler "
        "output bound to a `MANIFEST.json` build digest and verified against `tests/golden/`. Direct console "
        "commits drift from Terraform IAM, policy tags, Knowledge Catalog scans, and G4 test specs.",
        f"2. **Author SQL upstream in `products/{p.id}/sql/*.sql`.** When drafting or repairing transformation "
        "SQL, output engine-neutral `SELECT` queries using `{{ ref('model_name') }}` and `{{ var('var_name') }}` "
        "(never `${ref(...)}`, `${self()}`, or `${when(...)}`), then run `dpf generate "
        f"{p.id}`.",
        "3. **Never drop bad rows silently in staging.** Do not add top-level `WHERE` or `QUALIFY` clauses to "
        "`role: staging` SQL bodies to filter out nulls, invalid values, or duplicates. `dpf` wraps staging "
        "bodies in `<model>__candidates`, deduplicates by `natural_key` / `dedupe_order`, and routes failing rows "
        "from `quality.rules` to `<model>_rejects`.",
        "4. **Sandbox exploration intake.** If you prototype new `.sqlx` actions in an isolated sandbox "
        f"workspace, import them back into DPF with `dpf proto import-dataform <product> --from <dir>`.",
        "",
        "## Declared Model Contracts",
        "",
        "| Layer | Model | Role | Grain Columns | Natural Key | Authored Body |",
        "|---|---|---|---|---|---|",
    ]
    for n in g.models:
        m = n.model
        grain = ", ".join(f"`{c}`" for c in (m.get("grain_columns") or [])) or "—"
        nk = ", ".join(f"`{c}`" for c in (m.get("natural_key") or [])) or "—"
        body = f"`products/{p.id}/{m['body']}`" if m.get("body") else "*(generated by pack)*"
        lines.append(f"| `{n.layer}` | `{n.name}` | `{n.role}` | {grain} | {nk} | {body} |")
    return "\n".join(lines) + "\n"


def render(p: Product, g: ProductGraph, actions: list[Action]) -> dict[str, str]:
    files = {
        f"{ROOT}/GEMINI.md": gemini_md(p, g),
        f"{ROOT}/workflow_settings.yaml": workflow_settings(p),
    }
    for a in actions:
        files[f"{ROOT}/definitions/{a.subdir}/{a.name}.sqlx"] = sqlx(a, p)
    return files
