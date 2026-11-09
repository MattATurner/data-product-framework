#!/usr/bin/env python3
"""Mechanical checks for a filled use-case definition (DPF Define, step 1).

The standard is read from the workspace every time, never copied into this skill:

  templates/src/use-case.form.yaml  sections, fields, options, hints and sign-off rows
  templates/scoring.yaml            the scorecard criteria a use case must give evidence for
  registry/brd-vocabulary.yaml      technology and modelling words that belong in the TDD

plus references/evidence-map.yaml in this skill, which names the answers a scorer reads for
each criterion.

Input is a filled 1-use-case.pdf (its form fields; needs pypdf from requirements/templates.txt)
or a use-case YAML shaped like examples/sales_performance/define/use-case.yaml.

The output (JSON by default, or Markdown) holds the answers in one shape whatever the input,
the mechanical findings, the evidence for each scorecard criterion and a provisional verdict.
The judgement checks in SKILL.md come on top. Findings are data, so the exit code is 0 for any
readable input; 2 means a usage error.

Usage:
  check_use_case.py INPUT [--root DIR] [--format json|md] [--out-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
FORM = "framework/templates/src/use-case.form.yaml"
SCORING = "framework/templates/scoring.yaml"
VOCABULARY = "registry/brd-vocabulary.yaml"
EVIDENCE_MAP = SKILL / "references" / "evidence-map.yaml"

ORDER = ("blocking", "should_fix", "suggestion")
VERDICT = {"blocking": "Not ready", "should_fix": "Ready with fixes", None: "Ready for scoring"}

# Control fields a use case cannot be tracked without. The rest of the control block is should-fix.
CONTROL_BLOCKING = {"uc_id", "title", "domain", "proposed_by"}
# Notes the form treats as optional.
OPTIONAL = {"time_notes"}
# Answers whose absence is a should-fix rather than a blocking gap.
SHOULD_FIX_IF_EMPTY = {"date", "version", "status", "classification", "finance_notes"}
# Fields that are identifiers, not prose: no vocabulary check.
NOT_PROSE = {"uc_id", "date", "version", "status", "finance_band", "time_band", "classification"}

EMPTY = {"", "-", "\u2013", "\u2014"}
BARE_UNKNOWN = re.compile(r"^\s*(unknown|not known|tbc|tbd|to be confirmed|\?+)\s*[.!]?\s*$", re.I)
PLACEHOLDER = re.compile(r"^\s*(to be estimated|to be confirmed|tbc|tbd|tbe|unknown|not known|n/?a|\?+)\s*[.!]?\s*$",
                         re.I)
UC_ID = re.compile(r"^UC-[A-Z][A-Z0-9]*-\d{3,}$")
SWOT = {"s": "S", "strength": "S", "strengths": "S", "w": "W", "weakness": "W", "weaknesses": "W",
        "o": "O", "opportunity": "O", "opportunities": "O", "t": "T", "threat": "T", "threats": "T"}
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


# --------------------------------------------------------------------------- workspace and inputs

def find_root(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        if (d / FORM).is_file():
            return d
    return None


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def option_label(opt) -> tuple[str, str]:
    """(id, label) for an option given as a string or a dict, as in templates/src/render.py."""
    if isinstance(opt, dict):
        return str(opt.get("id", opt["label"])), str(opt["label"])
    return str(opt), str(opt)


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(text(v) for v in value if text(v))
    s = str(value).strip()
    return "" if s in EMPTY else s


def from_yaml(path: Path) -> tuple[dict, list]:
    doc = load_yaml(path)
    values = doc.get("values", doc)
    if not isinstance(values, dict):
        raise SystemExit(f"error: {path} holds no mapping of answers")
    return values, list(doc.get("illustrative") or [])


def from_pdf(path: Path, form: dict) -> tuple[dict, list]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("error: reading a PDF needs pypdf: pip install --require-hashes -r requirements/templates.txt")
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    fields = PdfReader(str(path)).get_fields() or {}

    def raw(name):
        return (fields.get(name) or {}).get("/V")

    def field_text(name):
        v = raw(name)
        return "" if v is None or str(v) == "/Off" else text(v)

    def radio(name, options):
        v = raw(name)
        if v is None or str(v) in ("/Off", ""):
            return ""
        state = str(v).lstrip("/").replace("#20", " ")
        labels = [option_label(o) for o in options]
        if state.isdigit() and int(state) < len(labels):   # WeasyPrint names the states 0, 1, 2 ...
            return labels[int(state)][1]
        for oid, label in labels:
            if state.lower() in (oid.lower(), label.lower()):
                return label
        return state

    def checked(name):
        v = raw(name)
        return v is not None and str(v).lstrip("/").lower() not in ("", "off")

    values: dict = {}
    for item in form.get("control", []):
        kind = item.get("kind", "line")
        values[item["id"]] = radio(item["id"], item["options"]) if kind == "choice" else field_text(item["id"])
    for sec in form.get("sections", []):
        for f in sec["fields"]:
            kind, fid = f.get("kind", "line"), f["id"]
            if kind in ("line", "area"):
                values[fid] = field_text(fid)
            elif kind == "choice":
                values[fid] = radio(fid, f["options"])
            elif kind == "checks":
                values[fid] = [oid for oid, _ in map(option_label, f["options"]) if checked(f"{fid}.{oid}")]
            elif kind == "grid":
                rows = []
                for n in range(1, int(f.get("rows", 3)) + 1):
                    row = {c["id"]: field_text(f"{fid}.{n}.{c['id']}") for c in f["columns"]}
                    if any(row.values()):
                        rows.append({"_row": n, **row})
                values[fid] = rows
    signoff = {}
    for i, role in enumerate((form.get("signoff") or {}).get("rows", []), 1):
        entry = {col: field_text(f"signoff.{i}.{col}") for col in ("name", "signature", "date")}
        if any(entry.values()):
            signoff[role or field_text(f"signoff.{i}.role")] = entry
    values["signoff"] = signoff
    return values, []


# --------------------------------------------------------------------------- normalising

def grid_rows(value, columns: list) -> list[dict]:
    """Rows as dicts with every column, plus `_row` (1-based, as numbered on the form)."""
    rows = []
    for i, row in enumerate(value or [], 1):
        if isinstance(row, dict):
            r = {c["id"]: text(row.get(c["id"])) for c in columns}
            n = row.get("_row", i)
        else:
            cells = [text(c) for c in row] + [""] * len(columns)
            r = {c["id"]: cells[k] for k, c in enumerate(columns)}
            n = i
        if any(r.values()):
            rows.append({"_row": n, **r})
    return rows


def normalise(values: dict, form: dict) -> dict:
    out: dict = {}
    for item in form.get("control", []):
        out[item["id"]] = text(values.get(item["id"]))
    for sec in form.get("sections", []):
        for f in sec["fields"]:
            kind, fid = f.get("kind", "line"), f["id"]
            v = values.get(fid)
            if kind == "grid":
                out[fid] = grid_rows(v, f["columns"])
            elif kind == "checks":
                chosen = [text(x) for x in (v if isinstance(v, (list, tuple)) else [v]) if text(x)]
                out[fid] = ordered_options(chosen, f["options"])
            else:
                out[fid] = text(v)
    signoff = {}
    for role, entry in (values.get("signoff") or {}).items():
        entry = entry if isinstance(entry, dict) else {"name": entry}
        signoff[str(role)] = {k: text(entry.get(k)) for k in ("name", "signature", "date")}
    out["signoff"] = signoff
    return out


def matches_option(value: str, options: list) -> bool:
    v = value.strip().lower()
    return any(v in (oid.lower(), label.lower()) for oid, label in map(option_label, options))


def ordered_options(chosen: list[str], options: list) -> list[str]:
    """Ticked options as option ids in the form's order; values that match no option go last, as given."""
    ids = []
    for oid, label in map(option_label, options):
        if any(c.lower() in (oid.lower(), label.lower()) for c in chosen):
            ids.append(oid)
    return ids + [c for c in chosen if not matches_option(c, options)]


