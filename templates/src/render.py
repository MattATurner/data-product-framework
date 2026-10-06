#!/usr/bin/env python3
"""Render the Define-stage templates as fillable PDFs, and the worked examples as filled PDFs.

    python templates/src/render.py                 # templates and worked examples
    python templates/src/render.py --templates     # templates only

Wording lives in templates/src/*.form.yaml, the scoring model in templates/scoring.yaml and the
look in templates/src/style.css. Worked-example values live beside each example. Needs
WeasyPrint and pypdf: `pip install --require-hashes -r requirements/templates.txt`.

This is a documentation build step. dpf does not read these templates and no gate checks them.
"""

from __future__ import annotations

import argparse
import html
import io
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "templates" / "src"
OUT = ROOT / "templates" / "define"
SCORING = ROOT / "templates" / "scoring.yaml"
PORTFOLIO_EXAMPLE = ROOT / "examples" / "use-case-portfolio"
SALES_EXAMPLE = ROOT / "examples" / "sales_performance" / "define"
SALES_BRD = ROOT / "openspec" / "specs" / "products" / "sales" / "sales-performance" / "brd"

# Fixed so that re-rendering unchanged sources gives identical files.
PDF_DATE = "2026-10-06T00:00:00Z"

STEPS = [(1, "Use case", "Describe it"), (2, "Scorecard", "Score it"), (3, "Prioritisation", "Choose"),
         (4, "BRD or PRD", "Require it"), (5, "TDD", "Next stage")]


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def joined(value, sep: str = ", ") -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return sep.join(str(v) for v in value)
    return str(value)


# ---------------------------------------------------------------------------------------------
# Rendering context: a blank template (form fields) or a filled example (values).
# ---------------------------------------------------------------------------------------------

class Ctx:
    def __init__(self, values: dict | None = None, illustrative=()):
        self.filled = values is not None
        self.values = values or {}
        self.illustrative = set(illustrative or ())

    def get(self, key, default=None):
        return self.values.get(key, default)

    def tag(self, key) -> str:
        return ' <span class="illus">Illustrative</span>' if self.filled and key in self.illustrative else ""


def text_input(name: str, default: str = "", cls: str = "") -> str:
    klass = ' class="%s"' % cls if cls else ""
    return '<input type="text" name="%s" value="%s"%s>' % (esc(name), esc(default), klass)


def textarea(name: str, lines: int = 2) -> str:
    return '<textarea name="%s" style="height:%.1fmm"></textarea>' % (esc(name), 4.1 * lines + 2.2)


def value_box(value) -> str:
    text = joined(value, "\n").strip()
    if not text:
        return '<div class="value empty">-</div>'
    return '<div class="value">%s</div>' % esc(text)


def option_label(opt) -> tuple[str, str, str]:
    """(id, label, hint) for an option given as a string or a dict."""
    if isinstance(opt, dict):
        return str(opt.get("id", opt["label"])), str(opt["label"]), str(opt.get("hint", ""))
    return str(opt), str(opt), ""


def render_choice(name: str, options: list, ctx: Ctx, multi: bool, layout: str = "") -> str:
    selected = ctx.get(name) if ctx.filled else None
    if multi:
        chosen = {str(s).lower() for s in (selected or [])}
    else:
        chosen = {str(selected).lower()} if selected else set()
    items = []
    for opt in options:
        oid, label, hint = option_label(opt)
        hint_html = ' <span class="ohint">%s</span>' % esc(hint) if hint else ""
        if ctx.filled:
            on = oid.lower() in chosen or label.lower() in chosen
            mark = "&#10003;" if (on and multi) else ("&#9679;" if on else "")
            box = '<span class="box%s%s">%s</span>' % ("" if multi else " round", " on" if on else "", mark)
            items.append('<div class="opt%s">%s<span>%s%s</span></div>' % ("" if on else " off", box, esc(label), hint_html))
        elif multi:
            items.append('<div class="opt"><input type="checkbox" name="%s.%s"><span>%s%s</span></div>'
                         % (esc(name), esc(oid), esc(label), hint_html))
        else:
            items.append('<div class="opt"><input type="radio" name="%s" value="%s"><span>%s%s</span></div>'
                         % (esc(name), esc(oid), esc(label), hint_html))
    return '<div class="choices %s">%s</div>' % (layout, "".join(items))


def grid_rows(value, columns: list) -> list[list[str]]:
    rows = []
    for row in value or []:
        if isinstance(row, dict):
            rows.append([joined(row.get(c["id"])) for c in columns])
        else:
            cells = [joined(c) for c in row]
            rows.append(cells + [""] * (len(columns) - len(cells)))
    return rows


