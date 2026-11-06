"""Test specification (test-spec.v1): every check a product must pass.

Derived, never hand-written: grain and not-null checks from every model's declared grain,
reject gates from quarantine rules, SCD integrity from Type 2 dimensions, key integrity
from fact references, quality rules from the policy, and the acceptance mapping (automated
SQL, static checks and attestations) from acceptance.yaml. Automated cases carry
engine-neutral SQL that returns rows only on failure.
"""

from __future__ import annotations

from dpf.core import Product
from dpf.graph import ProductGraph

PLATFORM = "test-data-product"


def _cols(cols: list[str], alias: str = "") -> str:
    pre = f"{alias}." if alias else ""
    return ", ".join(f"{pre}{c}" for c in cols)


def action_name(case_id: str) -> str:
    """Engine action / test name for a case id (identifier-safe, deterministic)."""
    import re
    kind, _, rest = case_id.partition(":")
    if kind == "acceptance":
        return "acceptance_" + rest.lower().replace("-", "_")
    if kind == "quality":
        return "assert_" + rest.lower().replace("-", "_")
    parts = rest.split(":")
    suffix = {"grain": "grain", "grain_not_null": "grain_not_null", "reject_gate": "no_rejects",
              "reject_warn": "warn_rejects", "ml_eval": "ml_eval",
              "scd_overlap": "scd_no_overlap", "scd_current": "scd_one_current"}.get(kind)
    if suffix:
        return f"assert_{parts[0]}_{suffix}"
    if kind == "integrity":
        return "assert_" + "_".join(parts)
    return "assert_" + re.sub(r"[^a-z0-9_]+", "_", case_id.lower())


def quality_condition(rule: dict) -> str | None:
    """Row-level failure condition for a quality rule, or None when it is not row-level."""
    t, col = rule.get("type"), rule.get("column")
    if t == "not_null":
        return f"{col} IS NULL"
    if t == "range":
        parts = []
        if rule.get("min") is not None:
            parts.append(f"{col} < {rule['min']}")
        if rule.get("max") is not None:
            parts.append(f"{col} > {rule['max']}")
        return " OR ".join(parts) or None
    if t == "set_membership":
        vals = ", ".join("'" + str(v).replace("'", "\\'") + "'" for v in rule.get("values") or [])
        return f"{col} NOT IN ({vals})"
    if t == "custom_sql" and rule.get("expression"):
        return f"NOT COALESCE(({rule['expression']}), FALSE)"
    return None