def allowed_from_label(label: str) -> list[str]:
    """'Type: profit, cost, revenue, valuation or indirect' -> [profit, cost, revenue, valuation, indirect]."""
    if ":" not in label:
        return []
    tail = label.split(":", 1)[1].replace(" or ", ", ")
    return [t.strip().lower() for t in tail.split(",") if t.strip()]


def numbered(rows: list[int]) -> str:
    rows = [str(r) for r in rows]
    if len(rows) == 1:
        return "row " + rows[0]
    return "rows " + ", ".join(rows[:-1]) + " and " + rows[-1]


# --------------------------------------------------------------------------- checks

class Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check: str, severity: str, section: str, field: str, message: str, question: str,
            quote: str = "", rows: list[int] | None = None):
        assert severity in ORDER, severity
        self.items.append({"id": f"M{len(self.items) + 1}", "check": check, "severity": severity,
                           "section": section, "field": field, "rows": rows or [], "message": message,
                           "quote": quote, "question": question})


def check(ans: dict, form: dict, vocabulary: dict) -> list[dict]:
    fd = Findings()
    how_to_unknown = next((h for h in form.get("how_to", []) if "Unknown" in h), "")

    # Control block
    for item in form.get("control", []):
        fid, label, v = item["id"], item["label"], ans.get(item["id"], "")
        if not v:
            if fid in OPTIONAL:
                continue
            sev = "blocking" if fid in CONTROL_BLOCKING else "should_fix"
            hint = f" ({item['hint']})" if item.get("hint") else ""
            fd.add("required", sev, "Control", fid, f"{label} is empty.", f"What is the {label.lower()}?{hint}")
        elif item.get("kind") == "choice" and not matches_option(v, item["options"]):
            opts = ", ".join(option_label(o)[1] for o in item["options"])
            fd.add("option", "should_fix", "Control", fid, f"{label} is \"{v}\", which is not one of: {opts}.",
                   f"Which of these is the {label.lower()}: {opts}?", quote=v)
    uc_id = ans.get("uc_id", "")
    if uc_id and not UC_ID.match(uc_id):
        fd.add("id-format", "should_fix", "Control", "uc_id",
               f"Use-case ID \"{uc_id}\" does not follow the pattern UC-<DOMAIN>-<number>, for example UC-SALES-001.",
               "Can the ID follow the pattern, for example UC-SALES-001?", quote=uc_id)

    # Sections
    for sec in form.get("sections", []):
        title = sec["title"]
        for f in sec["fields"]:
            kind, fid = f.get("kind", "line"), f["id"]
            label = f.get("label") or title
            v = ans.get(fid)
            ask = (f.get("hint") or sec.get("hint") or "").strip()
            if kind in ("line", "area"):
                if not v:
                    if fid in OPTIONAL:
                        continue
                    sev = "should_fix" if fid in SHOULD_FIX_IF_EMPTY else "blocking"
                    fd.add("required", sev, title, fid, f"{label} is not answered.",
                           (ask.strip() + " " if ask else "") + "If it is not known, write \"Unknown\" and who can answer.")
                elif BARE_UNKNOWN.match(v):
                    fd.add("unknown-no-owner", "should_fix", title, fid,
                           f"{label} says \"{v}\" but names no one who can answer.",
                           "Who can answer this, and by when? " + how_to_unknown, quote=v)
            elif kind == "choice":
                opts = ", ".join(option_label(o)[1] for o in f["options"])
                if not v:
                    fd.add("required", "blocking", title, fid, f"{label}: no band is chosen.", f"Which band fits: {opts}?")
                elif not matches_option(v, f["options"]):
                    fd.add("option", "should_fix", title, fid, f"{label} is \"{v}\", which is not one of: {opts}.",
                           f"Which band fits: {opts}?", quote=v)
            elif kind == "checks":
                if not v:
                    sev = "should_fix" if fid in SHOULD_FIX_IF_EMPTY else "blocking"
                    fd.add("required", sev, title, fid, f"{title}: nothing is ticked.", ask or "Tick all that apply.")
                else:
                    bad = [x for x in v if not matches_option(x, f["options"])]
                    if bad:
                        fd.add("option", "should_fix", title, fid, f"{title}: unknown option {', '.join(bad)}.",
                               "Which of the listed purposes apply?", quote=", ".join(bad))
            elif kind == "grid":
                check_grid(fd, title, f, ask, v or [])

    # Prose: technology and modelling words, and a long description
    check_vocabulary(fd, ans, form, vocabulary)
    desc = ans.get("description", "")
    if desc:
        sentences = [s for s in SENTENCE_END.split(desc.strip()) if s.strip()]
        if len(sentences) > 3:
            fd.add("long-description", "suggestion", "Description", "description",
                   f"The description has {len(sentences)} sentences; the form asks for two or three.",
                   "Can you say what it is about in two or three sentences?")

    # Submission
    so = form.get("signoff") or {}
    for role in so.get("rows", []):
        if not role:
            continue
        name = (ans.get("signoff", {}).get(role) or {}).get("name", "")
        if not name:
            why = "so nobody has checked it before the panel scores it" if role.lower().startswith("review") else \
                "so the panel does not know who submitted it"
            fd.add("signoff", "should_fix", so.get("title", "Submission"), role,
                   f"{so.get('title', 'Submission')}: no name under \"{role}\", {why}.",
                   f"Who signs as \"{role}\"? Give a name and role.")
    return fd.items