def render_grid(field: dict, ctx: Ctx) -> str:
    cols = field["columns"]
    colgroup = "".join('<col style="width:%s%%">' % c.get("width", 100 // len(cols)) for c in cols)
    head = "".join("<th>%s</th>" % esc(c["label"]) for c in cols)
    body = []
    if ctx.filled:
        rows = grid_rows(ctx.get(field["id"]), cols)
        if not rows:
            body.append('<tr><td colspan="%d"><div class="cellv">%s</div></td></tr>'
                        % (len(cols), esc(field.get("empty", "None."))))
        for row in rows:
            body.append("<tr>%s</tr>" % "".join('<td><div class="cellv">%s</div></td>' % esc(cell) for cell in row))
    else:
        for n in range(1, int(field.get("rows", 3)) + 1):
            cells = []
            for c in cols:
                name = "%s.%d.%s" % (field["id"], n, c["id"])
                default = str(c.get("default", "")).replace("{n}", str(n))
                if default:
                    cells.append("<td>%s</td>" % text_input(name, default))
                else:
                    cells.append('<td><textarea name="%s"></textarea></td>' % esc(name))
            body.append("<tr>%s</tr>" % "".join(cells))
    return ('<table class="grid%s"><colgroup>%s</colgroup><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % ("" if ctx.filled else " blank", colgroup, head, "".join(body)))


def render_requirements(field: dict, ctx: Ctx) -> str:
    out = []
    if ctx.filled:
        for r in ctx.get(field["id"]) or []:
            parts = ['<div class="req"><div><span class="rid">%s</span><span class="rtitle">%s</span></div>'
                     % (esc(r["id"]), esc(r["title"])),
                     '<div class="rbody">%s</div>' % esc(r["statement"])]
            for s in r.get("scenarios", []):
                steps = "".join('<div class="step"><span class="kw">%s</span>%s</div>' % (esc(k), esc(t))
                                for k, t in s["steps"])
                parts.append('<div class="axv"><div class="axt">%s &#183; %s</div>%s</div>'
                             % (esc(s["id"]), esc(s["title"]), steps))
            parts.append("</div>")
            out.append("".join(parts))
        return "".join(out)
    for n in range(1, int(field.get("count", 6)) + 1):
        base = "%s.%d" % (field["id"], n)
        gwt = "".join("<tr><th>%s</th><td>%s</td></tr>" % (k, text_input("%s.ax.%s" % (base, k.lower())))
                      for k in ("GIVEN", "WHEN", "THEN", "AND"))
        out.append(
            '<div class="req">'
            '<div class="head"><span class="tag">Requirement</span>%s%s</div>'
            '<div class="stmt">%s</div>'
            '<div class="ax"><div class="head"><span class="tag">Acceptance example</span>%s%s</div>'
            '<table class="gwt">%s</table></div></div>'
            % (text_input(base + ".id", "R-%d" % n, "id"), text_input(base + ".title", "", "title"),
               textarea(base + ".statement", 2),
               text_input(base + ".ax.id", "AX-%d" % n, "id"), text_input(base + ".ax.title", "", "title"), gwt))
    return "".join(out)


def render_control_value(item: dict, ctx: Ctx) -> str:
    kind = item.get("kind", "line")
    if kind == "choice":
        return render_choice(item["id"], item["options"], ctx, multi=False)
    if ctx.filled:
        return value_box(ctx.get(item["id"]))
    return text_input(item["id"], str(item.get("default", "")))


def render_control(items: list, ctx: Ctx) -> str:
    cells = []
    for it in items:
        hint = '<div class="hint">%s</div>' % esc(it["hint"]) if it.get("hint") and not ctx.filled else ""
        cells.append('<div class="cell%s"><div class="label">%s%s</div>%s%s</div>'
                     % (" wide" if it.get("wide") else "", esc(it["label"]), ctx.tag(it["id"]),
                        render_control_value(it, ctx), hint))
    return '<div class="control">%s</div>' % "".join(cells)


def render_field(field: dict, ctx: Ctx) -> str:
    kind = field.get("kind", "line")
    fid = field["id"]
    if kind == "line":
        ctrl = value_box(ctx.get(fid)) if ctx.filled else text_input(fid, str(field.get("default", "")))
    elif kind == "area":
        ctrl = value_box(ctx.get(fid)) if ctx.filled else textarea(fid, int(field.get("lines", 2)))
    elif kind == "choice":
        ctrl = render_choice(fid, field["options"], ctx, multi=False)
    elif kind == "checks":
        ctrl = render_choice(fid, field["options"], ctx, multi=True, layout="list")
    elif kind == "grid":
        ctrl = render_grid(field, ctx)
    elif kind == "requirements":
        ctrl = render_requirements(field, ctx)
    else:
        raise ValueError("unknown field kind %r in %s" % (kind, fid))
    label = field.get("label")
    hint = '<div class="hint">%s</div>' % esc(field["hint"]) if field.get("hint") else ""
    long_block = kind == "requirements" or (kind == "grid" and ctx.filled and len(ctx.get(fid) or []) > 6)
    stack = "stack breakable" if long_block else "stack"
    if not label:
        return '<div class="%s">%s</div>' % (stack, ctrl)
    label_html = '<div class="label">%s%s</div>' % (esc(label), ctx.tag(fid))
    if kind in ("line", "area", "choice"):
        return '<div class="row"><div class="lhs">%s%s</div><div class="rhs">%s</div></div>' % (label_html, hint, ctrl)
    return '<div class="%s">%s%s%s</div>' % (stack, label_html, hint, ctrl)


def number_sections(spec: dict) -> list[tuple[int | None, dict]]:
    out, n = [], 0
    for sec in spec.get("sections", []):
        if sec.get("numbered", True):
            n += 1
            out.append((n, sec))
        else:
            out.append((None, sec))
    return out


def render_section(num, sec: dict, ctx: Ctx) -> str:
    badge = '<span class="num">%d</span>' % num if num else ""
    tags = "".join(ctx.tag(f["id"]) for f in sec["fields"] if not f.get("label"))
    hint = '<p class="hint">%s</p>' % esc(sec["hint"]) if sec.get("hint") else ""
    parts = ['<section class="sec"><div class="sec-head"><h2>%s<span>%s</span>%s</h2>%s</div>'
             % (badge, esc(sec["title"]), tags, hint)]
    parts.extend(render_field(f, ctx) for f in sec["fields"])
    parts.append("</section>")
    return "".join(parts)


def render_signoff(signoff: dict, ctx: Ctx) -> str:
    if not signoff:
        return ""
    names = ctx.get("signoff", {}) if ctx.filled else {}
    rows = []
    for i, role in enumerate(signoff.get("rows", []), 1):
        role_cell = '<td class="role">%s</td>' % esc(role) if role else (
            '<td><div class="cellv"></div></td>' if ctx.filled else '<td class="in">%s</td>' % text_input("signoff.%d.role" % i))
        cells = []
        for col in ("name", "signature", "date"):
            if ctx.filled:
                cells.append('<td><div class="cellv">%s</div></td>' % esc((names.get(role) or {}).get(col, "")))
            else:
                cells.append('<td class="in">%s</td>' % text_input("signoff.%d.%s" % (i, col)))
        rows.append("<tr>%s%s</tr>" % (role_cell, "".join(cells)))
    hint = '<p class="hint">%s</p>' % esc(signoff["hint"]) if signoff.get("hint") else ""
    return ('<section class="sec signoff"><h2><span>%s</span></h2>%s<table class="sign%s"><colgroup><col style="width:24%%">'
            '<col style="width:30%%"><col style="width:30%%"><col style="width:16%%"></colgroup><thead><tr>'
            '<th>Role</th><th>Name</th><th>Signature</th><th>Date</th></tr></thead><tbody>%s</tbody></table></section>'
            % (esc(signoff.get("title", "Sign-off")), hint, " compact" if signoff.get("compact") else "", "".join(rows)))


def render_cover(spec: dict, ctx: Ctx, ref: str, banner: str = "", show_howto: bool = True) -> str:
    step = int(spec["step"])
    chips = []
    for n, name, verb in STEPS:
        cls = "chip" + (" on" if n == step else "") + (" design" if n == 5 else "")
        label = ("Define %d" % n) if n < 5 else "Design"
        chips.append('<div class="%s"><b>%s</b>%s &#183; %s</div>' % (cls, esc(name), label, esc(verb)))
    kicker = '%s<span class="stage">%s</span> &#183; Step %d of 4' % (
        "Worked example &#183; " if ctx.filled else "", esc(spec["stage"]), step)
    parts = ['<div class="cover"><div class="kicker">%s</div><h1>%s</h1>' % (kicker, esc(spec["title"]))]
    if spec.get("intro"):
        parts.append('<div class="intro">%s</div>' % esc(spec["intro"]))
    if spec.get("alternative"):
        parts.append('<div class="alt">%s</div>' % esc(spec["alternative"]))
    parts.append('<div class="flow">%s</div>' % "".join(chips))
    if banner:
        parts.append('<div class="example-banner"><strong>Worked example.</strong> %s</div>' % esc(banner))
    elif show_howto and spec.get("how_to"):
        parts.append('<div class="howto"><h3>How to fill this in</h3><ul>%s</ul></div>'
                     % "".join("<li>%s</li>" % esc(h) for h in spec["how_to"]))
    parts.append('<div class="ref">%s</div></div>' % esc(ref))
    return "".join(parts)


def render_next(spec: dict) -> str:
    return '<div class="next"><b>Next:</b> %s</div>' % esc(spec["next"]) if spec.get("next") else ""


def render_appendix(spec: dict) -> str:
    rows = []
    for num, sec in number_sections(spec):
        if not sec.get("maps_to"):
            continue
        rows.append("<tr><td>%s</td><td>%s</td><td><code>%s</code></td></tr>"
                    % (esc(("%d. " % num if num else "") + sec["title"]), esc(sec.get("rubric", "-")), esc(sec["maps_to"])))
    if not rows:
        return ""
    prd_note = ""
    if spec["name"] == "prd":
        prd_note = (
            "<p>A PRD is recorded in the same place as a BRD, because both answer the same rubric. "
            "Keep the number: <code>PRD-SALES-003</code> is recorded as <code>BRD-SALES-003</code>, and the "
            "Purpose line names the source document, for example <code>**Source:** PRD-SALES-003 v1.0.0</code>. "
            "Product summary, success measures, releases and risks stay with the PRD.</p>")
    return (
        '<section class="appendix"><h2><span>For the data team: where each answer goes</span></h2>'
        "<p>Record the approved document in the repository with the <code>author-brd</code> skill, as "
        "<code>openspec/specs/products/&lt;domain&gt;/&lt;product&gt;/brd/spec.md</code> and <code>brd.yaml</code>. "
        "Put the use case on the Purpose line, for example <code>**Use case:** UC-SALES-001</code>. Then run "
        "<code>dpf brd validate &lt;product&gt;</code> (gate G0) and take any gaps back to the business.</p>%s"
        '<table><thead><tr><th style="width:34%%">Section</th><th style="width:12%%">Rubric group</th>'
        '<th>Recorded in</th></tr></thead><tbody>%s</tbody></table></section>' % (prd_note, "".join(rows)))


def document(title: str, description: str, body: str, wide: bool = False) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>%s</title>'
            '<meta name="author" content="Data Product Framework">'
            '<meta name="description" content="%s">'
            '<meta name="keywords" content="data product, define, use case, BRD, PRD">'
            '<meta name="generator" content="templates/src/render.py">'
            '<meta name="dcterms.created" content="%s"><meta name="dcterms.modified" content="%s">'
            '</head><body class="%s">%s</body></html>'
            % (esc(title), esc(description), PDF_DATE, PDF_DATE, "wide" if wide else "", body))


# ---------------------------------------------------------------------------------------------
# Form documents: use case, BRD, PRD
# ---------------------------------------------------------------------------------------------

def build_form(spec: dict, version: str, ctx: Ctx, ref: str = "", banner: str = "") -> str:
    ref = ref or "%s &#183; template %s" % (spec["title"], version)
    parts = [render_cover(spec, ctx, html.unescape(ref), banner), render_control(spec.get("control", []), ctx)]
    parts.extend(render_section(num, sec, ctx) for num, sec in number_sections(spec))
    parts.append(render_signoff(spec.get("signoff"), ctx))
    parts.append(render_next(spec))
    parts.append(render_appendix(spec))
    return document(spec["title"], spec.get("intro", ""), "".join(parts))


# ---------------------------------------------------------------------------------------------
# Scoring: scorecard and prioritisation matrix
# ---------------------------------------------------------------------------------------------

def quadrant_for(scoring: dict, value: float, ease: float) -> dict:
    t = float(scoring["threshold"])
    want = ("high" if value >= t else "low", "high" if ease >= t else "low")
    for q in scoring["quadrants"]:
        if (q["value"], q["ease"]) == want:
            return q
    raise ValueError("no quadrant for %s" % (want,))


def score(scoring: dict, uc: dict) -> dict:
    """Weighted scores, axis scores, total and quadrant for one use case."""
    weights = {c["id"]: int(c["weight"]) for c in scoring["criteria"]}
    weights.update(uc.get("weights") or {})
    s = uc["scores"]
    missing = [c["id"] for c in scoring["criteria"] if s.get(c["id"]) is None]
    if missing:
        raise ValueError("%s has no score for %s" % (uc["id"], ", ".join(missing)))
    weighted = {cid: weights[cid] * int(s[cid]) for cid in weights}
    out = {"weighted": weighted, "weights": weights}
    for axis in ("value", "ease"):
        ids = [c["id"] for c in scoring["criteria"] if c["axis"] == axis]
        out[axis + "_total"] = sum(weighted[i] for i in ids)
        out[axis + "_weights"] = sum(weights[i] for i in ids)
        out[axis] = out[axis + "_total"] / out[axis + "_weights"]
    out["total"] = out["value_total"] + out["ease_total"]
    out["max"] = int(scoring["scale"]["max"]) * sum(weights.values())
    out["quadrant"] = quadrant_for(scoring, out["value"], out["ease"])
    return out


def scoring_guide(scoring: dict) -> str:
    rows = []
    for i, c in enumerate(scoring["criteria"], 1):
        g = c["guide"]
        rows.append(
            '<tr><td class="w">%d</td><td class="c">%s%s</td><td>%s</td><td class="w">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            % (i, esc(c["label"]), '<span class="axis-chip new">Added</span>' if c.get("added") else "",
               esc(scoring["axes"][c["axis"]]["label"]), c["weight"], esc(g[1]), esc(g[3]), esc(g[5])))
    return ('<h2><span>Scoring guide</span></h2>'
            '<p class="hint">Use these descriptions so that a score means the same thing to everyone. A 2 or a 4 sits '
            'between the descriptions on either side. Higher is always better. The weights are the defaults; '
            'criteria marked Added are new to this framework.</p>'
            '<table class="guide"><colgroup><col style="width:3%%"><col style="width:19%%"><col style="width:6%%">'
            '<col style="width:6%%"><col style="width:22%%"><col style="width:22%%"><col style="width:22%%"></colgroup>'
            '<thead><tr><th>#</th><th>Criterion</th><th>Axis</th><th>Weight</th><th>Scores 1</th><th>Scores 3</th>'
            '<th>Scores 5</th></tr></thead><tbody>%s</tbody></table>' % "".join(rows))


def build_scorecard(spec: dict, scoring: dict, version: str, portfolio: dict | None = None) -> str:
    ctx = Ctx(portfolio if portfolio is not None else None)
    crits = scoring["criteria"]
    ucs = portfolio["use_cases"] if portfolio else [None] * int(spec["slots"])
    results = [score(scoring, uc) for uc in ucs] if portfolio else [None] * len(ucs)
    illus = set((portfolio or {}).get("illustrative_criteria", []))
    w_value = sum(int(c["weight"]) for c in crits if c["axis"] == "value")
    w_ease = sum(int(c["weight"]) for c in crits if c["axis"] == "ease")
    max_total = int(scoring["scale"]["max"]) * (w_value + w_ease)
    k = len(ucs)
    slot_w = 62.0 / max(k, 3)
    cols = ['<col style="width:3%">', '<col style="width:%.2f%%">' % (97 - 7 - slot_w * k), '<col style="width:7%">']
    for _ in ucs:
        cols += ['<col style="width:%.2f%%">' % (slot_w * 0.45), '<col style="width:%.2f%%">' % (slot_w * 0.55)]

    def slot_head(i, uc, key):
        if uc is not None:
            return '<th colspan="2" class="uchead" style="text-align:left">%s</th>' % esc(uc.get(key, ""))
        return '<th colspan="2" class="uchead in">%s</th>' % text_input("uc.%d.%s" % (i, key))

    head1 = ('<tr><th rowspan="3">#</th><th colspan="2" class="rowlbl">Use-case ID</th>%s</tr>'
             % "".join(slot_head(i, uc, "id") for i, uc in enumerate(ucs, 1)))
    head2 = ('<tr><th colspan="2" class="rowlbl">Title</th>%s</tr>'
             % "".join(slot_head(i, uc, "title") for i, uc in enumerate(ucs, 1)))
    head3 = ('<tr><th style="text-align:left">Criterion</th><th>Weight (1&#8211;5)</th>%s</tr>'
             % "".join("<th>Score</th><th>W &#215; S</th>" for _ in ucs))

    body = []
    n = 0
    for axis in ("value", "ease"):
        body.append('<tr class="group"><td colspan="%d">%s &#8212; %s</td></tr>'
                    % (3 + 2 * k, esc(scoring["axes"][axis]["label"]), esc(scoring["axes"][axis]["question"])))
        for c in [c for c in crits if c["axis"] == axis]:
            n += 1
            chip = '<span class="axis-chip new">Added</span>' if c.get("added") else ""
            row = ['<td>%d</td>' % n,
                   '<td class="crit">%s%s<span class="ask">%s</span></td>' % (esc(c["label"]), chip, esc(c["asks"]))]
            if portfolio:
                row.append('<td class="v">%s</td>' % c["weight"])
            else:
                row.append('<td class="in w">%s</td>' % text_input("weight.%s" % c["id"], str(c["weight"])))
            for i, (uc, res) in enumerate(zip(ucs, results), 1):
                if uc is not None:
                    cls = " illus" if c["id"] in illus else ""
                    mark = "&#8224;" if c["id"] in illus else ""
                    row.append('<td class="v%s">%s%s</td>' % (cls, uc["scores"][c["id"]], mark))
                    row.append('<td class="v calc">%s</td>' % res["weighted"][c["id"]])
                else:
                    row.append('<td class="in">%s</td>' % text_input("score.%d.%s" % (i, c["id"])))
                    row.append('<td class="in calc">%s</td>' % text_input("weighted.%d.%s" % (i, c["id"])))
            body.append("<tr>%s</tr>" % "".join(row))

    def sum_row(key, label, fmt, cls="sum"):
        cells = ['<td colspan="3" class="lbl">%s</td>' % label]
        for i, (uc, res) in enumerate(zip(ucs, results), 1):
            if uc is not None:
                cells.append('<td colspan="2" class="v">%s</td>' % fmt(res))
            else:
                cells.append('<td colspan="2" class="in calc">%s</td>' % text_input("%s.%d" % (key, i)))
        return '<tr class="%s">%s</tr>' % (cls, "".join(cells))

    t = float(scoring["threshold"])
    body.append(sum_row("value_total", "Value total (add the W &#215; S value rows)", lambda r: r["value_total"]))
    body.append(sum_row("value_score", "Value score = value total &#247; sum of value weights (%d by default)" % w_value,
                        lambda r: "%.2f" % r["value"]))
    body.append(sum_row("ease_total", "Ease total (add the W &#215; S ease rows)", lambda r: r["ease_total"]))
    body.append(sum_row("ease_score", "Ease score = ease total &#247; sum of ease weights (%d by default)" % w_ease,
                        lambda r: "%.2f" % r["ease"]))
    body.append(sum_row("total", "Overall total (out of %d by default)" % max_total,
                        lambda r: "%d &#160;(%d%%)" % (r["total"], round(100.0 * r["total"] / r["max"])), "sum total"))
    body.append(sum_row("quadrant", "Quadrant (high = %.1f or more)" % t,
                        lambda r: '<span class="qpill %s">%s</span>' % (r["quadrant"]["id"], esc(r["quadrant"]["label"]))))

    table = ('<table class="score"><colgroup>%s</colgroup><thead>%s%s%s</thead><tbody>%s</tbody></table>'
             % ("".join(cols), head1, head2, head3, "".join(body)))

    if portfolio:
        ref = "%s &#183; worked example" % portfolio.get("title", "Scorecard")
        cover = render_cover(spec, ctx, html.unescape(ref), portfolio.get("note", ""))
        control = render_control([{"id": "title", "label": "Portfolio"}, {"id": "assessed_on", "label": "Date"},
                                  {"id": "panel", "label": "Scored by"}], ctx)
        foot = ""
        if illus:
            foot = '<p class="footnote">&#8224; Illustrative score: %s</p>' % esc(portfolio.get("illustrative_note", ""))
        foot += "".join('<p class="footnote">%s</p>' % esc(f) for f in portfolio.get("footnotes") or [])
    else:
        ref = "%s &#183; template %s" % (spec["title"], version)
        cover = render_cover(spec, ctx, html.unescape(ref))
        control = render_control([{"id": "portfolio", "label": "Portfolio or round"},
                                  {"id": "date", "label": "Date"}, {"id": "panel", "label": "Scored by"}], ctx)
        foot = ""
    parts = [cover, control, scoring_guide(scoring),
             '<section style="break-before: page"><h2><span>Scores</span></h2>', table, foot, render_next(spec), "</section>"]
    return document(spec["title"], spec.get("intro", ""), "".join(parts), wide=True)


QUAD_FILL = {"quick_win": ("#e6f4ea", "#137333"), "strategic_bet": ("#e8f0fe", "#1967d2"),
             "fill_in": ("#fef7e0", "#b06000"), "deprioritise": ("#fce8e6", "#c5221f")}


def matrix_svg(scoring: dict, points: list[tuple[str, float, float, str]]) -> str:
    """Value (up) against ease (right), 1 to 5, split at the threshold."""
    W, H = 600, 470
    x0, x1, y0, y1 = 58, 588, 12, 412
    lo, hi = float(scoring["scale"]["min"]), float(scoring["scale"]["max"])
    t = float(scoring["threshold"])

    def X(e):
        return x0 + (e - lo) / (hi - lo) * (x1 - x0)

    def Y(v):
        return y1 - (v - lo) / (hi - lo) * (y1 - y0)

    q = {qq["id"]: qq for qq in scoring["quadrants"]}
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="128mm" font-family="Roboto, sans-serif">' % (W, H)]
    rects = [("strategic_bet", x0, y0, X(t), Y(t)), ("quick_win", X(t), y0, x1, Y(t)),
             ("deprioritise", x0, Y(t), X(t), y1), ("fill_in", X(t), Y(t), x1, y1)]
    for qid, ax, ay, bx, by in rects:
        fill, ink = QUAD_FILL[qid]
        s.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (ax, ay, bx - ax, by - ay, fill))
        lx = ax + 10 if qid in ("strategic_bet", "deprioritise") else bx - 10
        anchor = "start" if qid in ("strategic_bet", "deprioritise") else "end"
        ly = ay + 22 if qid in ("strategic_bet", "quick_win") else by - 12
        s.append('<text x="%.1f" y="%.1f" font-size="15" font-weight="700" fill="%s" text-anchor="%s">%s</text>'
                 % (lx, ly, ink, anchor, esc(q[qid]["label"])))
    for v in range(int(lo), int(hi) + 1):
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#ffffff" stroke-width="1"/>' % (x0, Y(v), x1, Y(v)))
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#ffffff" stroke-width="1"/>' % (X(v), y0, X(v), y1))
        s.append('<text x="%.1f" y="%.1f" font-size="12" fill="#5f6368" text-anchor="end">%d</text>' % (x0 - 8, Y(v) + 4, v))
        s.append('<text x="%.1f" y="%.1f" font-size="12" fill="#5f6368" text-anchor="middle">%d</text>' % (X(v), y1 + 18, v))
    s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#5f6368" stroke-width="1.2" stroke-dasharray="5 4"/>' % (X(t), y0, X(t), y1))
    s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#5f6368" stroke-width="1.2" stroke-dasharray="5 4"/>' % (x0, Y(t), x1, Y(t)))
    s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#9aa0a6" stroke-width="1"/>' % (x0, y0, x1 - x0, y1 - y0))
    s.append('<text x="%.1f" y="%d" font-size="13" font-weight="500" fill="#3c4043" text-anchor="middle">%s: %s &#8594;</text>'
             % ((x0 + x1) / 2, H - 12, esc(scoring["axes"]["ease"]["label"]), "easier to deliver"))
    s.append('<text transform="translate(16 %.1f) rotate(-90)" font-size="13" font-weight="500" fill="#3c4043" text-anchor="middle">%s: %s &#8594;</text>'
             % ((y0 + y1) / 2, esc(scoring["axes"]["value"]["label"]), "matters more"))
    for label, ease, value, qid in points:
        _, ink = QUAD_FILL[qid]
        px, py = X(ease), Y(value)
        s.append('<circle cx="%.1f" cy="%.1f" r="8" fill="%s" stroke="#ffffff" stroke-width="2"/>' % (px, py, ink))
        # Keep the label off the dashed threshold line when the point sits close to it.
        dy = -9.0 if abs(value - t) < 0.2 else 4.5
        s.append('<text x="%.1f" y="%.1f" font-size="13" font-weight="700" fill="#202124">%s</text>' % (px + 12, py + dy, esc(label)))
    s.append("</svg>")
    return "".join(s)


