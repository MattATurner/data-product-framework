"""Monitor plane (`dpf monitor`): evaluate observed run state against the observability policy.

The deployed product checks itself (generated scheduled queries, Knowledge Catalog data
quality scans, log-based alerts). `dpf monitor` is the same policy evaluated offline from a
run-evidence.v1 document, so a breach can be reproduced, tested and turned into work:
with `--open-change` it opens an OpenSpec change (schema `data-product`, `skip_specs: true`)
that quotes the breach and links the runbook, so the fix flows back through the gates.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dpf.core import Product, Report, write_text
from dpf.generate.render import duration_minutes

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
RUNBOOK_ANCHOR = {"freshness": "freshness-or-volume-breach", "volume": "freshness-or-volume-breach",
                  "check": "pipeline-failed", "schema-drift": "schema-drift"}


@dataclass
class Breach:
    kind: str                      # freshness | volume | check | schema-drift
    policy: str                    # OB-n, check id, or entity
    summary: str
    observed: str = ""
    threshold: str = ""
    requirements: list[str] = field(default_factory=list)


_FRACTION = re.compile(r"(\d{2}:\d{2}:\d{2})\.(\d+)")


def parse_ts(value: str) -> datetime:
    """RFC 3339 -> aware datetime (naive means UTC). Python 3.10 parses only 3- or 6-digit
    fractions, so pad or cut the fraction to microseconds first."""
    text = _FRACTION.sub(lambda m: f"{m.group(1)}.{(m.group(2) + '000000')[:6]}",
                         value.strip().replace("Z", "+00:00"), count=1)
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_calendar(at: datetime, cal: dict | None) -> bool:
    if not cal:
        return True
    local = at.astimezone(ZoneInfo(cal.get("timezone") or "UTC"))
    if DAYS[local.weekday()] not in cal.get("days", DAYS):
        return False
    hm = local.strftime("%H:%M")
    return cal.get("start", "00:00") <= hm <= cal.get("end", "23:59")


def evaluate(p: Product, ev: dict) -> tuple[list[Breach], list[str]]:
    """Breaches and notes for one run-evidence document."""
    obs = p.manifest.get("observability") or {}
    at = parse_ts(ev["observed_at"])
    models = {m["name"]: m for m in ev.get("models", [])}
    breaches: list[Breach] = []
    notes: list[str] = []
    for ob in obs.get("freshness", []) or []:
        reqs = list(ob.get("brd_requirement_id") or [])
        limit = duration_minutes(ob["max_staleness"])
        if not in_calendar(at, ob.get("calendar")):
            cal = ob["calendar"]
            notes.append(f"{ob['id']}: {at.isoformat()} is outside the business calendar "
                         f"({' '.join(cal['days'])} {cal['start']}-{cal['end']} {cal['timezone']}); not evaluated")
            continue
        m = models.get(ob["model"])
        if m is None:
            breaches.append(Breach("freshness", ob["id"], f"{ob['model']} was not observed", "not observed",
                                   f"{limit} min", reqs))
            continue
        age = int((at - parse_ts(m["last_built_at"])).total_seconds() // 60)
        if age > limit:
            breaches.append(Breach("freshness", ob["id"], f"{ob['model']} is {age} minutes old (limit {limit})",
                                   f"{age} min", f"{limit} min ({ob['max_staleness']})", reqs))
        else:
            notes.append(f"{ob['id']}: {ob['model']} is {age} minutes old (limit {limit})")
    for ob in obs.get("volume", []) or []:
        m = models.get(ob["model"])
        n = m.get("rows_in_window") if m else None
        exp, tol = int(ob["expected_rows"]), float(ob["tolerance_pct"])
        lo, hi = int(exp * (1 - tol / 100)), int(exp * (1 + tol / 100))
        if n is None:
            notes.append(f"{ob['id']}: no row count observed for {ob['model']}; not evaluated")
        elif not lo <= n <= hi:
            breaches.append(Breach("volume", ob["id"], f"{ob['model']} holds {n} rows per {ob['window']} "
                                   f"(expected {lo}–{hi})", str(n), f"{lo}–{hi}", list(ob.get("brd_requirement_id") or [])))
        else:
            notes.append(f"{ob['id']}: {ob['model']} holds {n} rows (expected {lo}–{hi})")
    for c in ev.get("checks", []) or []:
        if c["status"] == "failed":
            breaches.append(Breach("check", c["id"], f"check {c['id']} failed" + (f": {c['detail']}" if c.get("detail") else ""),
                                   "failed", "passed"))
    drift = obs.get("schema_drift") or {}
    for d in ev.get("drift_events", []) or []:
        changes = "; ".join(d.get("changes") or [])
        if d["classification"] == "breaking":
            breaches.append(Breach("schema-drift", d["entity"],
                                   f"breaking schema change on {d['entity']} ({changes}); batch "
                                   f"{d.get('batch_id', '?')} quarantined, watermark held", changes,
                                   drift.get("on_breaking", "quarantine_and_alert")))
        else:
            notes.append(f"schema drift on {d['entity']} is additive ({changes}): {drift.get('on_additive', 'land_and_record')}")
    return breaches, notes


def _kebab(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def open_change(p: Product, ev: dict, breaches: list[Breach]) -> Path:
    """Write an OpenSpec change that turns the breach into tracked work."""
    at = parse_ts(ev["observed_at"])
    kinds = sorted({b.kind for b in breaches})
    kind = kinds[0] if len(kinds) == 1 else "incident"
    cid = _kebab(f"monitor-{p.id}-{kind}-{at.strftime('%Y%m%d-%H%M')}")
    d = p.ws.root / "openspec" / "changes" / cid
    obs = p.manifest.get("observability") or {}
    runbook = (obs.get("alerting") or {}).get("runbook") or f"examples/{p.id}/RUNBOOK.md"
    reqs = sorted({r for b in breaches for r in b.requirements}, key=lambda x: int(x.split("-")[1]))
    anchors = sorted({RUNBOOK_ANCHOR[b.kind] for b in breaches})
    brd = f"{p.brd.get('brd_id')}@{p.brd.get('version')}"
    rows = "\n".join(f"| {b.kind} | {b.policy} | {b.observed} | {b.threshold} | {', '.join(b.requirements) or '—'} |"
                     for b in breaches)
    write_text(d / ".openspec.yaml",
               "schema: data-product\n"
               f"created: {at.date().isoformat()}\n"
               f"goal: Restore {p.id} to its observability policy after a {kind} breach\n"
               f"affected_areas:\n  - products/{p.id}\n  - monitor-data-product\n"
               "# Opened by `dpf monitor --open-change`: an operational fix has no spec delta until the\n"
               "# investigation shows a requirement or decision must change. Remove skip_specs then.\n"
               "skip_specs: true\n")
    write_text(d / "proposal.md", f"""# Proposal: restore {p.id} after a {kind} breach

