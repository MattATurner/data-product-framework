"""dbt adapter: renders the same engine-neutral plan as a dbt-bigquery project.

Parity with the Dataform adapter: identical SQL and semantic models; raw relations become
sources; blocking checks become singular tests that `dbt build` runs after the model they
depend on, so a failure skips every downstream model (the reject-gate test also depends on
the staging model itself, not only on its reject view, for exactly that reason).
"""

from __future__ import annotations

import yaml

from dpf.core import Product
from dpf.graph import ProductGraph
from dpf.generate.plan import INCREMENTAL_MARKER, Action
from dpf.generate.render import is_timestamp, marker, project_vars, py_list, sub_refs, timezone

ROOT = "dbt"
MATERIALIZED = {"view": "view", "table": "table", "incremental": "incremental",
                "materialized_view": "materialized_view"}


def _ref(g: ProductGraph, name: str) -> str:
    node = g.get(name)
    if node is not None and node.kind == "raw":
        return f"{{{{ source('{node.source}', '{name}') }}}}"
    return f"{{{{ ref('{name}') }}}}"


def _config(a: Action) -> str:
    items = [f"materialized='{MATERIALIZED[a.kind]}'", f"schema=var('{a.dataset}_dataset')"]
    if a.tags:
        items.append(f"tags={py_list(a.tags)}")
    if a.kind == "incremental":
        items += ["incremental_strategy='merge'", f"unique_key={py_list(a.unique_key)}"]
    if a.partition_by and a.kind in ("table", "incremental", "materialized_view"):
        dtype = "timestamp" if is_timestamp(a.partition_by) else "date"
        gran = ", 'granularity': 'day'" if dtype == "timestamp" else ""
        items.append(f"partition_by={{'field': '{a.partition_by}', 'data_type': '{dtype}'{gran}}}")
    if a.cluster_by and a.kind in ("table", "incremental", "materialized_view"):
        items.append(f"cluster_by={py_list(a.cluster_by)}")
    if a.kind == "incremental" and a.incremental_predicate:
        items.append(f'incremental_predicates=["DBT_INTERNAL_DEST.{a.incremental_predicate}"]')
    if a.kind != "view":
        items.append("persist_docs={'relation': true, 'columns': true}")
    return "{{ config(\n    " + ",\n    ".join(items) + "\n) }}\n"


def model_sql(g: ProductGraph, a: Action) -> str:
    sql = sub_refs(a.sql, lambda n: _ref(g, n))
    if INCREMENTAL_MARKER in sql:
        pred = a.incremental_predicate
        sql = sql.replace(INCREMENTAL_MARKER, f"{{% if is_incremental() %}}WHERE {pred}{{% endif %}}" if pred else "")
    return _config(a) + marker(a.header) + "\n" + sql.rstrip() + "\n"


def test_sql(g: ProductGraph, a: Action) -> str:
    cfg = []
    if a.severity == "warn":
        cfg.append("severity='warn'")
    if a.tags:
        cfg.append(f"tags={py_list(a.tags)}")
    hdr = dict(a.header)
    if a.severity != "block":
        hdr["severity"] = a.severity
    out = ("{{ config(" + ", ".join(cfg) + ") }}\n" if cfg else "") + marker(hdr) + "\n"
    if a.case_id and a.case_id.startswith("reject_gate:") and a.model:
        out += f"-- depends_on: {{{{ ref('{a.model}') }}}}\n"
    return out + sub_refs(a.sql, lambda n: _ref(g, n)).rstrip() + "\n"


