"""G0 — BRD completeness and approval (`dpf brd validate`).

The rubric (registry/brd-rubric.yaml) and the vocabulary list (registry/brd-vocabulary.yaml)
are data. Unanswered groups become questions for the business owner in the gap register
`generated/<product>/gaps.md`; nothing is written back into the specs.
"""

from __future__ import annotations

import re
from datetime import date

from dpf.core import Product, Report, write_text


def _get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _filled(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _strings(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


def _term_hits(text: str, terms: list[str]) -> list[str]:
    hits = []
    for t in terms:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])", text, re.I):
            hits.append(t)
    return hits


def check_brd(p: Product, report: Report, write_gaps: bool = True) -> list[dict]:
    """Run G0 for one product. Returns the gap list (also written to gaps.md)."""
    report.head(f"G0 · BRD completeness — {p.id}", gate="G0")
    gaps: list[dict] = []
    reg = p.registry
    rubric = reg.rubric
    brd = p.brd
    brd_path = p.brd_dir / "brd.yaml"
    spec_path = p.brd_dir / "spec.md"

    if not spec_path.exists():
        report.fail(f"BRD spec missing: {spec_path.relative_to(p.ws.root)}")
        return gaps
    if not brd_path.exists():
        report.fail(f"BRD answers missing: {brd_path.relative_to(p.ws.root)}")
        return gaps

    errs = p.ws.validate(brd, "brd.v1")
    report.check(not errs, "brd.yaml conforms to brd.v1",
                 f"brd.yaml does not conform to brd.v1: {'; '.join(errs[:5])}")

    spec = p.brd_spec
    meta = spec.purpose_meta
    report.check(meta.get("brd") == brd.get("brd_id"), f"spec and answers agree on id {brd.get('brd_id')}",
                 f"spec.md says BRD {meta.get('brd')!r}, brd.yaml says {brd.get('brd_id')!r}")
    report.check(meta.get("version") == brd.get("version"), f"spec and answers agree on version {brd.get('version')}",
                 f"spec.md version {meta.get('version')!r} differs from brd.yaml version {brd.get('version')!r}")
    if brd.get("product_id") != p.id:
        report.fail(f"brd.yaml product_id {brd.get('product_id')!r} is not {p.id!r}")

    # -- requirements and scenarios (group J)
    req_ids: list[str] = []
    ax_ids: list[str] = []
    for r in spec.requirements:
        rid = r.meta.get("id")
        if not rid or not re.fullmatch(r"R-\d+", rid):
            report.fail(f"requirement '{r.name}' has no '**ID:** R-n' line")
            continue
        if rid in req_ids:
            report.fail(f"requirement id {rid} is used twice")
        req_ids.append(rid)
        if not r.normative:
            report.fail(f"{rid} '{r.name}' has no SHALL or MUST statement")
        scen = [s for s in r.scenarios if s.meta.get("id")]
        if not scen:
            report.fail(f"{rid} '{r.name}' has no business acceptance scenario (AX id)")
            gaps.append({"group": "J", "field": rid, "question": _group(rubric, "J").get("question", ""),
                         "context": r.name})
        for s in r.scenarios:
            sid = s.meta.get("id")
            if not sid:
                report.fail(f"{rid}: scenario '{s.name}' has no '**ID:** AX-n' line")
                continue
            if sid in ax_ids:
                report.fail(f"scenario id {sid} is used twice")
            ax_ids.append(sid)
            if not {"WHEN", "THEN"} <= s.keywords:
                report.fail(f"{sid} '{s.name}' needs WHEN and THEN steps")
    if req_ids:
        report.ok(f"{len(req_ids)} requirements, {len(ax_ids)} acceptance scenarios")

    # -- rubric groups A..K
    for group in rubric.get("groups", []) or []:
        missing = [f for f in group.get("fields", []) or [] if not _filled(_get(brd, f))]
        if group.get("check") == "scenario_per_requirement":
            continue
        if missing:
            report.fail(f"group {group['id']} ({group['title']}) unanswered: {', '.join(missing)}")
            gaps.append({"group": group["id"], "field": ", ".join(missing), "question": group.get("question", ""),
                         "context": group.get("title", "")})
        else:
            report.ok(f"group {group['id']} ({group['title']}) answered")

    # -- optional answers that the text suggests matter
    text = spec.raw.lower()
    for opt in rubric.get("optional", []) or []:
        if _filled(brd.get(opt["field"])):
            continue
        hints = [w for w in opt.get("hint_words", []) if re.search(rf"\b{re.escape(w)}", text)]
        if hints:
            report.warn(f"'{opt['field']}' is not answered but the BRD mentions {', '.join(hints)}")
            gaps.append({"group": "optional", "field": opt["field"], "question": opt.get("question", ""),
                         "context": f"mentions: {', '.join(hints)}"})

    # -- satisfies references
    known = set(req_ids)
    for path, refs in _satisfies(brd):
        bad = [x for x in refs if x not in known]
        if bad:
            report.fail(f"brd.yaml {path} cites unknown requirement(s) {', '.join(bad)}")

    # -- vocabulary
    vocab = reg.vocabulary
    corpus = "\n".join([spec.raw] + _strings({k: v for k, v in brd.items() if k != "changelog"}))
    for kind in ("modelling_terms", "technology_terms"):
        hits = _term_hits(corpus, vocab.get(kind, []) or [])
        label = "modelling vocabulary" if kind == "modelling_terms" else "technology choices"
        report.check(not hits, f"no {label} in the BRD",
                     f"BRD contains {label} that belongs in the TDD: {', '.join(hits)}")
    for pat in vocab.get("patterns", []) or []:
        found = sorted(set(m.group(0) for m in re.finditer(pat["regex"], corpus, re.I)))
        if found:
            report.fail(f"BRD {pat['message']} ({', '.join(found)})")

    # -- sources and glossary (registry consulted, never mutated)
    systems = reg.systems
    for s in brd.get("sources_believed", []) or []:
        if s.get("system") not in systems:
            report.warn(f"source '{s.get('system')}' is not in the source-system registry")
    labels = set()
    for t in reg.glossary_terms:
        labels.add(_norm(t.get("label") or t.get("term") or t.get("id")))
        labels.update(_norm(a) for a in t.get("aliases", []) or [])
    undefined = sorted({x for o in brd.get("required_outputs", []) or []
                        for x in (o.get("figures") or []) + (o.get("attributes") or [])
                        if _norm(x) not in labels})
    report.check(not undefined, "every figure and attribute is defined in the glossary",
                 f"not in the business glossary: {', '.join(undefined)}", warn=True)

    # -- open questions and approval
    for q in brd.get("open_questions", []) or []:
        if not q.get("assumption"):
            report.fail(f"open question {q.get('id')} has no working assumption: {q.get('question')}")
            gaps.append({"group": "open", "field": q.get("id"), "question": q.get("question", ""),
                         "context": f"owner {q.get('owner', 'unassigned')}"})
        else:
            report.warn(f"open question {q.get('id')} proceeds on an assumption; the product stays provisional")
    report.check(brd.get("status") == "approved", "BRD is approved by the business owner",
                 f"BRD status is '{brd.get('status')}'; G0 needs 'approved'")

    if write_gaps:
        write_gap_register(p, gaps)
    return gaps


def _group(rubric: dict, gid: str) -> dict:
    return next((g for g in rubric.get("groups", []) or [] if g.get("id") == gid), {})


def _satisfies(obj, path: str = "") -> list[tuple[str, list[str]]]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "satisfies" and isinstance(v, list):
                out.append((path or "(root)", v))
            else:
                out += _satisfies(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _satisfies(v, f"{path}[{i}]")
    return out


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def write_gap_register(p: Product, gaps: list[dict]) -> None:
    lines = [f"# Gap register — {p.brd.get('brd_id', p.id)}", "",
             f"Generated by `dpf brd validate {p.id}` on {date.today().isoformat()}. Questions to put to the "
             "business owner. Answers go into the BRD (`brd.yaml` or `spec.md`) through an OpenSpec change; "
             "this file is regenerated, never edited.", ""]
    if not gaps:
        lines.append("No gaps. Every rubric group is answered and every requirement has an acceptance scenario.")
    else:
        lines += ["| Group | Field | Question | Context |", "|---|---|---|---|"]
        for g in gaps:
            lines.append(f"| {g['group']} | {g['field']} | {g['question']} | {g['context']} |")
    write_text(p.generated_dir / "gaps.md", "\n".join(lines) + "\n")