## Why

`dpf monitor` found {len(breaches)} breach(es) of the observability policy at {ev['observed_at']}
(run `{ev.get('run_id', 'n/a')}`):

| Kind | Policy | Observed | Threshold | Requirements |
|---|---|---|---|---|
{rows}

## What Changes

- Find the cause using the runbook ({', '.join(f'`{runbook}#{a}`' for a in anchors)}).
- Apply the operational fix: re-run, backfill, or accept a reviewed schema change.
- If the cause is a design gap, add BRD or TDD delta specs and remove `skip_specs` from `.openspec.yaml`.

## Capabilities

- `monitor-data-product` (no change expected).

## Products

- `{p.id}` — {brd}. No BRD change is expected{f'; requirements at risk: {", ".join(reqs)}' if reqs else ''}.

## Gates

- G3 (`dpf check {p.id} --gate G3`) if the fix changes the manifest or SQL bodies.
- G4 (`dpf check {p.id} --gate G4`) after a deployed run records new evidence.
""")
    write_text(d / "design.md", f"""# Design

No design change is planned. If the investigation finds that the manifest, a SQL body or a
methodology pack must change, describe it here, say whether the semantic digest changes, and
re-sign `semantics.md` with `dpf signoff {p.id}` when it does.
""")
    write_text(d / "verification.md", f"""# Verification

- Re-run the observation and evaluate it: `dpf monitor {p.id} --evidence <new run-evidence.json>`
  reports no breach.
- If the build changed: `dpf test run {p.id} --live` records evidence for the new build digest.
""")
    write_text(d / "operations.md", f"""# Operations

Observed at {ev['observed_at']}. Follow the runbook sections:

{chr(10).join(f'- `{runbook}#{a}`' for a in anchors)}

State any backfill or restatement window here before running it.
""")
    write_text(d / "tasks.md", f"""# Tasks

## 1. Investigate
- [ ] 1.1 Confirm the breach in the deployed project (alert, transfer run history, or quality scan result).
- [ ] 1.2 Follow the runbook section(s) above and record the cause in operations.md.

## 2. Fix
- [ ] 2.1 Apply the operational fix (re-run, backfill, or accept the schema change with `--accept-schema`).
- [ ] 2.2 If a spec or design change is needed, add delta specs, remove `skip_specs`, and run `openspec validate --strict`.

## 3. Verify
- [ ] 3.1 `dpf monitor {p.id} --evidence <new run-evidence.json>` reports no breach.
- [ ] 3.2 If the build changed: `dpf check {p.id} --gate G3`, then `dpf check {p.id} --gate G4` after a deployed run.
""")
    return d


def collect(p: Product) -> dict:
    """Observe the deployed product (needs google-cloud-bigquery and credentials)."""
    from google.cloud import bigquery  # type: ignore

    from dpf.generate.plan import relation_dataset
    from dpf.generate.render import is_timestamp, timezone as business_tz
    from dpf.graph import ProductGraph

    dep = p.manifest.get("deployment") or {}
    project, datasets = dep.get("gcp_project"), dep.get("datasets") or {}
    tz = business_tz(p)
    g = ProductGraph(p)
    client = bigquery.Client(project=project)
    obs = p.manifest.get("observability") or {}
    names = sorted({o["model"] for k in ("freshness", "volume") for o in obs.get(k, []) or []})
    models = []
    for name in names:
        ds = datasets.get(relation_dataset(p, g, name))
        row = list(client.query(f"SELECT TIMESTAMP_MILLIS(last_modified_time) AS t FROM `{project}.{ds}.__TABLES__` "
                                f"WHERE table_id = '{name}'").result())
        if not row:
            continue
        entry = {"name": name, "last_built_at": row[0]["t"].isoformat().replace("+00:00", "Z")}
        vol = next((o for o in obs.get("volume", []) or [] if o["model"] == name), None)
        if vol:
            days = max(1, duration_minutes(vol["window"]) // 1440)
            col = vol.get("date_column")
            expr = f"DATE({col}, '{tz}')" if is_timestamp(col) else col
            where = (f"WHERE {expr} >= DATE_SUB(CURRENT_DATE('{tz}'), INTERVAL {days} DAY) "
                     f"AND {expr} < CURRENT_DATE('{tz}')") if col else ""
            n = list(client.query(f"SELECT COUNT(*) AS n FROM `{project}.{ds}.{name}` {where}").result())
            entry["rows_in_window"] = int(n[0]["n"])
        models.append(entry)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {"product_id": p.id, "observed_at": now.isoformat().replace("+00:00", "Z"),
            "run_id": now.strftime("observe-%Y%m%dT%H%M%SZ"), "models": models}


def monitor(p: Product, report: Report, evidence: dict | None = None, open_change_on_breach: bool = False) -> int:
    report.head(f"monitor — {p.id}", gate="monitor")
    if evidence is None:
        try:
            evidence = collect(p)
        except ImportError:
            report.fail("pass --evidence <run-evidence.json>, or install google-cloud-bigquery to observe the deployed product")
            return 1
    errs = p.ws.validate(evidence, "run-evidence.v1")
    if errs:
        report.fail(f"evidence does not conform to run-evidence.v1: {'; '.join(errs[:3])}")
        return 1
    if evidence["product_id"] != p.id:
        report.fail(f"evidence is for {evidence['product_id']}, not {p.id}")
        return 1
    breaches, notes = evaluate(p, evidence)
    for n in notes:
        report.ok(n)
    for b in breaches:
        report.fail(f"{b.kind} {b.policy}: {b.summary}" + (f" [{', '.join(b.requirements)}]" if b.requirements else ""))
    if not breaches:
        report.ok(f"no breach of the observability policy at {evidence['observed_at']}")
        return 0
    if open_change_on_breach:
        d = open_change(p, evidence, breaches)
        report.info(f"opened change {d.relative_to(p.ws.root)}/ (validate with `openspec validate {d.name} --strict`)")
    return 1


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