def project_yml(p: Product) -> str:
    ds = (p.manifest.get("deployment") or {}).get("datasets") or {}
    doc = {
        "name": p.id,
        "version": str(p.manifest.get("version")),
        "config-version": 2,
        "require-dbt-version": ">=1.8.0",
        "profile": f"dpf_{p.id}",
        "model-paths": ["models"],
        "test-paths": ["tests"],
        "macro-paths": ["macros"],
        "vars": project_vars(p),
        "data_tests": {p.id: {"+store_failures": True, "+schema": ds.get("assertions", "dpf_assertions")}},
    }
    head = (marker({"product": p.id, "engine": "dbt", "implements": "generate-artefacts"}, "#") + "\n"
            "# policy_tag_* vars are REQUIRED before building tables with tagged columns: pass them with\n"
            "# --vars from `terraform output policy_tags`. An empty tag fails the build rather than\n"
            "# publishing unprotected columns.\n")
    return head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def sources_yml(p: Product, g: ProductGraph, actions: list[Action]) -> str:
    by_source: dict[str, list[Action]] = {}
    for a in actions:
        if a.kind == "declaration":
            by_source.setdefault(g.nodes[a.name].source, []).append(a)
    doc = {"version": 2, "sources": [
        {"name": src, "description": f"Raw, append-only landing of source system {src}.",
         "schema": "{{ var('raw_dataset') }}",
         "tables": [{"name": a.name, "description": a.description} for a in acts]}
        for src, acts in by_source.items()]}
    return marker({"product": p.id, "implements": "land-immutable-raw"}, "#") + "\n" + \
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def schema_yml(p: Product, actions: list[Action]) -> str:
    models = []
    for a in actions:
        if a.kind in ("declaration", "assertion"):
            continue
        entry = {"name": a.name, "description": a.description}
        if a.columns and a.kind in ("table", "incremental"):
            entry["columns"] = [{"name": c, "description": s["description"],
                                 "policy_tags": [f"{{{{ var('{s['policy_tag_var']}') }}}}"]}
                                for c, s in a.columns.items()]
        models.append(entry)
    return marker({"product": p.id, "implements": "generate-artefacts"}, "#") + "\n" + \
        yaml.safe_dump({"version": 2, "models": models}, sort_keys=False, allow_unicode=True, width=1000)


def profiles_example(p: Product) -> str:
    dep = p.manifest.get("deployment") or {}
    doc = {f"dpf_{p.id}": {"target": "dev", "outputs": {"dev": {
        "type": "bigquery", "method": "oauth", "project": dep.get("gcp_project"),
        "dataset": (dep.get("datasets") or {}).get("staging"), "location": dep.get("region"),
        "threads": 4, "job_execution_timeout_seconds": 900}}}}
    return "# Copy to ~/.dbt/profiles.yml (or set DBT_PROFILES_DIR). Generated by dpf.\n" + \
        yaml.safe_dump(doc, sort_keys=False)


GENERATE_SCHEMA = """{#- dpf: the dataset named in each model's config is used verbatim (no target prefix). -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
"""


def orchestration_md(p: Product) -> str:
    orch = p.manifest.get("orchestration") or {}
    tz = timezone(p)
    tags = [f"policy_tag_{t['tag']}" for t in (p.manifest.get("governance") or {}).get("policy_tags", []) or []]
    vars_arg = (" --vars '{" + ", ".join(f"{t}: <terraform output>" for t in tags) + "}'") if tags else ""
    lines = [f"# Orchestration — {p.id} (dbt)", "",
             "dbt has no scheduler of its own. Run each schedule below from Cloud Composer, Cloud Run jobs "
             "or Workflows with the given cron, in the business timezone. `dbt build` runs every model's tests "
             "straight after the model and skips everything downstream of a failed blocking test; acceptance "
             "tests are excluded from scheduled runs.", "",
             "| Schedule | Cron | Timezone | Command |", "|---|---|---|---|"]
    for s in orch.get("schedules", []) or []:
        lines.append(f"| `{s['id']}` | `{s['cron']}` | {tz} | `dbt build --select tag:{s['id']} --exclude tag:acceptance{vars_arg}` |")
    lines += ["", "Acceptance (against the seeded fixture, never scheduled):", "",
              "```bash", f"dbt build --exclude tag:acceptance{vars_arg}", "dbt test --select tag:acceptance", "```", "",
              "Warn-level tests report but never skip downstream models.", ""]
    return "\n".join(lines)


def render(p: Product, g: ProductGraph, actions: list[Action]) -> dict[str, str]:
    files = {
        f"{ROOT}/dbt_project.yml": project_yml(p),
        f"{ROOT}/profiles.yml.example": profiles_example(p),
        f"{ROOT}/macros/generate_schema_name.sql": GENERATE_SCHEMA,
        f"{ROOT}/models/sources.yml": sources_yml(p, g, actions),
        f"{ROOT}/models/schema.yml": schema_yml(p, actions),
        f"{ROOT}/orchestration.md": orchestration_md(p),
    }
    for a in actions:
        if a.kind == "declaration":
            continue
        if a.kind == "assertion":
            files[f"{ROOT}/tests/{a.name}.sql"] = test_sql(g, a)
        else:
            files[f"{ROOT}/models/{a.subdir}/{a.name}.sql"] = model_sql(g, a)
    return files