def check_grid(fd: Findings, title: str, f: dict, ask: str, value) -> None:
    fid, cols = f["id"], f["columns"]
    rows = grid_rows(value, cols)
    labels = {c["id"]: c["label"] for c in cols}
    complete = [r for r in rows if all(r[c["id"]] for c in cols)]
    partial = [r for r in rows if r not in complete]
    if not complete:
        if rows:
            gaps = "; ".join(f"row {r['_row']} has no {', '.join(labels[c['id']].lower() for c in cols if not r[c['id']])}"
                             for r in partial)
            msg = f"{title}: no row is complete ({gaps})."
            question = " ".join(f"For row {r['_row']}, what is the "
                                f"{', '.join(labels[c['id']].lower() for c in cols if not r[c['id']])}?"
                                for r in partial) + " At least one complete row is needed."
        else:
            msg = f"{title}: no rows are filled in."
            question = ask.strip() or "Please fill in at least one complete row."
        fd.add("no-complete-row", "blocking", title, fid, msg, question, rows=[r["_row"] for r in partial])
    else:
        for r in partial:
            missing = ", ".join(labels[c["id"]].lower() for c in cols if not r[c["id"]])
            fd.add("partial-row", "should_fix", title, fid, f"{title}, row {r['_row']}: no {missing}.",
                   f"What is the {missing} for row {r['_row']}?", rows=[r["_row"]])

    # Column values with a fixed set of answers
    for c in cols:
        cid = c["id"]
        if fid == "swot" and cid == "type":
            bad = [r for r in rows if r[cid] and r[cid].strip().lower().rstrip(".") not in SWOT]
            if bad:
                fd.add("option", "should_fix", title, fid,
                       f"{title}: type must be S, W, O or T ({numbered([r['_row'] for r in bad])}).",
                       "Is each item a strength (S), weakness (W), opportunity (O) or threat (T)?",
                       quote=", ".join(r[cid] for r in bad), rows=[r["_row"] for r in bad])
        allowed = allowed_from_label(c["label"]) if cid == "type" and fid != "swot" else []
        if allowed:
            bad = [r for r in rows if r[cid] and r[cid].strip().lower() not in allowed]
            if bad:
                fd.add("option", "should_fix", title, fid,
                       f"{title}: type must be one of {', '.join(allowed)} ({numbered([r['_row'] for r in bad])}).",
                       f"Which type is each benefit: {', '.join(allowed)}?",
                       quote=", ".join(r[cid] for r in bad), rows=[r["_row"] for r in bad])
        if cid == "size":
            vague = [r for r in rows if r[cid] and PLACEHOLDER.match(r[cid])]
            if vague:
                fd.add("placeholder-size", "should_fix", title, fid,
                       f"{title}: the rough size is \"{vague[0][cid]}\" ({numbered([r['_row'] for r in vague])}).",
                       "What is the rough size of each benefit, even to an order of magnitude?",
                       quote=vague[0][cid], rows=[r["_row"] for r in vague])