def build_test_spec(p: Product, g: ProductGraph, digest: str) -> dict:
    cases: list[dict] = []
    man = p.manifest

    def add(**kw) -> None:
        kw.setdefault("tags", [])
        kw.setdefault("satisfies", [])
        cases.append({k: v for k, v in kw.items() if v is not None})

    for u in g.upstream_nodes:
        um = u.model
        ureqs = list(um.get("brd_requirement_id") or [])
        ugrain = list(um.get("grain_columns") or [])
        if ugrain:
            add(id=f"grain:{u.name}", kind="grain", method="automated", severity="block", model=u.name,
                description=f"{u.name}: {um.get('grain_statement') or u.name} — no duplicates on ({', '.join(ugrain)})",
                sql=(f"SELECT {_cols(ugrain)}, COUNT(*) AS rows_per_grain\nFROM {{{{ ref('{u.name}') }}}}\n"
                     f"GROUP BY {_cols(ugrain)}\nHAVING COUNT(*) > 1"),
                satisfies=ureqs, implements=PLATFORM)
            add(id=f"grain_not_null:{u.name}", kind="grain", method="automated", severity="block", model=u.name,
                description=f"{u.name}: grain columns are never null",
                sql=f"SELECT *\nFROM {{{{ ref('{u.name}') }}}}\nWHERE " + " OR ".join(f"{c} IS NULL" for c in ugrain),
                satisfies=ureqs, implements=PLATFORM)

    for name in [n for n in g.topo() if g.nodes[n].kind == "model"]:
        n = g.nodes[name]
        m = n.model
        reqs = list(m.get("brd_requirement_id") or [])
        grain = list(m.get("grain_columns") or [])
        attrs = m.get("attributes") or {}
        if n.role == "ml_model":
            eval_cfg = attrs.get("evaluation") or {}
            metric = eval_cfg.get("metric")
            conds = []
            if eval_cfg.get("min") is not None:
                conds.append(f"{metric} < {eval_cfg['min']}")
            if eval_cfg.get("max") is not None:
                conds.append(f"{metric} > {eval_cfg['max']}")
            if metric and conds:
                add(id=f"ml_eval:{name}", kind="quality", method="automated",
                    severity=eval_cfg.get("severity", "block"), model=name,
                    description=f"{name}: ML.EVALUATE metric {metric} meets threshold",
                    sql=f"SELECT *\nFROM ML.EVALUATE(MODEL {{{{ ref('{name}') }}}})\nWHERE {' OR '.join(conds)}",
                    satisfies=reqs, implements=PLATFORM)
            continue
        add(id=f"grain:{name}", kind="grain", method="automated", severity="block", model=name,
            description=f"{name}: {m.get('grain_statement')} — no duplicates on ({', '.join(grain)})",
            sql=(f"SELECT {_cols(grain)}, COUNT(*) AS rows_per_grain\nFROM {{{{ ref('{name}') }}}}\n"
                 f"GROUP BY {_cols(grain)}\nHAVING COUNT(*) > 1"),
            satisfies=reqs, implements=PLATFORM)
        add(id=f"grain_not_null:{name}", kind="grain", method="automated", severity="block", model=name,
            description=f"{name}: grain columns are never null",
            sql=f"SELECT *\nFROM {{{{ ref('{name}') }}}}\nWHERE " + " OR ".join(f"{c} IS NULL" for c in grain),
            satisfies=reqs, implements=PLATFORM)
        if n.layer == "staging":
            rules = g.quarantine_rules(name)
            if rules:
                q_cfg = man.get("quality") or {}
                gate_beh = q_cfg.get("gate_behaviour", "block")
                has_blocking_rule = any(r.get("severity", "block") == "block" for r in rules)
                sev = "block" if (gate_beh == "block" and has_blocking_rule) else "warn"
                rule_pcts = [r["max_reject_pct"] for r in rules if r.get("max_reject_pct") is not None]
                max_pct = min(rule_pcts) if rule_pcts else q_cfg.get("max_reject_pct")
                rule_rows = [r["max_reject_rows"] for r in rules if r.get("max_reject_rows") is not None]
                max_rows = min(rule_rows) if rule_rows else q_cfg.get("max_reject_rows")
                if max_pct is not None:
                    gate_sql = (f"SELECT\n"
                                f"  COUNTIF(_reject_reason IS NOT NULL) AS rejected_rows,\n"
                                f"  COUNT(*) AS candidate_rows,\n"
                                f"  SAFE_DIVIDE(COUNTIF(_reject_reason IS NOT NULL) * 100.0, COUNT(*)) AS reject_pct\n"
                                f"FROM {{{{ ref('{name}__candidates') }}}}\n"
                                f"WHERE _dpf_row_rank = 1\n"
                                f"HAVING SAFE_DIVIDE(COUNTIF(_reject_reason IS NOT NULL) * 100.0, COUNT(*)) > {max_pct}")
                    desc = f"{name}: quarantined row share ({', '.join(r['id'] for r in rules)}) does not exceed {max_pct}%"
                elif max_rows is not None:
                    gate_sql = (f"SELECT COUNT(*) AS rejected_rows\n"
                                f"FROM {{{{ ref('{name}_rejects') }}}}\n"
                                f"HAVING COUNT(*) > {max_rows}")
                    desc = f"{name}: quarantined row count ({', '.join(r['id'] for r in rules)}) does not exceed {max_rows}"
                else:
                    gate_sql = f"SELECT *\nFROM {{{{ ref('{name}_rejects') }}}}"
                    if sev == "block":
                        desc = (f"{name}: no row is quarantined ({', '.join(r['id'] for r in rules)}); "
                                "any rejected row blocks every downstream refresh")
                    else:
                        desc = (f"{name}: quarantined rows ({', '.join(r['id'] for r in rules)}) are excluded "
                                "and logged as a warning without blocking downstream refreshes")
                add(id=f"reject_gate:{name}", kind="reject_gate", method="automated", severity=sev, model=name,
                    description=desc,
                    sql=gate_sql,
                    satisfies=sorted({x for r in rules for x in r.get("brd_requirement_id") or []}),
                    implements="enforce-data-quality")
                warn_pct = q_cfg.get("warn_reject_pct")
                if warn_pct is not None:
                    warn_sql = (f"SELECT\n"
                                f"  COUNTIF(_reject_reason IS NOT NULL) AS rejected_rows,\n"
                                f"  COUNT(*) AS candidate_rows,\n"
                                f"  SAFE_DIVIDE(COUNTIF(_reject_reason IS NOT NULL) * 100.0, COUNT(*)) AS reject_pct\n"
                                f"FROM {{{{ ref('{name}__candidates') }}}}\n"
                                f"WHERE _dpf_row_rank = 1\n"
                                f"HAVING SAFE_DIVIDE(COUNTIF(_reject_reason IS NOT NULL) * 100.0, COUNT(*)) > {warn_pct}")
                    add(id=f"reject_warn:{name}", kind="reject_gate", method="automated", severity="warn", model=name,
                        description=f"{name}: warn when quarantined row share exceeds {warn_pct}%",
                        sql=warn_sql,
                        satisfies=sorted({x for r in rules for x in r.get("brd_requirement_id") or []}),
                        implements="enforce-data-quality")
        if n.role == "dimension" and int(attrs.get("scd_type", 1) or 1) == 2:
            nk = list(m.get("natural_key") or [])
            on = " AND ".join(f"a.{c} = b.{c}" for c in nk)
            add(id=f"scd_overlap:{name}", kind="scd_integrity", method="automated", severity="block", model=name,
                description=f"{name}: validity windows of one member never overlap",
                sql=(f"SELECT {_cols(nk, 'a')}, a.valid_from, a.valid_to, b.valid_from AS overlapping_from\n"
                     f"FROM {{{{ ref('{name}') }}}} AS a\nJOIN {{{{ ref('{name}') }}}} AS b\n"
                     f"  ON {on} AND a.version_no < b.version_no\n"
                     f" AND a.valid_from < b.valid_to AND b.valid_from < a.valid_to"),
                satisfies=reqs, implements=PLATFORM)
            add(id=f"scd_current:{name}", kind="scd_integrity", method="automated", severity="block", model=name,
                description=f"{name}: exactly one current version per member",
                sql=(f"SELECT {_cols(nk)}, COUNTIF(is_current) AS current_versions\nFROM {{{{ ref('{name}') }}}}\n"
                     f"GROUP BY {_cols(nk)}\nHAVING COUNTIF(is_current) != 1"),
                satisfies=reqs, implements=PLATFORM)
        if n.role == "fact":
            fnk = list(m.get("natural_key") or grain)
            for ref in attrs.get("dim_refs", []) or []:
                dim = g.get(ref.get("dimension") or "")
                if not dim or dim.role != "dimension" or not ref.get("natural_key"):
                    continue
                col, sk = ref["natural_key"], dim.model.get("surrogate_key")
                add(id=f"integrity:{name}:{col}:not_null", kind="integrity", method="automated", severity="block",
                    model=name, description=f"{name}: every line names a {col} (reference to {dim.name})",
                    sql=f"SELECT {_cols(fnk)}\nFROM {{{{ ref('{name}') }}}}\nWHERE {col} IS NULL",
                    satisfies=reqs, implements=PLATFORM)
                add(id=f"integrity:{name}:{dim.name}:late_arrival", kind="integrity", method="automated",
                    severity="warn", model=name,
                    description=f"{name}: lines whose {col} has not yet arrived in {dim.name} (kept with the unknown member)",
                    sql=f"SELECT {_cols(fnk)}, {col}\nFROM {{{{ ref('{name}') }}}}\nWHERE {sk} = -1",
                    satisfies=reqs, implements=PLATFORM)

    for r in (man.get("quality") or {}).get("rules", []) or []:
        if r.get("on_fail") == "quarantine":
            continue
        cond = quality_condition(r)
        if r.get("type") == "unique":
            cols = r.get("columns") or [r.get("column")]
            sql = (f"SELECT {_cols(cols)}, COUNT(*) AS duplicates\nFROM {{{{ ref('{r['model']}') }}}}\n"
                   f"GROUP BY {_cols(cols)}\nHAVING COUNT(*) > 1")
        elif cond:
            sql = f"SELECT *\nFROM {{{{ ref('{r['model']}') }}}}\nWHERE {cond}"
        else:
            continue
        add(id=f"quality:{r['id']}", kind="quality", method="automated", severity=r.get("severity", "block"),
            model=r["model"], description=f"{r['id']}: {r['type']} on {r.get('column') or ', '.join(r.get('columns') or [])}",
            sql=sql, satisfies=list(r.get("brd_requirement_id") or []), implements=r.get("implements"))

    sl = man.get("semantic_layer") or {}
    if "lookml" in (sl.get("targets") or []):
        for e in sl.get("explores") or []:
            ereqs = list(e.get("brd_requirement_id") or sl.get("brd_requirement_id") or [])
            add(id=f"lookml_explore:{e['name']}", kind="static", method="static", severity="block",
                check="lookml_explore", element=f"explore:{e['name']}",
                description=(f"explore {e['name']}: every joined view declares primary_key, joins use surrogate keys "
                             "and zero PDTs exist"),
                satisfies=ereqs, implements=PLATFORM)
        for d in sl.get("dashboards") or []:
            dreqs = list(d.get("brd_requirement_id") or sl.get("brd_requirement_id") or [])
            add(id=f"lookml_dashboard:{d['name']}", kind="static", method="static", severity="block",
                check="lookml_dashboard", element=f"dashboard:{d['name']}",
                description=(f"dashboard {d['name']}: valid LookML YAML, Stephen Few chart types and resolved "
                             "Explore fields"),
                satisfies=dreqs, implements=PLATFORM)

    ax_owner = p.scenario_ids
    for t in (p.acceptance or {}).get("tests", []) or []:
        reqs = sorted({ax_owner[a] for a in t["verifies"] if a in ax_owner}, key=lambda x: int(x.split("-")[1]))
        base = dict(id=f"acceptance:{t['id']}", method=t["method"], description=t["description"],
                    verifies=list(t["verifies"]), satisfies=reqs, tags=["acceptance"])
        if t["method"] == "automated":
            add(kind="acceptance", severity="block", model=t.get("model"), sql=t["sql"].rstrip(), **base)
        elif t["method"] == "static":
            add(kind="static", severity="block", check=t["check"], element=t.get("element"), **base)
        else:
            add(kind="acceptance", severity="block", attested_by_role=t["attested_by_role"], **base)
    return {"product_id": p.id, "artefact_digest": digest, "cases": cases}
