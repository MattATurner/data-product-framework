#!/usr/bin/env python3
"""Render any DPF TDD v2 Markdown specification (`specs/tdd/spec.md`) into a rich PDF.

Usage:
  .venv/bin/python framework/templates/src/render_tdd_pdf.py examples/sales_performance/specs/tdd/spec.md
  .venv/bin/python framework/templates/src/render_tdd_pdf.py examples/sales_performance/specs/tdd/spec.md \
      --output examples/sales_performance/specs/tdd/tdd.pdf

Features:
  - Executive Cover Page with DPF 5-stage ribbon, Document Control card, and auto-numbered TOC
  - Automatic A4 Landscape spreads for architectural diagrams, FHD, data flow, ER model, and mockups
  - Automatic 2x Retina PNG selection whenever `<diagram>.png` sits beside `<diagram>.svg`
  - Structured Decision Cards for Appendix A normative requirements (`D-n`, `Satisfies`, `SHALL`, `GIVEN/WHEN/THEN`)
  - Zero external Markdown dependencies (pure Python stdlib + WeasyPrint)
"""

from __future__ import annotations

import argparse
import html
import re
import struct
from pathlib import Path
from typing import Any


CSS_PATH = Path(__file__).resolve().parent / "tdd-pdf.css"

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
META_PAIR_RE = re.compile(r"\*\*([A-Za-z][A-Za-z ]*):\*\*\s*(.*?)\s*(?=\s[·|]\s\*\*|$)")
IMG_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)\s*$")
STEP_RE = re.compile(r"^\s*-\s+\*\*(GIVEN|WHEN|THEN|AND|BECAUSE)\*\*\s+(.*)$")


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def _inline(text: str, highlight_shall: bool = False, soft_wrap_code: bool = False) -> str:
    """Convert inline Markdown (`code`, **bold**, *italic*, [links](url)) to safe HTML."""
    # Protect inline code spans first
    tokens: list[str] = []

    def _hold_code(m: re.Match) -> str:
        raw_c = _esc(m.group(1))
        if soft_wrap_code:
            raw_c = re.sub(r"([._/])", "\\1\u200b", raw_c)
        tokens.append(f"<code>{raw_c}</code>")
        return f"\x00T{len(tokens) - 1}\x00"

    s = re.sub(r"`([^`]+)`", _hold_code, text)
    s = _esc(s)

    # Links [label](href)
    def _link(m: re.Match) -> str:
        lbl, href = m.group(1), m.group(2)
        if href.startswith(("http://", "https://", "#")):
            return f'<a href="{href}">{lbl}</a>'
        if lbl.strip() == href.strip():
            return f"<code>{href}</code>"
        return f"<span>{lbl}</span> (<code>{href}</code>)"

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    if highlight_shall:
        s = re.sub(r"\b(SHALL NOT|MUST NOT|SHALL|MUST)\b", r'<span class="shall-kw">\1</span>', s)

    for idx, tok in enumerate(tokens):
        s = s.replace(f"\x00T{idx}\x00", tok)
    return s