def prose(ans: dict, form: dict):
    """(section, field, text) for every free-text answer."""
    for item in form.get("control", []):
        if item["id"] not in NOT_PROSE and ans.get(item["id"]):
            yield "Control", item["id"], ans[item["id"]]
    for sec in form.get("sections", []):
        for f in sec["fields"]:
            fid, kind = f["id"], f.get("kind", "line")
            if fid in NOT_PROSE:
                continue
            if kind in ("line", "area") and ans.get(fid):
                yield sec["title"], fid, ans[fid]
            elif kind == "grid":
                for r in ans.get(fid) or []:
                    for c in f["columns"]:
                        if r.get(c["id"]):
                            yield sec["title"], fid, r[c["id"]]


def check_vocabulary(fd: Findings, ans: dict, form: dict, vocabulary: dict) -> None:
    terms = [(t, "technology") for t in vocabulary.get("technology_terms", [])] + \
            [(t, "modelling") for t in vocabulary.get("modelling_terms", [])]
    hits: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for section, fid, value in prose(ans, form):
        for term, kind in terms:
            m = re.search(r"\b%s\b" % re.escape(term), value, re.I)
            if m:
                hits.setdefault((m.group(0), kind), []).append((section, fid, sentence_around(value, m.start())))
        for p in vocabulary.get("patterns", []):
            m = re.search(p["regex"], value, re.I)
            if m:
                hits.setdefault((m.group(0), "pattern:" + p.get("message", "")), []).append(
                    (section, fid, sentence_around(value, m.start())))
    for (word, kind), where in hits.items():
        section, fid, quote = where[0]
        fields = sorted({w[1] for w in where})
        if kind == "technology":
            msg = f"Names a technology (\"{word}\"). The use case says what is needed, not how; the TDD chooses technology."
            q = "What does the business need here, without naming a product?"
        elif kind == "modelling":
            msg = f"Uses a modelling term (\"{word}\"). Design words belong in the TDD."
            q = "Can you say this in business terms?"
        else:
            msg = f"\"{word}\" {kind.split(':', 1)[1] or 'does not belong in a use case'}."
            q = "Can you say this in business terms?"
        fd.add("vocabulary", "should_fix", section, fids_label(fields), msg, q, quote=quote)


