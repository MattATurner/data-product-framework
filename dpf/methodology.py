"""Methodology rules (rule.v1 `check:` ids) and the methodology recommendation.

Rules are data in `methodologies/<pack>/rules/*.yaml`; this module holds the mechanical
check behind each `check:` id. Active rules are the default pack's rules plus the rules of
every pack a product uses, applied to every model whose role is in the rule's `applies_to`.
Checks that need generated artefacts (the test specification) run when one is supplied (G3).
"""

from __future__ import annotations

import re
from typing import Callable

from dpf.core import Product, Report
from dpf.graph import LAYER_RANK, ProductGraph, body_refs

POINT_IN_TIME = re.compile(
    r"\b(stay(s)? as (they|it) (were|was)|at the time|that applied|applied on|keep(s)? (the|their|its) "
    r"(earlier|old|original)|as (it|they) (was|were) then|remain(s)? under)\b", re.I)


# ----------------------------------------------------------------- helpers
def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _attrs(m: dict) -> dict:
    return m.get("attributes") or {}


def _scd(m: dict) -> int:
    try:
        return int(_attrs(m).get("scd_type", 1) or 1)
    except (TypeError, ValueError):
        return 0


def _cases(ctx: dict) -> list[dict]:
    return (ctx.get("test_spec") or {}).get("cases", []) or []