def _png_aspect_ratio(path: Path) -> float | None:
    try:
        with path.open("rb") as fh:
            sig = fh.read(24)
            if len(sig) == 24 and sig[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", sig[16:24])
                return w / h if h else None
    except OSError:
        return None
    return None


def _svg_aspect_ratio(path: Path) -> float | None:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        m = re.search(r'viewBox="[-0-9.]+\s+[-0-9.]+\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)"', head)
        if m:
            w, h = float(m.group(1)), float(m.group(2))
            return w / h if h else None
    except OSError:
        return None
    return None


def _resolve_figure(rel_path: str, base_dir: Path) -> tuple[Path, float]:
    raw = (base_dir / rel_path).resolve()
    # Prefer crisp Chrome-rasterized 2x Retina PNG beside an SVG for exact WeasyPrint fidelity
    if raw.suffix.lower() == ".svg":
        png_sibling = raw.with_suffix(".png")
        if png_sibling.is_file():
            ar = _png_aspect_ratio(png_sibling) or 1.8
            return png_sibling, ar
        ar = _svg_aspect_ratio(raw) or 1.8
        return raw, ar
    ar = _png_aspect_ratio(raw) or 1.8
    return raw, ar


# ---------------------------------------------------------------------------
# Lightweight Block Markdown Parser
# ---------------------------------------------------------------------------
def _parse_blocks(lines: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped == "---":
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            blocks.append({"type": "code", "lang": lang, "text": "\n".join(code_lines)})
            continue

        # Sub-headings
        if stripped.startswith("### "):
            blocks.append({"type": "h3", "text": stripped[4:].strip()})
            i += 1
            continue
        if stripped.startswith("#### "):
            blocks.append({"type": "h4", "text": stripped[5:].strip()})
            i += 1
            continue

        # Standalone image line
        m_img = IMG_LINE_RE.match(stripped)
        if m_img:
            blocks.append({"type": "image", "alt": m_img.group(1).strip(), "src": m_img.group(2).strip()})
            i += 1
            continue

        # Markdown table
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            headers = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue

        # Blockquote
        if stripped.startswith("> "):
            q_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                q_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append({"type": "quote", "text": " ".join(q_lines)})
            continue

        # Unordered list
        if re.match(r"^-\s+", stripped):
            items: list[str] = []
            while i < n:
                st = lines[i].strip()
                if re.match(r"^-\s+", st):
                    items.append(re.sub(r"^-\s+", "", st))
                    i += 1
                elif st and items and lines[i].startswith("  ") and not st.startswith(("#", "|", "![", "```")):
                    items[-1] += " " + st
                    i += 1
                elif not st and i + 1 < n and re.match(r"^-\s+", lines[i + 1].strip()):
                    i += 1
                else:
                    break
            blocks.append({"type": "ul", "items": items})
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n:
                st = lines[i].strip()
                if re.match(r"^\d+\.\s+", st):
                    items.append(re.sub(r"^\d+\.\s+", "", st))
                    i += 1
                elif st and items and lines[i].startswith("  ") and not st.startswith(("#", "|", "![", "```")):
                    items[-1] += " " + st
                    i += 1
                elif not st and i + 1 < n and re.match(r"^\d+\.\s+", lines[i + 1].strip()):
                    i += 1
                else:
                    break
            blocks.append({"type": "ol", "items": items})
            continue

        # Paragraph (join wrapped lines until blank line or next block opener)
        p_lines = [stripped]
        i += 1
        while i < n:
            st = lines[i].strip()
            if (
                not st
                or st == "---"
                or st.startswith(("#", "|", "> ", "```", "- "))
                or re.match(r"^\d+\.\s+", st)
                or IMG_LINE_RE.match(st)
            ):
                break
            p_lines.append(st)
            i += 1
        blocks.append({"type": "p", "text": " ".join(p_lines)})

    return blocks


def _render_block(blk: dict[str, Any], base_dir: Path, fig_counter: list[int], plate_class: str = "") -> str:
    btype = blk["type"]
    if btype == "h3":
        return f'<h3 class="sub-title">{_inline(blk["text"])}</h3>'
    if btype == "h4":
        return f'<h4 style="font-size:8.8pt;margin:2mm 0 1mm;color:#334155">{_inline(blk["text"])}</h4>'
    if btype == "p":
        txt = blk["text"]
        if txt.lower().startswith(("interactive ", "source assets:", "vector source:")):
            return f'<p class="interactive-note">{_inline(txt)}</p>'
        return f"<p>{_inline(txt)}</p>"
    if btype == "quote":
        return f"<blockquote>{_inline(blk['text'])}</blockquote>"
    if btype == "code":
        return f"<pre><code>{_esc(blk['text'])}</code></pre>"
    if btype == "ul":
        lis = "".join(f"<li>{_inline(it)}</li>" for it in blk["items"])
        return f'<ul class="body-list">{lis}</ul>'
    if btype == "ol":
        lis = "".join(f"<li>{_inline(it)}</li>" for it in blk["items"])
        return f'<ol class="body-list">{lis}</ol>'
    if btype == "table":
        # Smart proportional column widths ensuring short columns never wrap normal words mid-word
        ncols = len(blk["headers"])
        weights: list[float] = []
        for ci in range(ncols):
            h_txt = blk["headers"][ci]
            cells = [r[ci] for r in blk["rows"] if ci < len(r)]
            h_words = [len(w) for w in re.split(r"[\s/_.-]+", h_txt) if w]
            c_words = [len(w) for cell in cells for w in re.split(r"[\s`]+", cell) if w and "_" not in w and "." not in w]
            min_word_floor = max([*h_words, *(w for w in c_words if w <= 14), 8]) * 2.45
            c_lens = [len(re.sub(r"`", "", cell)) for cell in cells]
            avg = (sum(c_lens) / len(c_lens)) if c_lens else len(h_txt)
            mx = max(c_lens) if c_lens else len(h_txt)
            weights.append(max(min_word_floor, min(58.0, 0.55 * avg + 0.45 * min(mx, 64.0))))
        total_w = sum(weights) or 1.0
        col_tags = "".join(f'<col style="width:{w / total_w * 100:.1f}%">' for w in weights)
        ths = "".join(f"<th>{_inline(h)}</th>" for h in blk["headers"])
        trs = []
        for row in blk["rows"]:
            tds = "".join(f"<td>{_inline(c, soft_wrap_code=True)}</td>" for c in row)
            trs.append(f"<tr>{tds}</tr>")
        return (
            f'<table class="data-table"><colgroup>{col_tags}</colgroup>'
            f'<thead><tr>{ths}</tr></thead><tbody>{"".join(trs)}</tbody></table>'
        )
    if btype == "image":
        fig_counter[0] += 1
        num = fig_counter[0]
        fig_path, ar = _resolve_figure(blk["src"], base_dir)
        cls = "diagram-frame"
        if plate_class:
            cls += f" {plate_class}"
        elif ar < 1.55:
            cls += " tall-plate"
        uri = fig_path.as_uri()
        alt = blk["alt"] or f"Diagram {num}"
        return (
            f'<figure class="{cls}">'
            f'<img src="{_esc(uri)}" alt="{_esc(alt)}"/>'
            f'<figcaption><span class="fig-num">Figure {num}</span><span>{_esc(alt)}</span></figcaption>'
            f"</figure>"
        )
    return ""


# ---------------------------------------------------------------------------
# Appendix A — Structured Normative Decision Cards Renderer
# ---------------------------------------------------------------------------
def _render_requirements_section(lines: list[str]) -> str:
    cards: list[str] = []
    cur_req: dict[str, Any] | None = None
    cur_scen: dict[str, Any] | None = None

    def flush() -> None:
        if not cur_req:
            return
        meta = cur_req["meta"]
        did = meta.get("decision") or meta.get("id") or "REQ"
        chips: list[str] = []
        if meta.get("satisfies"):
            chips.append(f'<span class="dec-chip">Satisfies: {_esc(meta["satisfies"])}</span>')
        if meta.get("layer") and meta.get("methodology"):
            chips.append(f'<span class="dec-chip">{_esc(meta["layer"])}: {_esc(meta["methodology"])}</span>')
        if meta.get("model"):
            chips.append(f'<span class="dec-chip">Model: {_esc(meta["model"])}</span>')
        if meta.get("grain"):
            chips.append(f'<span class="dec-chip grain">Grain: {_esc(meta["grain"])}</span>')
        if meta.get("adr"):
            chips.append(f'<span class="dec-chip adr">{_esc(meta["adr"])}</span>')

        body_html = f'<p>{_inline(" ".join(cur_req["body"]).strip(), highlight_shall=True)}</p>'
        scen_html = ""
        for sc in cur_req["scenarios"]:
            rows = []
            for kw, text in sc["steps"]:
                kcls = "kw-pill"
                if kw == "THEN":
                    kcls += " then"
                elif kw == "WHEN":
                    kcls += " when"
                rows.append(
                    f'<tr><td class="kw-col"><span class="{kcls}">{kw}</span></td>'
                    f'<td>{_inline(text, highlight_shall=True)}</td></tr>'
                )
            scen_html += (
                f'<div class="scenario-box">'
                f'<div class="scenario-title">Scenario: {_esc(sc["name"])}</div>'
                f'<table class="scenario-steps">{"".join(rows)}</table>'
                f"</div>"
            )

        cards.append(
            f'<div class="decision-card">'
            f'<div class="decision-head">'
            f'<div class="decision-title-wrap"><span class="dec-id">{_esc(did)}</span>'
            f'<span class="dec-title">{_esc(cur_req["name"])}</span></div>'
            f'<div class="dec-chips">{"".join(chips)}</div>'
            f"</div>"
            f'<div class="decision-body">{body_html}{scen_html}</div>'
            f"</div>"
        )

    for raw in lines:
        st = raw.strip()
        if not st or st == "---":
            continue
        if st.startswith("### Requirement:"):
            flush()
            cur_req = {"name": st.split(":", 1)[1].strip(), "meta": {}, "body": [], "scenarios": []}
            cur_scen = None
            continue
        if st.startswith("#### Scenario:") and cur_req is not None:
            cur_scen = {"name": st.split(":", 1)[1].strip(), "steps": []}
            cur_req["scenarios"].append(cur_scen)
            continue
        if cur_req is None:
            continue
        if cur_scen is None and st.startswith("**") and META_PAIR_RE.search(st):
            parsed = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in META_PAIR_RE.findall(st)}
            if parsed and any(k in parsed for k in ("decision", "satisfies", "id", "model")):
                cur_req["meta"].update(parsed)
                continue
        if cur_scen is not None:
            ms = STEP_RE.match(raw)
            if ms:
                cur_scen["steps"].append((ms.group(1), ms.group(2).strip()))
            elif cur_scen["steps"]:
                kw, prev = cur_scen["steps"][-1]
                cur_scen["steps"][-1] = (kw, prev + " " + st)
        else:
            cur_req["body"].append(st)
    flush()
    return "\n".join(cards)


# ---------------------------------------------------------------------------
# Full Document HTML Builder
# ---------------------------------------------------------------------------
def build_tdd_html(spec_path: Path, page_map: dict[str, int] | None = None) -> str:
    raw_md = HTML_COMMENT_RE.sub("", spec_path.read_text(encoding="utf-8"))
    base_dir = spec_path.parent
    page_map = page_map or {}

    title = spec_path.parent.parent.parent.name.replace("_", " ").title()
    sections: list[tuple[str, list[str]]] = []
    cur_sec: str | None = None
    cur_lines: list[str] = []

    for line in raw_md.splitlines():
        if line.startswith("# ") and cur_sec is None:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if cur_sec is not None:
                sections.append((cur_sec, cur_lines))
            cur_sec = line[3:].strip()
            cur_lines = []
            continue
        if cur_sec is not None:
            cur_lines.append(line)
    if cur_sec is not None:
        sections.append((cur_sec, cur_lines))

    # Extract Purpose metadata, prose, and Document Control table
    purpose_meta: dict[str, str] = {}
    purpose_blocks: list[dict[str, Any]] = []
    body_sections: list[tuple[str, list[str]]] = []

    for heading, slines in sections:
        if heading.lower() == "purpose":
            cleaned: list[str] = []
            for l in slines:
                if l.strip().startswith("**") and META_PAIR_RE.search(l):
                    parsed = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in META_PAIR_RE.findall(l)}
                    if any(k in parsed for k in ("tdd", "satisfies", "version", "owner")):
                        purpose_meta.update(parsed)
                        continue
                cleaned.append(l)
            purpose_blocks = _parse_blocks(cleaned)
        else:
            body_sections.append((heading, slines))

    # Split title into Product Name & Subtitle ("Sales Performance — Technical Design Document")
    if "—" in title:
        main_title, sub_title = [x.strip() for x in title.split("—", 1)]
    elif " - " in title:
        main_title, sub_title = [x.strip() for x in title.split(" - ", 1)]
    else:
        main_title, sub_title = title, "Technical Design Document"

    tdd_id = purpose_meta.get("tdd", "TDD")
    satisfies = purpose_meta.get("satisfies", "")
    version = purpose_meta.get("version", "")
    owner = purpose_meta.get("owner", "")

    # Extract classification / environment from doc control table if present
    doc_control_rows: list[tuple[str, str]] = []
    purpose_prose: list[str] = []
    classification = ""
    for blk in purpose_blocks:
        if blk["type"] == "table":
            for r in blk["rows"]:
                if len(r) >= 2:
                    doc_control_rows.append((r[0], r[1]))
                    if "classification" in r[0].lower():
                        classification = r[1]
        elif blk["type"] == "p":
            purpose_prose.append(f"<p>{_inline(blk['text'])}</p>")

    footer_str = " · ".join(x for x in [classification or "Technical Design", f"Satisfies {satisfies}" if satisfies else "", f"Owner: {owner}" if owner else ""] if x)

    # Build TOC entries (exact resolved page numbers injected on pass 2)
    toc_rows: list[str] = []
    sec_ids: list[str] = []
    for idx, (heading, _) in enumerate(body_sections):
        sid = f"sec-{idx + 1}-{_slug(heading)}"
        sec_ids.append(sid)
        is_app = heading.lower().startswith("appendix") or heading.lower() == "requirements"
        cls = "toc-row is-appendix" if is_app else "toc-row"
        pg = str(page_map.get(sid, "—"))
        toc_rows.append(
            f'<a href="#{sid}" class="{cls}">'
            f'<span class="toc-name">{_esc(heading)}</span>'
            f'<span class="toc-dots"></span>'
            f'<span class="toc-pg">{pg}</span></a>'
        )

    # Cover Metadata Pills
    pills = [f'<span class="cover-pill accent">{_esc(tdd_id)}</span>']
    if version:
        pills.append(f'<span class="cover-pill">Version {_esc(version)}</span>')
    if satisfies:
        pills.append(f'<span class="cover-pill">Satisfies {_esc(satisfies)}</span>')
    if owner:
        pills.append(f'<span class="cover-pill">Owner: {_esc(owner)}</span>')

    # Cover Document Control Table HTML
    dc_html = ""
    if doc_control_rows:
        dc_trs = "".join(f"<tr><th>{_inline(k)}</th><td>{_inline(v)}</td></tr>" for k, v in doc_control_rows)
        dc_html = f'<div class="cover-grid-label">Document Control &amp; Governance</div><table class="doc-control-table"><tbody>{dc_trs}</tbody></table>'

    cover_html = f"""
    <section class="cover-page">
      <div class="hidden-strings">
        <span class="s-tdd">{_esc(tdd_id)}</span>
        <span class="s-footer">{_esc(footer_str)}</span>
      </div>
      <div class="cover-band">
        <div class="cover-kicker">Data Product Framework · Design Stage · Gate G1</div>
        <h1 class="cover-title">{_esc(main_title)}</h1>
        <div class="cover-subtitle">{_esc(sub_title)}</div>
        <div class="cover-meta-pills">{"".join(pills)}</div>
      </div>

      <div class="lifecycle-strip">
        <div class="lifecycle-step done"><b>1. Use Case</b>Approved</div>
        <div class="lifecycle-step done"><b>2. Scorecard</b>Prioritised</div>
        <div class="lifecycle-step done"><b>3. BRD (G0)</b>Signed Off</div>
        <div class="lifecycle-step active"><b>4. TDD (G1)</b>This Document</div>
        <div class="lifecycle-step"><b>5. Build &amp; Accept</b>G2 · G3 · G4</div>
      </div>

      <div class="purpose-box">{"".join(purpose_prose)}</div>
      {dc_html}

      <div class="toc-card">
        <div class="toc-title">Contents</div>
        <div class="toc-grid">{"".join(toc_rows)}</div>
      </div>
    </section>
    """

    # Render all body sections
    fig_counter = [0]
    rendered_sections: list[str] = []
    prev_was_landscape = False

    for idx, (heading, slines) in enumerate(body_sections):
        sid = sec_ids[idx]
        is_appendix = heading.lower().startswith("appendix")
        is_reqs = heading == "Requirements" or heading.endswith("Requirements")

        m_num = re.match(r"^(\d+)\.\s+(.*)$", heading)
        m_app = re.match(r"^Appendix\s+([A-Z])\s*[—:-]\s*(.*)$", heading)
        if m_num:
            badge_txt = f"{int(m_num.group(1)):02d}"
            clean_h = m_num.group(2)
            run_lbl = f"{badge_txt} · {clean_h}"
        elif m_app:
            badge_txt = f"APP {m_app.group(1)}"
            clean_h = m_app.group(2)
            run_lbl = f"Appendix {m_app.group(1)} · {clean_h}"
        else:
            badge_txt = "REQ" if is_reqs else "SEC"
            clean_h = heading
            run_lbl = heading

        h_cls = "sec-title appendix-title" if is_appendix else "sec-title"
        header_html = (
            f'<h2 id="{sid}" class="{h_cls}" data-section="{_esc(run_lbl)}">'
            f'<span class="sec-badge">{_esc(badge_txt)}</span><span>{_esc(clean_h)}</span></h2>'
        )

        if is_reqs:
            inner = _render_requirements_section(slines)
            rendered_sections.append(f'<section class="tdd-section page-break-before">{header_html}{inner}</section>')
            prev_was_landscape = False
            continue

        blocks = _parse_blocks(slines)
        img_blocks = [b for b in blocks if b["type"] == "image"]

        if img_blocks:
            _, primary_ar = _resolve_figure(img_blocks[0]["src"], base_dir)
            if primary_ar < 1.55:
                # Dense tall diagram (e.g. Entity-Relationship Model): full-height Landscape Plate,
                # followed cleanly by the Entity Summary tables & prose on a fresh Portrait page!
                plate_parts = []
                follow_parts = []
                seen_img = False
                for b in blocks:
                    if not seen_img:
                        plate_parts.append(_render_block(b, base_dir, fig_counter, plate_class="tall-plate"))
                        if b["type"] == "image":
                            seen_img = True
                    elif b["type"] == "p" and b["text"].lower().startswith("interactive "):
                        plate_parts.append(_render_block(b, base_dir, fig_counter))
                    else:
                        follow_parts.append(_render_block(b, base_dir, fig_counter))

                rendered_sections.append(
                    f'<section class="tdd-section landscape-section">{header_html}{"".join(plate_parts)}</section>'
                )
                if follow_parts:
                    rendered_sections.append(
                        f'<section class="tdd-section page-break-before">{"".join(follow_parts)}</section>'
                    )
                    prev_was_landscape = False
                else:
                    prev_was_landscape = True
            else:
                img_idx = next(i for i, b in enumerate(blocks) if b["type"] == "image")
                pre_blocks = blocks[:img_idx]
                img_blk = blocks[img_idx]
                post_blocks = blocks[img_idx + 1:]

                note_blocks = []
                while post_blocks and post_blocks[0]["type"] == "p" and post_blocks[0]["text"].lower().startswith("interactive "):
                    note_blocks.append(post_blocks.pop(0))

                pre_html = "".join(_render_block(b, base_dir, fig_counter) for b in pre_blocks)
                has_pre_table = bool(pre_blocks and any(b["type"] == "table" for b in pre_blocks))
                has_post_table = any(b["type"] == "table" for b in post_blocks)
                h3_indices = [i for i, b in enumerate(post_blocks) if b["type"] == "h3"]

                # Choose image plate height so the diagram + walkthrough/table sit TOGETHER on ONE single landscape spread!
                if has_pre_table:
                    pclass = "dashboard-plate"
                elif has_post_table or len(h3_indices) >= 2:
                    pclass = "compact-plate"
                else:
                    pclass = "medium-plate"

                img_html = _render_block(img_blk, base_dir, fig_counter, plate_class=pclass)
                note_html = "".join(_render_block(b, base_dir, fig_counter) for b in note_blocks)

                if len(h3_indices) in (2, 3) and h3_indices[0] == 0 and not has_post_table:
                    cards_html = []
                    cols = len(h3_indices)
                    for k, start_i in enumerate(h3_indices):
                        end_i = h3_indices[k + 1] if k + 1 < cols else len(post_blocks)
                        chunk = "".join(_render_block(b, base_dir, fig_counter) for b in post_blocks[start_i:end_i])
                        cards_html.append(f'<div class="landscape-prose-card">{chunk}</div>')
                    post_html = f'<div class="landscape-prose-grid" style="grid-template-columns:repeat({cols},1fr)">{"".join(cards_html)}</div>'
                else:
                    raw_post = "".join(_render_block(b, base_dir, fig_counter) for b in post_blocks)
                    ul_blks = [b for b in post_blocks if b["type"] == "ul"]
                    if ul_blks and not has_post_table:
                        n_items = sum(len(u["items"]) for u in ul_blks)
                        wrap_cls = "landscape-walkthrough cols-2" if n_items <= 2 else "landscape-walkthrough"
                    else:
                        wrap_cls = ""
                    post_html = f'<div class="{wrap_cls}">{raw_post}</div>' if raw_post else ""

                if has_pre_table:
                    rendered_sections.append(
                        f'<section class="tdd-section page-break-before">{header_html}{pre_html}</section>'
                    )
                    rendered_sections.append(
                        f'<section class="tdd-section landscape-section">'
                        f'<h3 class="sub-title" style="margin-top:0">{_esc(img_blk["alt"])}</h3>'
                        f'{img_html}{note_html}{post_html}</section>'
                    )
                else:
                    rendered_sections.append(
                        f'<section class="tdd-section landscape-section">'
                        f'{header_html}{pre_html}{img_html}{note_html}{post_html}</section>'
                    )
                prev_was_landscape = True
        else:
            inner = "".join(_render_block(b, base_dir, fig_counter) for b in blocks)
            brk = " page-break-before" if (is_appendix or prev_was_landscape) else ""
            rendered_sections.append(f'<section class="tdd-section{brk}">{header_html}{inner}</section>')
            prev_was_landscape = False

    css_text = CSS_PATH.read_text(encoding="utf-8")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
{css_text}
</style>
</head>
<body>
{cover_html}
{"".join(rendered_sections)}
</body>
</html>
"""


def render_pdf(spec_path: Path, output_pdf: Path, save_html: Path | None = None) -> Path:
    import weasyprint

    spec_path = spec_path.resolve()
    base_url = spec_path.parent.as_uri() + "/"

    # Pass 1: layout document to extract exact 1-based page numbers for every section anchor
    draft_html = build_tdd_html(spec_path)
    draft_doc = weasyprint.HTML(string=draft_html, base_url=base_url).render()
    page_map: dict[str, int] = {}
    for pno, page in enumerate(draft_doc.pages, start=1):
        for anchor in page.anchors:
            page_map.setdefault(anchor, pno)

    # Pass 2: render final PDF with exact TOC page numbers
    final_html = build_tdd_html(spec_path, page_map=page_map)
    if save_html:
        save_html.parent.mkdir(parents=True, exist_ok=True)
        save_html.write_text(final_html, encoding="utf-8")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    final_doc = weasyprint.HTML(string=final_html, base_url=base_url).render()
    final_doc.write_pdf(str(output_pdf))
    return output_pdf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a DPF Markdown TDD into a rich executive PDF.")
    ap.add_argument("spec", type=Path, help="Path to specs/tdd/spec.md")
    ap.add_argument("--output", "-o", type=Path, help="Output PDF path (default: <spec_dir>/tdd.pdf)")
    ap.add_argument("--save-html", type=Path, help="Optional path to save intermediate HTML for inspection")
    args = ap.parse_args(argv)

    out_pdf = args.output or (args.spec.parent / "tdd.pdf")
    render_pdf(args.spec, out_pdf, save_html=args.save_html)
    print(f"Rendered PDF: {out_pdf.resolve()} ({out_pdf.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