def fids_label(fields: list[str]) -> str:
    return fields[0] if len(fields) == 1 else ", ".join(fields)


def sentence_around(value: str, pos: int) -> str:
    """The sentence of `value` that contains position `pos`, for quoting."""
    start = value.rfind(". ", 0, pos)
    start = 0 if start < 0 else start + 2
    end = value.find(". ", pos)
    end = len(value) if end < 0 else end + 1
    s = value[start:end].strip()
    return s if len(s) <= 220 else s[:217] + "..."


# --------------------------------------------------------------------------- evidence

def evidence(ans: dict, form: dict, scoring: dict, emap: dict, fd_items: list[dict]) -> list[dict]:
    grids = {f["id"]: f for sec in form.get("sections", []) for f in sec["fields"] if f.get("kind") == "grid"}
    mapped = (emap.get("criteria") or {})
    out = []
    for c in scoring.get("criteria", []):
        entry = {"criterion": c["id"], "label": c["label"], "axis": c["axis"], "weight": c["weight"],
                 "asks": c.get("asks", ""), "ask_sponsor": "", "answers": []}
        spec = mapped.get(c["id"])
        if spec is None:
            fd_items.append({"id": f"M{len(fd_items) + 1}", "check": "evidence-map", "severity": "suggestion",
                             "section": "Skill", "field": c["id"], "rows": [],
                             "message": f"references/evidence-map.yaml has no entry for criterion \"{c['id']}\" "
                                        f"in {SCORING}; update the skill.",
                             "quote": "", "question": ""})
            out.append(entry)
            continue
        entry["ask_sponsor"] = spec.get("ask", "")
        for src in spec.get("from", []):
            fid, where = (src, {}) if isinstance(src, str) else (src["field"], src.get("where") or {})
            if fid in grids:
                for r in ans.get(fid) or []:
                    if all(norm_cell(fid, k, r.get(k, "")) in [norm_cell(fid, k, x) for x in (w if isinstance(w, list) else [w])]
                           for k, w in where.items()):
                        cells = " | ".join(r[col["id"]] for col in grids[fid]["columns"] if r.get(col["id"]))
                        entry["answers"].append({"field": fid, "row": r["_row"], "text": cells})
            else:
                v = ans.get(fid)
                v = ", ".join(v) if isinstance(v, list) else (v or "")
                if v:
                    entry["answers"].append({"field": fid, "text": v, "unknown": bool(BARE_UNKNOWN.match(v))})
        out.append(entry)
    return out


def norm_cell(fid: str, col: str, value: str) -> str:
    v = str(value).strip().lower().rstrip(".")
    return SWOT.get(v, v).lower() if (fid, col) == ("swot", "type") else v


# --------------------------------------------------------------------------- report