def build_prioritisation(spec: dict, scoring: dict, version: str, portfolio: dict | None = None) -> str:
    ctx = Ctx(portfolio if portfolio is not None else None)
    t = float(scoring["threshold"])
    points, rows = [], []
    if portfolio:
        for uc in portfolio["use_cases"]:
            r = score(scoring, uc)
            points.append((uc["id"], r["ease"], r["value"], r["quadrant"]["id"]))
            d = uc.get("decision") or {}
            rows.append(
                "<tr><td><div class=\"cellv\"><b>%s</b><br>%s</div></td><td class=\"ctr\">%.2f</td><td class=\"ctr\">%.2f</td>"
                "<td class=\"ctr\"><span class=\"qpill %s\">%s</span></td><td><div class=\"cellv\"><b>%s</b></div></td>"
                "<td><div class=\"cellv\">%s</div></td><td class=\"ctr\">%s</td><td><div class=\"cellv\">%s</div></td></tr>"
                % (esc(uc["id"]), esc(uc["title"]), r["value"], r["ease"], r["quadrant"]["id"], esc(r["quadrant"]["label"]),
                   esc(d.get("decision", "")), esc(d.get("reason", "")), esc(d.get("next", "")), esc(d.get("owner", ""))))
    else:
        for i in range(1, int(spec["rows"]) + 1):
            dec = render_choice("decision.%d" % i, ["Approve", "Defer", "Reject"], ctx, multi=False)
            nxt = render_choice("next.%d" % i, ["BRD", "PRD"], ctx, multi=False)
            rows.append(
                '<tr><td class="in">%s</td><td class="in">%s</td><td class="in">%s</td><td class="in">%s</td><td>%s</td>'
                '<td class="in"><textarea name="reason.%d"></textarea></td><td>%s</td><td class="in">%s</td></tr>'
                % (text_input("uc.%d" % i), text_input("value.%d" % i), text_input("ease.%d" % i), text_input("quadrant.%d" % i),
                   dec, i, nxt, text_input("owner.%d" % i)))
    legend = []
    for qd in scoring["quadrants"]:
        rule = "Value %s, ease %s (high = %.1f or more)" % (qd["value"], qd["ease"], t)
        legend.append('<div class="quad %s"><div class="qt">%s</div><div class="qr">%s</div>%s</div>'
                      % (qd["id"], esc(qd["label"]), esc(rule), esc(qd["action"])))
    matrix = ('<div class="matrix-wrap"><div class="plot">%s</div><div class="legend">%s</div></div>'
              % (matrix_svg(scoring, points), "".join(legend)))
    decide = ('<h2><span>Decision record</span></h2><p class="hint">One row per use case. The quadrant suggests an action; '
              'record what was decided, why, and any conditions.</p>'
              '<table class="decide"><colgroup><col style="width:17%"><col style="width:6%"><col style="width:6%">'
              '<col style="width:11%"><col style="width:12%"><col style="width:28%"><col style="width:9%"><col style="width:11%">'
              '</colgroup><thead><tr><th>Use case</th><th>Value</th><th>Ease</th><th>Quadrant</th><th>Decision</th>'
              '<th>Reason and conditions</th><th>Next</th><th>Owner</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>')
    sign = render_signoff({"title": "Decided by", "rows": ["Chair", "", ""], "compact": True}, ctx)
    if portfolio:
        ref = "%s &#183; worked example" % portfolio.get("title", "Prioritisation")
        parts = [render_cover(spec, ctx, html.unescape(ref), portfolio.get("note", "")), matrix,
                 '<section style="break-before: page">', decide, render_next(spec), "</section>"]
    else:
        ref = "%s &#183; template %s" % (spec["title"], version)
        parts = [render_cover(spec, ctx, html.unescape(ref)), matrix,
                 '<section style="break-before: page">', decide, sign, render_next(spec), "</section>"]
    return document(spec["title"], spec.get("intro", ""), "".join(parts), wide=True)


