"""Dataform adapter: renders the engine-neutral plan as a Dataform core 3 repository."""

from __future__ import annotations

from dpf.core import Product
from dpf.graph import ProductGraph
from dpf.generate.plan import INCREMENTAL_MARKER, Action
from dpf.generate.render import is_timestamp, js, marker, project_vars, sub_refs, sub_vars

ROOT = "dataform"


def _sql(a: Action) -> str:
    sql = sub_refs(a.sql, lambda n: f'${{ref("{n}")}}')
    sql = sub_vars(sql, lambda v: f"${{dataform.projectConfig.vars.{v}}}")
    if INCREMENTAL_MARKER in sql:
        pred = sub_vars(a.incremental_predicate or "", lambda v: f"${{dataform.projectConfig.vars.{v}}}")
        sql = sql.replace(INCREMENTAL_MARKER, f"${{when(incremental(), `WHERE {pred}`)}}" if pred else "")
    return sql.rstrip() + "\n"


def _config(a: Action) -> str:
    lines: list[str] = []
    kind = {"materialized_view": "view"}.get(a.kind, a.kind)
    lines.append(f"  type: {js(kind)},")
    if a.kind == "declaration":
        lines.append(f"  schema: dataform.projectConfig.vars.{a.dataset}_dataset,")
        lines.append(f"  name: {js(a.name)},")
    elif a.kind != "assertion":
        lines.append(f"  schema: dataform.projectConfig.vars.{a.dataset}_dataset,")
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


def sqlx(a: Action) -> str:
    if a.kind == "declaration":
        cfg = _config(a).replace("config {\n", "config {\n  " + marker(a.header, "//") + "\n", 1)
        return cfg
    hdr = dict(a.header)
    if a.kind == "assertion" and a.severity != "block":
        hdr["severity"] = a.severity
    return _config(a) + "\n" + marker(hdr) + "\n" + _sql(a)


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


def render(p: Product, g: ProductGraph, actions: list[Action]) -> dict[str, str]:
    files = {f"{ROOT}/workflow_settings.yaml": workflow_settings(p)}
    for a in actions:
        files[f"{ROOT}/definitions/{a.subdir}/{a.name}.sqlx"] = sqlx(a)
    return files