def assess(path: Path, root: Path) -> dict:
    form, scoring, vocabulary = load_yaml(root / FORM), load_yaml(root / SCORING), load_yaml(root / VOCABULARY)
    emap = load_yaml(EVIDENCE_MAP)
    if path.suffix.lower() == ".pdf":
        values, illustrative, fmt = *from_pdf(path, form), "pdf"
    elif path.suffix.lower() in (".yaml", ".yml"):
        values, illustrative, fmt = *from_yaml(path), "yaml"
    else:
        raise SystemExit(f"error: {path.name}: expected a .pdf or .yaml file")
    ans = normalise(values, form)
    findings = check(ans, form, vocabulary)
    ev = evidence(ans, form, scoring, emap, findings)
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ORDER}
    worst = next((s for s in ORDER[:2] if counts[s]), None)
    try:
        shown = str(path.resolve().relative_to(root))
    except ValueError:
        shown = str(path)
    return {
        "input": shown, "format": fmt,
        "standard": {"form": FORM, "scoring": SCORING, "scoring_version": str(scoring.get("version", "")),
                     "vocabulary": VOCABULARY, "evidence_map": "references/evidence-map.yaml"},
        "use_case": {"id": ans.get("uc_id", ""), "title": ans.get("title", ""), "status": ans.get("status", ""),
                     "proposed_by": ans.get("proposed_by", "")},
        "illustrative": illustrative,
        "sections": ["Control"] + [s["title"] for s in form.get("sections", [])]
                    + ([form["signoff"].get("title", "Sign-off")] if form.get("signoff") else []),
        "provisional_verdict": VERDICT[worst],
        "counts": counts,
        "findings": findings,
        "evidence": ev,
        "answers": ans,
    }


SEV_LABEL = {"blocking": "Blocking", "should_fix": "Should fix", "suggestion": "Suggestion"}


def to_markdown(r: dict) -> str:
    uc = r["use_case"]
    c = r["counts"]
    lines = [f"# Mechanical checks: {uc['id'] or '(no ID)'} {uc['title']}".rstrip(), "",
             f"- Input: `{r['input']}` ({r['format']})",
             f"- Standard: `{r['standard']['form']}`, `{r['standard']['scoring']}` "
             f"{r['standard']['scoring_version']}, `{r['standard']['vocabulary']}`",
             f"- Provisional verdict: **{r['provisional_verdict']}** ({c['blocking']} blocking, "
             f"{c['should_fix']} should fix, {c['suggestion']} suggestions)"]
    if r["illustrative"]:
        lines.append(f"- Illustrative answers (worked example): {', '.join(r['illustrative'])}")
    lines += ["", "## Findings", ""]
    if r["findings"]:
        lines += ["| # | Severity | Section | Field | Finding | Question for the sponsor |", "|---|---|---|---|---|---|"]
        for f in r["findings"]:
            lines.append("| %s | %s | %s | `%s` | %s | %s |" % (f["id"], SEV_LABEL[f["severity"]], f["section"],
                                                           f["field"], md(f["message"]), md(f["question"])))
    else:
        lines.append("None.")
    lines += ["", "## Evidence for the scorecard", "",
              "| Criterion | Axis (weight) | Answers a scorer would read |", "|---|---|---|"]
    for e in r["evidence"]:
        if e["answers"]:
            shown = "<br>".join(md(f"{a['field']}{' row ' + str(a['row']) if a.get('row') else ''}: {a['text']}")
                                for a in e["answers"])
        else:
            shown = md(f"None. Ask: {e['ask_sponsor']}") if e["ask_sponsor"] else "None."
        lines.append(f"| {e['label']} | {e['axis'].capitalize()} ({e['weight']}) | {shown} |")
    return "\n".join(lines) + "\n"


def md(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mechanical checks for a filled DPF use-case definition.")
    ap.add_argument("input", type=Path, help="filled 1-use-case.pdf or use-case YAML")
    ap.add_argument("--root", type=Path, help="workspace root (default: found from the input or the current directory)")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    ap.add_argument("--out-dir", type=Path, help="also write checks.json and checks.md to this directory")
    a = ap.parse_args(argv)
    if not a.input.is_file():
        print(f"error: {a.input} not found", file=sys.stderr)
        return 2
    root = a.root or find_root(a.input.resolve().parent) or find_root(Path.cwd())
    if root is None or not (root / FORM).is_file():
        print(f"error: no DPF workspace found ({FORM} is missing); pass --root", file=sys.stderr)
        return 2
    result = assess(a.input, root.resolve())
    if a.out_dir:
        a.out_dir.mkdir(parents=True, exist_ok=True)
        (a.out_dir / "checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (a.out_dir / "checks.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result) if a.format == "md" else json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