# ---------------------------------------------------------------------------------------------
# Worked example: the BRD record of sales_performance, shown in the BRD template
# ---------------------------------------------------------------------------------------------

def brd_values(brd_dir: Path, use_case: str = "") -> dict:
    sys.path.insert(0, str(ROOT))
    from dpf.specs import parse_spec  # noqa: E402  (the framework's own OpenSpec parser)

    brd = load(brd_dir / "brd.yaml")
    spec = parse_spec((brd_dir / "spec.md").read_text(encoding="utf-8"), brd_dir / "spec.md")
    meta = spec.purpose_meta
    paras, cur = [], []
    for line in spec.purpose.splitlines():
        if line.lstrip().startswith(">"):
            continue
        if not line.strip():
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        cur.append(line.strip())
    if cur:
        paras.append(" ".join(cur))

    def cap(s):
        s = str(s or "")
        return s[:1].upper() + s[1:]

    reqs = []
    for r in spec.requirements:
        scen = [{"id": s.meta.get("id", ""), "title": s.name, "steps": s.steps} for s in r.scenarios]
        reqs.append({"id": r.meta.get("id", ""), "title": r.name, "statement": " ".join(r.body.split()), "scenarios": scen})
    prot = brd.get("protection") or {}
    ext = brd.get("external_readers") or {}
    tl = brd.get("timeliness") or {}
    owner = meta.get("owner") or brd.get("business_owner")
    steward = meta.get("steward") or brd.get("data_steward")
    return {
        "doc_id": brd["brd_id"], "product": spec.title.split("\u2014")[0].strip(), "owner": owner, "steward": steward,
        "domain": cap(brd.get("domain")), "use_case": use_case, "version": brd["version"], "date": "",
        "status": {"in_review": "In review"}.get(brd["status"], cap(brd["status"])),
        "changelog": [[c["version"], " ".join(str(c["change"]).split()), c.get("raised_by", ""), c.get("accepted_by", "")]
                      for c in brd.get("changelog", [])],
        "purpose": "\n\n".join(paras),
        "questions": [[q["id"], q["text"], q["decision_supported"], joined(q["consumers"])] for q in brd["business_questions"]],
        "outputs": [[o["id"], o["type"], joined(o.get("figures")), joined(o.get("slices")), joined(o.get("attributes")),
                     joined([x for x in (o.get("recipient"), o.get("frequency")) if x]), joined(o.get("satisfies"))]
                    for o in brd["required_outputs"]],
        "drill_to": cap(brd["level_of_detail"]["drill_to"]), "distinct_by": cap(brd["level_of_detail"]["distinct_by"]),
        "history": [[h["id"], cap(h["attribute"]), h["answer"]] for h in brd.get("history_behaviour", [])],
        "freshness_need": cap(tl.get("freshness_need")), "justification": cap(tl.get("justification")),
        "expected_users": cap(tl.get("expected_users")), "peak_volume": cap(tl.get("peak_volume")),
        "exceptions": "\n".join(brd.get("exceptions", [])),
        "unusable_row": cap(brd["fitness"]["unusable_row"]), "on_bad_data": brd["fitness"]["on_bad_data"],
        "sources": [[x["system"], x["holds"], cap(x.get("authority"))] for x in brd["sources_believed"]],
        "sensitivity": brd.get("sensitivity"), "residency": brd.get("residency"),
        "restricted": cap(joined(prot.get("restricted_attributes"))), "visible": cap(joined(prot.get("visible_to_analysts"))),
        "who_may_access": joined(prot.get("who_may_access")),
        "external": ("%s: %s" % (cap(ext.get("who")), ext.get("access"))) if ext.get("required") else "None",
        "agreement": [[a["id"], cap(a["team"]), cap(a["must_agree_on"])] for a in brd.get("agreement_with_other_teams", [])],
        "totalling": cap(joined((brd.get("totalling") or {}).get("can_be_summed_across"))),
        "requirements": reqs,
        "non_goals": "\n".join(brd.get("non_goals", [])),
        "open_questions": [[q["id"], q["question"], q.get("owner", ""), q.get("due", ""), q.get("assumption", ""),
                            q.get("blast_radius", "")] for q in brd.get("open_questions", [])],
        "signoff": {"Business owner": {"name": owner}, "Data steward": {"name": steward}},
    }