# ----------------------------------------------------------------- checks
# Each check returns a list of violation messages for the targeted models.
def grain_asserted(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    for n in targets:
        m = n.model
        if not m.get("grain_statement") or not m.get("grain_columns"):
            out.append(f"{n.name}: grain statement and grain columns must both be declared")
            continue
        if ctx.get("test_spec") is not None:
            cols = ", ".join(m["grain_columns"])
            case = next((c for c in _cases(ctx) if c.get("kind") == "grain" and c.get("model") == n.name), None)
            if case is None:
                out.append(f"{n.name}: no grain test in the test specification")
            elif case.get("severity") != "block" or f"GROUP BY {cols}" not in (case.get("sql") or ""):
                out.append(f"{n.name}: grain test must be blocking and on exactly ({cols})")
    return out


def body_present_and_resolvable(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    for n in targets:
        rel = n.model.get("body")
        if not rel:
            out.append(f"{n.name}: role '{n.role}' needs an authored SQL body (model.body)")
            continue
        body = p.body(n.model)
        if body is None:
            out.append(f"{n.name}: body file products/{p.id}/{rel} does not exist")
            continue
        for ref in body_refs(body):
            tgt = g.get(ref)
            if tgt is None:
                out.append(f"{n.name}: body references '{ref}', which is not a declared model or raw relation")
            elif ref == n.name:
                out.append(f"{n.name}: body references itself")
            elif LAYER_RANK[tgt.layer] > LAYER_RANK[n.layer]:
                out.append(f"{n.name}: body references '{ref}' in a later layer ({tgt.layer})")
            elif n.layer != "staging" and tgt.kind == "raw":
                out.append(f"{n.name}: only staging models may read raw relations (found '{ref}')")
    return out


def nesting_depth(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    limit = int((rule.get("params") or {}).get("max_depth", 2))
    out = []
    for n in targets:
        for child in n.model.get("nesting", []) or []:
            if child.get("child") not in g.nodes:
                out.append(f"{n.name}: nested child '{child.get('child')}' is not a declared model")
            if int(child.get("depth", 1)) > limit:
                out.append(f"{n.name}: nesting '{child.get('as')}' is {child.get('depth')} levels deep (limit {limit})")
    return out


def view_chain_depth(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    limit = int((rule.get("params") or {}).get("max_depth", 3))

    def is_view(name: str) -> bool:
        node = g.get(name)
        return bool(node and node.kind == "model" and node.layer != "staging"
                    and (node.model.get("materialisation") or "view") == "view")

    def depth(name: str, seen: frozenset = frozenset()) -> int:
        if not is_view(name) or name in seen:
            return 0
        return 1 + max([depth(i, seen | {name}) for i in g.nodes[name].inputs] or [0])

    return [f"{n.name}: chain of {depth(n.name)} stacked views exceeds {limit}; materialise one of them"
            for n in targets if depth(n.name) > limit]


def surrogate_key_required(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    for n in targets:
        sk = n.model.get("surrogate_key")
        if not sk:
            out.append(f"{n.name}: dimension must declare surrogate_key")
        elif sk in (n.model.get("natural_key") or []):
            out.append(f"{n.name}: surrogate key '{sk}' must not be a natural key column")
    return out


def dimension_single_grain(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    for n in targets:
        m, attrs = n.model, _attrs(n.model)
        nk = list(m.get("natural_key") or [])
        scd = _scd(m)
        if not nk:
            out.append(f"{n.name}: dimension must declare natural_key")
            continue
        if scd not in (1, 2):
            out.append(f"{n.name}: scd_type must be 1 or 2 (got {attrs.get('scd_type')!r})")
            continue
        expected = nk + (["valid_from"] if scd == 2 else [])
        if sorted(m.get("grain_columns") or []) != sorted(expected):
            out.append(f"{n.name}: Type {scd} grain columns must be ({', '.join(expected)}), "
                       f"got ({', '.join(m.get('grain_columns') or [])})")
        hist = m.get("history_semantics")
        if scd == 2 and hist not in ("point_in_time", "full_history"):
            out.append(f"{n.name}: Type 2 dimension must declare point_in_time or full_history history")
        if scd == 1 and hist != "current_only":
            out.append(f"{n.name}: Type 1 dimension must declare current_only history")
        if scd == 2 and not attrs.get("tracked"):
            out.append(f"{n.name}: Type 2 dimension must list tracked attributes")
        src = g.get(attrs.get("source") or "")
        if not src or src.layer != "staging":
            out.append(f"{n.name}: attributes.source must name a staging model")
    return out


def conformance_respected(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    reg = p.registry.conformed
    for n in targets:
        name = n.model.get("conformed_as")
        if not name:
            continue
        entry = reg.get(name)
        if entry is None:
            out.append(f"{n.name}: conformed_as '{name}' is not in the bus matrix (registry conformance.yaml)")
            continue
        owner = entry.get("owning_domain")
        if _norm(entry.get("grain")) != _norm(n.model.get("grain_statement")):
            out.append(f"{n.name}: grain differs from conformed '{name}' owned by domain '{owner}' "
                       f"('{entry.get('grain')}')")
        if sorted(entry.get("natural_key") or []) != sorted(n.model.get("natural_key") or []):
            out.append(f"{n.name}: natural key differs from conformed '{name}' owned by domain '{owner}' "
                       f"({', '.join(entry.get('natural_key') or [])})")
        if owner not in (p.manifest.get("domain"), "shared") and p.id not in (entry.get("used_by") or []):
            out.append(f"{n.name}: product is not listed in used_by of '{name}' (owning domain '{owner}')")
    return out


def fact_fk_integrity(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    for n in targets:
        attrs = _attrs(n.model)
        if attrs.get("fact_type", "transaction") != "transaction":
            out.append(f"{n.name}: fact_type '{attrs.get('fact_type')}' is planned, not implemented")
        src = g.get(attrs.get("source") or "")
        if not src or src.layer != "staging":
            out.append(f"{n.name}: attributes.source must name a staging model")
        cols = g.output_columns(attrs.get("source")) if src else None
        for ref in attrs.get("dim_refs", []) or []:
            dim = g.get(ref.get("dimension") or "")
            if not dim or dim.role not in ("dimension", "calendar"):
                out.append(f"{n.name}: dim_ref '{ref.get('dimension')}' is not a declared dimension or calendar")
                continue
            if dim.role == "calendar":
                if not ref.get("from"):
                    out.append(f"{n.name}: calendar reference to {dim.name} must name a 'from' date column")
                continue
            if not ref.get("natural_key"):
                out.append(f"{n.name}: reference to {dim.name} must name the natural_key column")
            elif cols is not None and ref["natural_key"] not in cols:
                out.append(f"{n.name}: '{ref['natural_key']}' is not a column of {attrs.get('source')}")
            if _scd(dim.model) == 2 and not ref.get("as_at"):
                out.append(f"{n.name}: Type 2 reference to {dim.name} must resolve as at an event column (as_at)")
        if ctx.get("test_spec") is not None:
            ids = {c["id"] for c in _cases(ctx)}
            for ref in attrs.get("dim_refs", []) or []:
                if ref.get("natural_key") and f"integrity:{n.name}:{ref['natural_key']}:not_null" not in ids:
                    out.append(f"{n.name}: no blocking not-null test for '{ref['natural_key']}'")
    return out


def additivity_declared(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    summed = ((p.brd.get("totalling") or {}).get("can_be_summed_across") or [])
    for n in targets:
        measures = _attrs(n.model).get("measures", []) or []
        if not measures:
            out.append(f"{n.name}: fact declares no measures")
        for ms in measures:
            if ms.get("additivity") not in ("additive", "semi_additive", "non_additive"):
                out.append(f"{n.name}: measure '{ms.get('name')}' must declare additivity")
        if summed and not any(ms.get("additivity") == "additive" for ms in measures):
            out.append(f"{n.name}: BRD says figures can be summed across {', '.join(summed)} but no measure is additive")
    return out


def no_fact_to_fact_join(p: Product, g: ProductGraph, rule: dict, targets: list, ctx: dict) -> list[str]:
    out = []
    facts = set(g.facts())
    for n in targets:
        reads = [i for i in n.inputs if i in facts]
        if n.role == "fact" and reads:
            out.append(f"{n.name}: a fact may not read another fact ({', '.join(reads)})")
        elif n.role != "fact" and len(reads) > 1:
            out.append(f"{n.name}: joins {len(reads)} facts directly ({', '.join(reads)}); combine through conformed dimensions")
    return out


RULE_CHECKS: dict[str, Callable] = {
    "grain_asserted": grain_asserted,
    "body_present_and_resolvable": body_present_and_resolvable,
    "nesting_depth": nesting_depth,
    "view_chain_depth": view_chain_depth,
    "surrogate_key_required": surrogate_key_required,
    "dimension_single_grain": dimension_single_grain,
    "conformance_respected": conformance_respected,
    "fact_fk_integrity": fact_fk_integrity,
    "additivity_declared": additivity_declared,
    "no_fact_to_fact_join": no_fact_to_fact_join,
}


# ----------------------------------------------------------------- runners
def active_rules(p: Product, g: ProductGraph) -> list[tuple[str, dict]]:
    ws = p.ws
    packs = [k for k, v in ws.packs.items() if v.get("is_default")]
    for layer in ("silver", "gold"):
        if p.layer_cfg(layer).get("models"):
            packs.append(g.layer_pack(layer))
    out, seen = [], set()
    for pack in dict.fromkeys(packs):
        for rid in (ws.packs.get(pack) or {}).get("rules", []) or []:
            if rid in seen:
                continue
            seen.add(rid)
            out.append((pack, ws.rules.get(rid) or {"id": rid, "_missing": True}))
    return out


def run_rules(p: Product, report: Report, g: ProductGraph | None = None, test_spec: dict | None = None) -> None:
    g = g or ProductGraph(p)
    ctx = {"test_spec": test_spec}
    for pack, rule in active_rules(p, g):
        rid = rule.get("id")
        if rule.get("_missing"):
            report.fail(f"rule '{rid}' listed by pack '{pack}' has no rule file", rule=rid)
            continue
        fn = RULE_CHECKS.get(rule.get("check", ""))
        if fn is None:
            report.fail(f"rule '{rid}' names unknown check '{rule.get('check')}'", rule=rid)
            continue
        applies = rule.get("applies_to") or []
        targets = [n for n in g.models if "*" in applies or n.role in applies]
        if not targets:
            continue
        problems = fn(p, g, rule, targets, ctx)
        if not problems:
            report.ok(f"{pack}/{rid}: {len(targets)} model(s) comply", rule=rid)
        for msg in problems:
            (report.warn if rule.get("severity") == "warn" else report.fail)(f"{pack}/{rid}: {msg}", rule=rid)


# ----------------------------------------------------------------- recommendation
def history_point_in_time(brd: dict) -> list[dict]:
    return [hb for hb in brd.get("history_behaviour", []) or [] if POINT_IN_TIME.search(hb.get("answer", ""))]


def recommend(p: Product) -> tuple[str, list[str]]:
    """Recommend a methodology for the integration layer from BRD signals alone."""
    reasons = []
    for ag in p.brd.get("agreement_with_other_teams", []) or []:
        reasons.append(f"{ag.get('id')}: figures must agree with {ag.get('team')} on {ag.get('must_agree_on')}")
    for hb in history_point_in_time(p.brd):
        reasons.append(f"{hb.get('id')}: past figures keep the {hb.get('attribute')} that applied at the time")
    return ("kimball" if reasons else "direct"), reasons
