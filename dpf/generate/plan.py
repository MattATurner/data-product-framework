"""Engine-neutral render plan: the actions every engine adapter renders.

SQL is written once, engine-neutrally, with `{{ ref('x') }}` and `{{ var('x') }}`; the
Dataform and dbt adapters translate those, plus the incremental marker, into their own
syntax. Generated roles (staging wrapper, Type 1/2 dimensions, calendar, transaction fact)
are built here from their declarations; business roles use the authored body verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dpf.core import Product
from dpf.graph import ProductGraph, body_refs
from dpf.generate.testspec import action_name, quality_condition

INCREMENTAL_MARKER = "/* dpf:incremental */"
LOW_TS = "TIMESTAMP '1900-01-01 00:00:00+00'"
HIGH_TS = "TIMESTAMP '9999-12-31 00:00:00+00'"


@dataclass
class Action:
    name: str
    kind: str                       # declaration | view | table | incremental | materialized_view | assertion
    dataset: str                    # deployment.datasets key
    subdir: str                     # sources | staging | silver | gold | assertions
    sql: str = ""
    model: str | None = None        # the declared model (or raw relation) this action realises or tests
    layer: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)  # graph inputs not visible as refs
    unique_key: list[str] = field(default_factory=list)
    partition_by: str | None = None
    cluster_by: list[str] = field(default_factory=list)
    incremental_predicate: str | None = None
    columns: dict[str, dict] = field(default_factory=dict)
    header: dict[str, str] = field(default_factory=dict)
    severity: str = "block"
    case_id: str | None = None
    blocking: bool = False

    @property
    def refs(self) -> list[str]:
        return body_refs(self.sql)


def indent(sql: str, n: int = 2) -> str:
    pad = " " * n
    return "\n".join(pad + line if line.strip() else line for line in sql.strip("\n").splitlines())


def strip_leading_comments(sql: str) -> str:
    lines = sql.strip("\n").splitlines()
    while lines and (lines[0].strip().startswith("--") or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines)


def ref(name: str) -> str:
    return f"{{{{ ref('{name}') }}}}"


def _key_concat(cols: list[str], alias: str) -> str:
    parts = [f"CAST({alias}.{c} AS STRING)" for c in cols]
    return parts[0] if len(parts) == 1 else "CONCAT(" + ", '|', ".join(parts) + ")"


# ----------------------------------------------------------------- generated SQL
def staging_candidates_sql(body: str, nk: list[str], order: list[str], rules: list[dict]) -> str:
    whens = []
    for r in rules:
        cond = quality_condition(r)
        if cond:
            whens.append(f"    WHEN {cond} THEN '{r['id']}'")
    reason = ("  CASE\n" + "\n".join(whens) + "\n  END AS _reject_reason") if whens \
        else "  CAST(NULL AS STRING) AS _reject_reason"
    return (f"WITH typed AS (\n{indent(strip_leading_comments(body))}\n)\n"
            f"SELECT\n  typed.*,\n"
            f"  ROW_NUMBER() OVER (PARTITION BY {', '.join(nk)} ORDER BY {', '.join(order)}) AS _dpf_row_rank,\n"
            f"  ROW_NUMBER() OVER (PARTITION BY {', '.join(nk)}, source_modified_ts ORDER BY _ingest_ts DESC) AS _dpf_version_rank,\n"
            f"{reason}\nFROM typed")


def staging_view_sql(name: str, which: str) -> str:
    if which == "current":
        return (f"SELECT * EXCEPT (_dpf_row_rank, _dpf_version_rank, _reject_reason)\n"
                f"FROM {ref(name + '__candidates')}\nWHERE _dpf_row_rank = 1 AND _reject_reason IS NULL")
    if which == "rejects":
        return (f"SELECT * EXCEPT (_dpf_row_rank, _dpf_version_rank)\n"
                f"FROM {ref(name + '__candidates')}\nWHERE _dpf_row_rank = 1 AND _reject_reason IS NOT NULL")
    return (f"SELECT * EXCEPT (_dpf_row_rank, _dpf_version_rank, _reject_reason)\n"
            f"FROM {ref(name + '__candidates')}\nWHERE _dpf_version_rank = 1 AND _reject_reason IS NULL")


def _unknown_value(col: str, attrs: dict, default: str) -> str:
    override = (attrs.get("unknown_member") or {}).get(col)
    if override is None:
        return default
    return str(override) if isinstance(override, (int, float)) else "'" + str(override).replace("'", "\\'") + "'"


def dimension_scd2_sql(m: dict) -> str:
    attrs = m.get("attributes") or {}
    nk, sk = list(m["natural_key"]), m["surrogate_key"]
    tracked, current = list(attrs.get("tracked") or []), list(attrs.get("current") or [])
    src = attrs["source"]
    tracked_struct = f"TO_JSON_STRING(STRUCT({', '.join(tracked)}))"
    part = ", ".join(nk)
    on = " AND ".join(f"c.{k} = v.{k}" for k in nk)
    sel = [f"  FARM_FINGERPRINT(CONCAT({_key_concat(nk, 'v')}, '|', CAST(v.version_no AS STRING))) AS {sk}"]
    sel += [f"  v.{c}" for c in nk + tracked] + [f"  c.{c}" for c in current]
    sel += [f"  IF(v.version_no = 1, {LOW_TS}, v.changed_at) AS valid_from",
            f"  COALESCE(v.next_changed_at, {HIGH_TS}) AS valid_to",
            "  v.next_changed_at IS NULL AS is_current", "  v.version_no"]
    unknown = (["-1"] + [_unknown_value(c, attrs, "'UNKNOWN'") for c in nk + tracked]
               + [_unknown_value(c, attrs, "NULL") for c in current] + [LOW_TS, HIGH_TS, "TRUE", "0"])
    return "\n".join([
        "WITH history AS (",
        f"  SELECT {', '.join(nk + tracked)}, source_modified_ts",
        f"  FROM {ref(src + '_history')}",
        "),",
        "changes AS (",
        "  SELECT",
        "    *,",
        f"    {tracked_struct} AS _dpf_tracked,",
        f"    LAG({tracked_struct}) OVER (PARTITION BY {part} ORDER BY source_modified_ts) AS _dpf_previous",
        "  FROM history",
        "),",
        "versions AS (",
        "  SELECT",
        f"    {', '.join(nk + tracked)},",
        "    source_modified_ts AS changed_at,",
        f"    ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY source_modified_ts) AS version_no,",
        f"    LEAD(source_modified_ts) OVER (PARTITION BY {part} ORDER BY source_modified_ts) AS next_changed_at",
        "  FROM changes",
        "  WHERE _dpf_previous IS NULL OR _dpf_previous != _dpf_tracked",
        "),",
        "current_values AS (",
        f"  SELECT {', '.join(nk + current) if current else ', '.join(nk)}",
        f"  FROM {ref(src)}",
        ")",
        "SELECT",
        ",\n".join(sel),
        "FROM versions AS v",
        f"LEFT JOIN current_values AS c ON {on}",
        "UNION ALL",
        "-- unknown member: facts whose reference has not arrived resolve here instead of being dropped",
        "SELECT " + ", ".join(unknown),
    ])


def dimension_scd1_sql(m: dict) -> str:
    attrs = m.get("attributes") or {}
    nk, sk = list(m["natural_key"]), m["surrogate_key"]
    cols = list(attrs.get("tracked") or []) + list(attrs.get("current") or [])
    sel = [f"  FARM_FINGERPRINT({_key_concat(nk, 's')}) AS {sk}"] + [f"  s.{c}" for c in nk + cols]
    unknown = ["-1"] + [_unknown_value(c, attrs, "'UNKNOWN'") for c in nk] + [_unknown_value(c, attrs, "NULL") for c in cols]
    return "\n".join(["SELECT", ",\n".join(sel), f"FROM {ref(attrs['source'])} AS s", "UNION ALL",
                      "SELECT " + ", ".join(unknown)])


def calendar_sql(m: dict) -> str:
    a = m.get("attributes") or {}
    return "\n".join([
        "SELECT",
        "  CAST(FORMAT_DATE('%Y%m%d', d) AS INT64) AS date_key,",
        "  d AS calendar_date,",
        "  EXTRACT(YEAR FROM d) AS year,",
        "  EXTRACT(QUARTER FROM d) AS quarter,",
        "  FORMAT_DATE('%Y-Q%Q', d) AS year_quarter,",
        "  EXTRACT(MONTH FROM d) AS month,",
        "  FORMAT_DATE('%Y-%m', d) AS year_month,",
        "  FORMAT_DATE('%B', d) AS month_name,",
        "  EXTRACT(DAYOFWEEK FROM d) AS day_of_week,",
        "  FORMAT_DATE('%A', d) AS day_name,",
        "  EXTRACT(DAYOFWEEK FROM d) IN (1, 7) AS is_weekend",
        f"FROM UNNEST(GENERATE_DATE_ARRAY(DATE '{a['start_date']}', DATE '{a['end_date']}')) AS d",
    ])


def fact_sql(m: dict, g: ProductGraph, tz: str) -> tuple[str, str | None]:
    attrs = m.get("attributes") or {}
    src = attrs["source"]
    flags = attrs.get("flags", []) or []
    flag_sel = "".join(f",\n    ({f['expression']}) AS {f['name']}" for f in flags)
    sel = [f"  s.{c}" for c in m.get("natural_key") or []]
    joins = []
    for i, r in enumerate(attrs.get("dim_refs", []) or [], 1):
        dim = g.get(r["dimension"])
        if dim is None:
            continue
        if dim.role == "calendar":
            sel.append(f"  CAST(FORMAT_DATE('%Y%m%d', s.{r['from']}) AS INT64) AS date_key")
            continue
        alias, sk, nkc = f"d{i}", dim.model["surrogate_key"], r["natural_key"]
        dim_nk = (dim.model.get("natural_key") or [nkc])[0]
        sel.append(f"  s.{nkc}")
        sel.append(f"  COALESCE({alias}.{sk}, -1) AS {sk}")
        cond = f"{alias}.{dim_nk} = s.{nkc}"
        if int((dim.model.get("attributes") or {}).get("scd_type", 1) or 1) == 2:
            as_at = f"TIMESTAMP(s.{r['as_at']}, '{tz}')"
            cond += f"\n AND {as_at} >= {alias}.valid_from\n AND {as_at} < {alias}.valid_to"
        joins.append(f"LEFT JOIN {ref(dim.name)} AS {alias}\n  ON {cond}")
    if attrs.get("event_date"):
        sel.append(f"  s.{attrs['event_date']}")
    sel += [f"  s.{x['name']}" for x in attrs.get("measures", []) or []]
    sel += [f"  s.{c}" for c in attrs.get("degenerate", []) or []]
    sel += [f"  s.{f['name']}" for f in flags]
    seen, uniq = set(), []
    for line in sel:
        key = line.strip().split(" AS ")[-1].split(".")[-1]
        if key not in seen:
            seen.add(key)
            uniq.append(line)
    window = attrs.get("restatement_window_days")
    predicate = (f"{attrs['event_date']} >= DATE_SUB(CURRENT_DATE('{tz}'), INTERVAL {int(window)} DAY)"
                 if window and attrs.get("event_date") else None)
    sql = "\n".join([
        "WITH source_rows AS (",
        f"  SELECT\n    *{flag_sel}",
        f"  FROM {ref(src)}",
        f"  {INCREMENTAL_MARKER}",
        ")",
        "SELECT",
        ",\n".join(uniq),
        "FROM source_rows AS s",
        *joins,
    ])
    return sql, predicate


# ----------------------------------------------------------------- plan
def model_schedules(p: Product, g: ProductGraph) -> dict[str, list[str]]:
    schedules = [s["id"] for s in (p.manifest.get("orchestration") or {}).get("schedules", []) or []]
    first = schedules[:1]
    out: dict[str, list[str]] = {}
    gold = [n for n in g.models if n.layer == "gold"]
    for n in gold:
        out[n.name] = [n.model.get("schedule")] if n.model.get("schedule") else list(first)
    for n in g.models:
        if n.layer == "gold":
            continue
        tags: list[str] = []
        for d in g.downstream(n.name):
            if d in out and g.nodes[d].layer == "gold":
                tags += out[d]
        out[n.name] = [s for s in schedules if s in tags] or list(first)
    return out


def build_plan(p: Product, g: ProductGraph, spec: dict, skills: dict[str, str]) -> list[Action]:
    man = p.manifest
    tz = (man.get("orchestration") or {}).get("timezone") or p.registry.defaults.get("business_timezone", "UTC")
    scheds = model_schedules(p, g)
    actions: list[Action] = []
    hist = g.scd2_sources()
    policy_cols: dict[str, dict[str, dict]] = {}
    for t in (man.get("governance") or {}).get("policy_tags", []) or []:
        for c in t["columns"]:
            policy_cols.setdefault(t["model"], {})[c] = {"policy_tag_var": f"policy_tag_{t['tag']}",
                                                        "description": f"Policy tag {t['tag']} ({t['id']})."}

    def header(n, extra: dict | None = None) -> dict:
        h = {"model": n.name, "layer": n.layer, "role": n.role, "skill": skills.get(n.name, "unknown"),
             "satisfies": ",".join(n.model.get("brd_requirement_id") or [])}
        if n.model.get("implements"):
            h["implements"] = n.model["implements"]
        h.update(extra or {})
        return {k: v for k, v in h.items() if v}

    for r in g.raw:
        actions.append(Action(name=r.name, kind="declaration", dataset="raw", subdir="sources", model=r.name,
                              layer="raw", description=f"Raw, append-only landing of {r.name} from {r.source}.",
                              header={"relation": r.name, "source": r.source, "skill": skills.get(f"land:{r.source}", "")}))

    for name in [x for x in g.topo() if g.nodes[x].kind == "model"]:
        n = g.nodes[name]
        m = n.model
        tags = scheds.get(name, [])
        mat = m.get("materialisation") or "view"
        grain = str(m.get("grain_statement") or name)
        desc = f"{grain[:1].upper()}{grain[1:]}."
        if n.layer == "staging":
            rules = g.quarantine_rules(name)
            actions.append(Action(name=f"{name}__candidates", kind="view", dataset="staging", subdir="staging",
                                  sql=staging_candidates_sql(p.body(m) or "", m["natural_key"], m["dedupe_order"], rules),
                                  model=name, layer="staging", tags=tags,
                                  description=f"Every typed version of {name}, ranked for deduplication, with the reject reason.",
                                  header=header(n, {"part": "candidates"})))
            actions.append(Action(name=name, kind="view" if mat == "view" else "table", dataset="staging",
                                  subdir="staging", sql=staging_view_sql(name, "current"), model=name, layer="staging",
                                  tags=tags, description=desc + " Rows failing a quarantine rule are excluded.",
                                  header=header(n)))
            actions.append(Action(name=f"{name}_rejects", kind="view", dataset="staging", subdir="staging",
                                  sql=staging_view_sql(name, "rejects"), model=name, layer="staging", tags=tags,
                                  description=f"Latest {name} rows that failed a quarantine rule, with _reject_reason.",
                                  header=header(n, {"part": "rejects", "satisfies": ",".join(sorted(
                                      {x for r in rules for x in r.get("brd_requirement_id") or []}))
                                      or ",".join(m.get("brd_requirement_id") or [])})))
            if name in hist:
                actions.append(Action(name=f"{name}_history", kind="view", dataset="staging", subdir="staging",
                                      sql=staging_view_sql(name, "history"), model=name, layer="staging", tags=tags,
                                      description=f"One row per change of {name}, for the Type 2 dimension(s) "
                                                  f"{', '.join(hist[name])}.", header=header(n, {"part": "history"})))
            continue

        dataset = m.get("dataset") or n.layer
        common = dict(model=name, layer=n.layer, dataset=dataset, subdir=n.layer, tags=tags, description=desc,
                      header=header(n), partition_by=m.get("partition_by"), cluster_by=list(m.get("cluster_by") or []),
                      columns=policy_cols.get(name, {}))
        if n.role == "dimension":
            scd = int((m.get("attributes") or {}).get("scd_type", 1) or 1)
            sql = dimension_scd2_sql(m) if scd == 2 else dimension_scd1_sql(m)
            actions.append(Action(name=name, kind="table", sql=sql, **common))
        elif n.role == "calendar":
            actions.append(Action(name=name, kind="table", sql=calendar_sql(m), **common))
        elif n.role == "fact":
            sql, pred = fact_sql(m, g, tz)
            kind = "incremental" if mat == "incremental_table" else "table"
            if kind != "incremental":
                sql = sql.replace(f"  {INCREMENTAL_MARKER}\n", "")
            actions.append(Action(name=name, kind=kind, sql=sql, unique_key=list(m.get("grain_columns") or []),
                                  incremental_predicate=pred if kind == "incremental" else None,
                                  inputs=[i for i in n.inputs], **common))
        else:
            body = strip_leading_comments(p.body(m) or "")
            kind = {"view": "view", "table": "table", "incremental_table": "incremental",
                    "materialized_view": "materialized_view"}[mat]
            actions.append(Action(name=name, kind=kind, sql=body, unique_key=list(m.get("grain_columns") or []),
                                  inputs=list(n.inputs), **common))

    # -- assertions from the test specification
    for case in spec["cases"]:
        if case["method"] != "automated":
            continue
        acceptance = case["kind"] == "acceptance"
        model = case.get("model")
        tags = ["acceptance"] if acceptance else list(scheds.get(model, []))
        hdr = {"test": case["id"], "model": model, "satisfies": ",".join(case.get("satisfies") or [])}
        if case.get("verifies"):
            hdr["verifies"] = ",".join(case["verifies"])
        actions.append(Action(name=action_name(case["id"]), kind="assertion", dataset="assertions",
                              subdir="assertions", sql=case["sql"], model=model, description=case["description"],
                              tags=tags, header={k: v for k, v in hdr.items() if v}, severity=case["severity"],
                              case_id=case["id"], blocking=(case["severity"] == "block" and not acceptance)))

    # -- blocking dependencies: nothing downstream of a failed blocking check is refreshed
    blocking_by_model: dict[str, list[str]] = {}
    for a in actions:
        if a.kind == "assertion" and a.blocking and a.model:
            blocking_by_model.setdefault(a.model, []).append(a.name)
    for a in actions:
        if a.kind in ("assertion", "declaration") or a.layer == "staging":
            continue
        deps = []
        for up in g.upstream(a.model):
            deps += blocking_by_model.get(up, [])
        unref = [i for i in a.inputs if i not in a.refs]
        a.dependencies = sorted(set(deps)) + [i for i in unref if i not in deps]
    return actions


def dataset_names(p: Product) -> dict[str, str]:
    return dict((p.manifest.get("deployment") or {}).get("datasets") or {})


def relation_dataset(p: Product, g: ProductGraph, name: str) -> str:
    """Dataset key holding a relation (declared model, raw relation or generated staging helper)."""
    base = re.sub(r"(__candidates|_rejects|_history)$", "", name)
    node = g.get(name) or g.get(base)
    if node is None:
        return "gold"
    if node.kind == "raw":
        return "raw"
    if node.layer == "staging":
        return "staging"
    return node.model.get("dataset") or node.layer