# ---------------------------------------------------------------------------------------------
# PDF output
# ---------------------------------------------------------------------------------------------

CENTRED_FIELDS = re.compile(r"^(weight|score|weighted|value_total|value_score|ease_total|ease_score|total|quadrant|value|ease)\.")


def fix_form_fields(pdf: bytes) -> bytes:
    """Make WeasyPrint's form fields draw correctly in more viewers.

    WeasyPrint writes an alpha operator into each text field's default appearance and gives
    check boxes and radio buttons none, so some viewers draw no tick. Give buttons the
    standard ZapfDingbats appearance, remove the operator from text fields and centre the
    number fields of the scorecard and the decision record.
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, NumberObject, TextStringObject

    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    acro = w._root_object.get("/AcroForm")
    if acro is None:
        return pdf
    acro = acro.get_object()
    fonts = acro["/DR"].get_object()["/Font"].get_object()
    fonts[NameObject("/ZaDb")] = w._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/ZapfDingbats")}))
    for page in w.pages:
        for ref in page.get("/Annots", []) or []:
            a = ref.get_object()
            parent = a.get("/Parent")
            parent = parent.get_object() if parent is not None else None
            ft = a.get("/FT") or (parent.get("/FT") if parent is not None else None)
            if ft == "/Btn":
                flags = int(a.get("/Ff") or (parent.get("/Ff") if parent is not None else 0) or 0)
                radio = bool(flags & (1 << 15))
                a[NameObject("/DA")] = TextStringObject("/ZaDb 0 Tf 0 g")
                mk = a.get("/MK")
                mk = mk.get_object() if mk is not None else DictionaryObject()
                mk[NameObject("/CA")] = TextStringObject("l" if radio else "4")
                a[NameObject("/MK")] = mk
            elif "/DA" in a:
                a[NameObject("/DA")] = TextStringObject(re.sub(r"/a[\d.]+ gs", "", str(a["/DA"])).strip())
                if CENTRED_FIELDS.match(str(a.get("/T", ""))):
                    a[NameObject("/Q")] = NumberObject(1)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def write_pdf(page_html: str, out: Path, forms: bool) -> int:
    import weasyprint

    doc = weasyprint.HTML(string=page_html, base_url=str(SRC)).render(
        stylesheets=[weasyprint.CSS(filename=str(SRC / "style.css"))], pdf_forms=forms)
    pdf = doc.write_pdf(pdf_forms=forms, pdf_identifier=out.name.encode())
    if forms:
        pdf = fix_form_fields(pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    print("  wrote %-58s %2d page(s)%s" % (out.relative_to(ROOT), len(doc.pages), "  [fillable]" if forms else ""))
    return len(doc.pages)


def render_templates(scoring: dict) -> None:
    version = str(scoring["version"])
    print("templates (fillable):")
    for name in ("use-case", "brd", "prd"):
        spec = load(SRC / ("%s.form.yaml" % name))
        write_pdf(build_form(spec, version, Ctx()), OUT / ("%s.pdf" % spec["file"]), forms=True)
    sc = load(SRC / "scorecard.form.yaml")
    write_pdf(build_scorecard(sc, scoring, version), OUT / ("%s.pdf" % sc["file"]), forms=True)
    pr = load(SRC / "prioritisation.form.yaml")
    write_pdf(build_prioritisation(pr, scoring, version), OUT / ("%s.pdf" % pr["file"]), forms=True)


def render_examples(scoring: dict) -> None:
    version = str(scoring["version"])
    sc = load(SRC / "scorecard.form.yaml")
    pr = load(SRC / "prioritisation.form.yaml")
    print("worked examples (filled):")
    for folder in (PORTFOLIO_EXAMPLE, SALES_EXAMPLE):
        if not (folder / "portfolio.yaml").exists():
            print("  skipped %s (not in this workspace)" % folder.relative_to(ROOT))
            continue
        portfolio = load(folder / "portfolio.yaml")
        write_pdf(build_scorecard(sc, scoring, version, portfolio), folder / "scorecard.pdf", forms=False)
        write_pdf(build_prioritisation(pr, scoring, version, portfolio), folder / "prioritisation.pdf", forms=False)
    uc_file = SALES_EXAMPLE / "use-case.yaml"
    if uc_file.exists():
        uc = load(uc_file)
        spec = load(SRC / "use-case.form.yaml")
        ctx = Ctx(uc["values"], uc.get("illustrative"))
        write_pdf(build_form(spec, version, ctx, "%s &#183; worked example" % uc["values"]["uc_id"], uc.get("note", "")),
                  SALES_EXAMPLE / "use-case.pdf", forms=False)
        if (SALES_BRD / "brd.yaml").exists():
            values = brd_values(SALES_BRD, uc["values"]["uc_id"])
            spec = load(SRC / "brd.form.yaml")
            note = ("%s %s@%s, read from the BRD record in the repository. Only the use-case link is added for the "
                    "example." % ("This is", values["doc_id"], values["version"]))
            ctx = Ctx(values, ["use_case"])
            write_pdf(build_form(spec, version, ctx, "%s &#183; worked example" % values["doc_id"], note),
                      SALES_EXAMPLE / "brd.pdf", forms=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--templates", action="store_true", help="render the blank templates only")
    args = ap.parse_args(argv)
    scoring = load(SCORING)
    render_templates(scoring)
    if not args.templates:
        render_examples(scoring)
    return 0


if __name__ == "__main__":
    sys.exit(main())
