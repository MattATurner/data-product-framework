#!/usr/bin/env python3
"""
Build a single-file, offline HTML method diagram for the Data Product Framework.

Reads  : data-product-framework-plan.md
Writes : data-product-framework-method.html

Every node in the diagram links to the relevant section(s) of the plan, whose
content is embedded in the page so it works from disk with no network access.
"""

import html
import json
import re
import sys
from pathlib import Path

SRC = Path("data-product-framework-plan.md")
OUT = Path("data-product-framework-method.html")


# --------------------------------------------------------------------------
# 1. Parse the plan into addressable sections keyed by number ("4", "4.3")
# --------------------------------------------------------------------------

def parse_sections(md: str) -> dict:
    lines = md.split("\n")
    heads = []  # (index, level, number, title)
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{2,3}) (\d+(?:\.\d+[a-z]?)?)\.? (.+)$", ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2), m.group(3).strip()))

    sections = {}
    for n, (idx, level, num, title) in enumerate(heads):
        end = len(lines)
        for later_idx, later_level, _, _ in heads[n + 1:]:
            # a ## section swallows its ### children; a ### stops at the next heading
            if level == 2 and later_level <= 2:
                end = later_idx
                break
            if level == 3 and later_level <= 3:
                end = later_idx
                break
        body = "\n".join(lines[idx + 1:end]).strip("\n")
        sections[num] = {"num": num, "title": title, "level": level, "body": body}
    return sections


# --------------------------------------------------------------------------
# 2. Minimal, dependency-free Markdown -> HTML
# --------------------------------------------------------------------------

def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", t)
    t = t.replace("--&gt;", "&rarr;").replace("-&gt;", "&rarr;")
    return t


def split_row(row: str):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def md_to_html(md: str) -> str:
    out, i = [], 0
    lines = md.split("\n")
    n = len(lines)

    while i < n:
        ln = lines[i]

        # fenced code
        if ln.startswith("```"):
            lang = ln[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            label = f'<span class="codelang">{html.escape(lang)}</span>' if lang else ""
            out.append(f'<div class="codeblock">{label}<pre><code>'
                       + html.escape("\n".join(buf)) + "</code></pre></div>")
            continue

        # table
        if ln.strip().startswith("|") and i + 1 < n and re.match(
                r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            header = split_row(ln)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in header)
            body = ""
            for r in rows:
                r += [""] * (len(header) - len(r))
                body += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r[:len(header)]) + "</tr>"
            out.append(f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead>'
                       f"<tbody>{body}</tbody></table></div>")
            continue

        # heading
        m = re.match(r"^(#{3,4}) (.+)$", ln)
        if m:
            lvl = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        # blockquote
        if ln.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            inner = md_to_html("\n".join(buf))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # lists
        if re.match(r"^\s*[-*] ", ln) or re.match(r"^\s*\d+\. ", ln):
            ordered = bool(re.match(r"^\s*\d+\. ", ln))
            tag = "ol" if ordered else "ul"
            items = []
            while i < n and (re.match(r"^\s*[-*] ", lines[i]) or re.match(r"^\s*\d+\. ", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*]|\d+\.) ", "", lines[i]))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        # rule
        if ln.strip() == "---":
            out.append("<hr>")
            i += 1
            continue

        # paragraph
        if ln.strip() == "":
            i += 1
            continue
        buf = []
        while i < n and lines[i].strip() != "" and not lines[i].startswith(("#", ">", "```", "|")) \
                and not re.match(r"^\s*[-*] ", lines[i]) and not re.match(r"^\s*\d+\. ", lines[i]) \
                and lines[i].strip() != "---":
            buf.append(lines[i])
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")

    return "".join(out)


# --------------------------------------------------------------------------
# 3. The method model — nodes and the plan sections each one links to
# --------------------------------------------------------------------------

LANES = [
    ("specify", "1 · Specify", "Business owns this column"),
    ("design", "2 · Design", "Engineering owns this column"),
    ("build", "3 · Build", "Agent, reviewed by engineering"),
    ("publish", "4 · Publish & govern", "Joint, business accepts"),
]

NODES = [
    # ---------------- Specify
    dict(id="brd", lane="specify", step="1", title="BRD spec",
         who="business", who_label="Business SME / analyst",
         path="specs/products/<product>/brd/spec.md",
         desc="What the business needs, in business language. No grain, no SCD, no BigQuery.",
         refs=[("Who writes it", "4.1"), ("Completeness rubric", "4.2"),
               ("Eliciting the model", "4.3"), ("Source-anchored BRDs", "4.4"),
               ("Example — brd.yaml", "4.5"), ("Open questions", "4.6"),
               ("Worked example", "12.1")]),
    dict(id="g0", lane="specify", step="G0", title="Gate G0 — BRD ready", kind="gate",
         who="auto", who_label="Business owner approves",
         desc="Every question the design depends on has a business answer. Emits gaps.md.",
         refs=[("Gate definitions", "3.3"), ("The rubric", "4.2")]),

    # ---------------- Design
    dict(id="tdd", lane="design", step="2", title="TDD spec",
         who="engineering", who_label="Data engineer, agent-assisted",
         path="specs/products/<product>/tdd/spec.md",
         desc="How it will be satisfied. Methodology, grain, SCD, keys, services. Declares satisfies: BRD@version.",
         refs=[("Two separate specs", "5.0"), ("Derivation table", "5.1"),
               ("Feasibility vs real sources", "5.2"), ("Worked example", "12.2")]),
    dict(id="semantics", lane="design", step="3", title="semantics.md",
         who="joint", who_label="Derived by engineering, signed by business",
         path="specs/products/<product>/semantics.md",
         desc="What the business will actually receive, in their language. The one document both parties read.",
         refs=[("Semantic playback", "5.3"), ("Worked example", "12.2b")]),
    dict(id="g1", lane="design", step="G1", title="Gate G1 — TDD ready", kind="gate",
         who="auto", who_label="Eng lead + formal business go",
         desc="Traceability both ways, no orphans, contracts type-check, semantics.md signed.",
         refs=[("Gate definitions", "3.3"), ("Traceability", "5.4")]),

    # ---------------- Build
    dict(id="compose", lane="build", step="4", title="Compose the skill DAG",
         who="agent", who_label="dpf compose",
         desc="Resolve the manifest into a chain of skills and type-check every contract handoff.",
         refs=[("Contract registry", "11"), ("Skill catalogue", "10"),
               ("Methodology pack skills", "10.5")]),
    dict(id="artefacts", lane="build", step="5", title="Generate artefacts",
         who="agent", who_label="Agent, reviewed by engineer",
         path="generated/<product>/",
         desc="Dataform SQLX, Terraform, Datastream config, Composer DAGs. Disposable and regenerable.",
         refs=[("Build chain", "12.3"), ("Repository layout", "13")]),
    dict(id="g23", lane="build", step="G2·G3", title="Gates G2 / G3", kind="gate",
         who="auto", who_label="Automated + code review",
         desc="Compile, dry-run, terraform validate, golden-fixture diff, reproducibility.",
         refs=[("Validation and CI", "14"), ("Gate definitions", "3.3")]),

    # ---------------- Publish
    dict(id="publish", lane="publish", step="6", title="Publish the data product",
         who="engineering", who_label="publish-data-product",
         desc="Access model, versioned product datasets, BigQuery sharing, deprecation policy.",
         refs=[("Publish & govern skills", "10.4"), ("Contracts", "11")]),
    dict(id="catalog", lane="publish", step="7", title="Register in Knowledge Catalog",
         who="engineering", who_label="register-knowledge-catalog",
         desc="Aspects, ownership, glossary, lineage, quality binding, BRD + TDD links, signed semantics.",
         refs=[("Publish & govern skills", "10.4"), ("Build chain", "12.3")]),
    dict(id="g4", lane="publish", step="G4", title="Gate G4 — Acceptance", kind="gate",
         who="auto", who_label="Business owner accepts",
         desc="Acceptance examples and semantics statements pass. Only now does status flip to published.",
         refs=[("Validation and CI", "14"), ("Acceptance", "12.4"), ("Gate definitions", "3.3")]),
]

PLANES = [
    dict(id="methodology", title="Methodology packs", who="engineering",
         desc="Optional and pluggable. direct (default) · Kimball · Data Vault 2.0 · OBT. Selected per layer in the TDD.",
         refs=[("The methodology plane", "6"), ("What a pack contributes", "6.2"),
               ("The direct path (no methodology)", "6.3"), ("The Kimball pack", "6.4"),
               ("Per-layer selection", "6.5"), ("How one is chosen", "6.6"),
               ("Pack roadmap", "6.7"), ("Pack skills", "10.5")]),
    dict(id="skills", title="Composable skills", who="agent",
         desc="Extract, load, transform, publish, govern — mapped to Google Cloud services.",
         refs=[("Skill catalogue", "10"), ("Extract", "10.1"), ("Load", "10.2"),
               ("Transform", "10.3"), ("Publish & govern", "10.4"),
               ("Methodology packs", "10.5"), ("Lifecycle & meta", "10.6")]),
    dict(id="engine", title="Engine & storage", who="engineering",
         desc="Pluggable, not mandated. Dataform (default) · dbt · Dataflow streaming · Spark. BQ native · Iceberg · GCS Parquet.",
         refs=[("Engine & storage options", "7"), ("Transform engines", "7.1"),
               ("Storage formats", "7.2"), ("What it adds", "7.3")]),
    dict(id="contracts", title="Contract registry", who="joint",
         desc="Eight typed JSON Schemas. Composition is validated before anything runs.",
         refs=[("The contract registry", "11"), ("Architecture", "8")]),
    dict(id="capabilities", title="Platform capabilities", who="engineering",
         desc="Reusable behaviour specs. Named for behaviour, never for tooling.",
         refs=[("Capability taxonomy", "9"), ("Three kinds of spec", "3.2")]),
]

FOOTER = [
    dict(id="overview", title="What we are building", refs=[("Overview", "1"),
         ("Design principles", "2"), ("The lifecycle", "3"), ("Architecture", "8")]),
    dict(id="repo", title="Repo layout & CLI", refs=[("Repository layout", "13"),
         ("Template vs example", "13.1"), ("The dpf CLI", "13.2")]),
    dict(id="delivery", title="Delivery plan", refs=[("Delivery plan", "15")]),
    dict(id="adrs", title="Decisions (ADRs)", refs=[("Decisions to lock", "16")]),
    dict(id="risks", title="Risks & next steps", refs=[("Risks", "17"),
         ("Immediate next steps", "18")]),
]

WHO_LABELS = {
    "business": "Business",
    "engineering": "Engineering",
    "joint": "Joint / signed",
    "agent": "Agent",
    "auto": "Gate",
}


# --------------------------------------------------------------------------
# 4. Page template
# --------------------------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --g-blue:#1a73e8; --g-green:#1e8e3e; --g-yellow:#f9ab00; --g-red:#d93025;
  --g-purple:#9334e6; --g-grey:#5f6368;
  --bg:#fff; --surface:#f8f9fa; --card:#fff; --border:#dadce0;
  --text:#202124; --text-2:#5f6368; --text-3:#80868b;
  --shadow:0 1px 2px rgba(60,64,67,.3),0 1px 3px 1px rgba(60,64,67,.15);
  --shadow-lg:0 4px 8px 3px rgba(60,64,67,.15),0 1px 3px rgba(60,64,67,.3);
  --radius:8px; --code-bg:#f1f3f4;
  --font:'Google Sans','Product Sans',Roboto,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
  --mono:'Roboto Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
body.dark{
  --bg:#202124; --surface:#292a2d; --card:#292a2d; --border:#3c4043;
  --text:#e8eaed; --text-2:#9aa0a6; --text-3:#80868b; --code-bg:#35363a;
  --g-blue:#8ab4f8; --g-green:#81c995; --g-yellow:#fdd663; --g-red:#f28b82;
  --g-purple:#c58af9;
  --shadow:0 1px 2px rgba(0,0,0,.6),0 1px 3px 1px rgba(0,0,0,.3);
  --shadow-lg:0 4px 8px 3px rgba(0,0,0,.4),0 1px 3px rgba(0,0,0,.6);
}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--font);
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}

/* ---------- header ---------- */
header{position:sticky;top:0;z-index:40;background:var(--bg);
  border-bottom:1px solid var(--border);padding:14px 24px;
  display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.brand{display:flex;flex-direction:column;gap:2px;margin-right:auto}
.brand h1{margin:0;font-size:18px;font-weight:500;letter-spacing:-.2px}
.brand p{margin:0;font-size:12.5px;color:var(--text-2)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--text-2)}
.legend span{display:flex;align-items:center;gap:6px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.dot.business{background:var(--g-blue)} .dot.engineering{background:var(--g-green)}
.dot.joint{background:var(--g-yellow)} .dot.agent{background:var(--g-purple)}
.dot.auto{background:var(--g-grey)}
button.tbtn{font-family:var(--font);font-size:13px;cursor:pointer;
  background:var(--surface);color:var(--text);border:1px solid var(--border);
  border-radius:100px;padding:7px 16px;transition:background .15s}
button.tbtn:hover{background:var(--border)}

/* ---------- board ---------- */
main{padding:26px 24px 60px;max-width:1560px;margin:0 auto}
.hint{font-size:13px;color:var(--text-2);margin:0 0 20px}
.hint strong{color:var(--text);font-weight:500}
.lanes{display:grid;grid-template-columns:1fr 26px 1fr 26px 1fr 26px 1fr;
  gap:0 6px;align-items:start}
.flowarrow{display:flex;align-items:center;justify-content:center;
  padding-top:88px;color:var(--text-3)}
.lane{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:12px;min-width:0}
.lane-head{padding:2px 4px 12px}
.lane-head h2{margin:0;font-size:13px;font-weight:600;letter-spacing:.4px;
  text-transform:uppercase;color:var(--text)}
.lane-head p{margin:3px 0 0;font-size:11.5px;color:var(--text-2)}

.node{width:100%;text-align:left;display:block;cursor:pointer;
  background:var(--card);border:1px solid var(--border);
  border-left:4px solid var(--accent,var(--g-grey));
  border-radius:var(--radius);padding:12px 13px;margin-bottom:10px;
  box-shadow:var(--shadow);font-family:var(--font);color:var(--text);
  transition:box-shadow .15s,transform .15s}
.node:hover{box-shadow:var(--shadow-lg);transform:translateY(-1px)}
.node:focus-visible{outline:2px solid var(--g-blue);outline-offset:2px}
.node.business{--accent:var(--g-blue)} .node.engineering{--accent:var(--g-green)}
.node.joint{--accent:var(--g-yellow)} .node.agent{--accent:var(--g-purple)}
.node.auto{--accent:var(--g-grey)}
.node.gate{background:transparent;border-style:dashed;box-shadow:none}
.node-top{display:flex;align-items:center;gap:8px;margin-bottom:5px}
.step{flex:none;font-size:11px;font-weight:600;color:#fff;background:var(--accent);
  border-radius:100px;padding:2px 9px;letter-spacing:.3px}
.node.auto .step,.node.joint .step{color:#202124}
body.dark .node .step{color:#202124}
.node-top h3{margin:0;font-size:14.5px;font-weight:500;letter-spacing:-.1px}
.node p{margin:0;font-size:12.5px;color:var(--text-2)}
.who{margin-top:7px;font-size:11px;color:var(--text-3)}
.path{margin-top:6px;font-family:var(--mono);font-size:10.5px;color:var(--text-3);
  word-break:break-all}
.reflist{margin-top:9px;display:flex;flex-wrap:wrap;gap:5px}
.refchip{font-size:10.5px;border:1px solid var(--border);border-radius:100px;
  padding:2px 8px;color:var(--text-2);background:var(--surface)}
body.dark .refchip{background:var(--bg)}

/* ---------- bands ---------- */
.band{margin-top:24px}
.band > h2{font-size:13px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;
  margin:0 0 4px}
.band > p.sub{margin:0 0 12px;font-size:12.5px;color:var(--text-2)}
.grid4{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{cursor:pointer;font-family:var(--font);font-size:13px;color:var(--text);
  background:var(--card);border:1px solid var(--border);border-radius:100px;
  padding:8px 16px;box-shadow:var(--shadow);transition:background .15s}
.chip:hover{background:var(--surface)}

/* ---------- drawer ---------- */
.scrim{position:fixed;inset:0;background:rgba(32,33,36,.45);opacity:0;
  pointer-events:none;transition:opacity .2s;z-index:50}
.scrim.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(760px,94vw);
  background:var(--bg);border-left:1px solid var(--border);z-index:60;
  transform:translateX(100%);transition:transform .24s cubic-bezier(.2,0,0,1);
  display:flex;flex-direction:column;box-shadow:var(--shadow-lg)}
.drawer.open{transform:none}
.dhead{padding:18px 22px 0;border-bottom:1px solid var(--border)}
.dhead .row{display:flex;align-items:flex-start;gap:12px}
.dhead h2{margin:0;font-size:19px;font-weight:500;flex:1}
.dhead .who{margin:4px 0 0;font-size:12px}
.close{background:none;border:none;cursor:pointer;color:var(--text-2);
  font-size:22px;line-height:1;padding:4px 8px;border-radius:50%}
.close:hover{background:var(--surface);color:var(--text)}
.tabs{display:flex;gap:2px;overflow-x:auto;margin-top:14px;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{flex:none;cursor:pointer;font-family:var(--font);font-size:12.5px;
  background:none;border:none;border-bottom:3px solid transparent;
  color:var(--text-2);padding:9px 13px;white-space:nowrap}
.tab:hover{color:var(--text)}
.tab.active{color:var(--g-blue);border-bottom-color:var(--g-blue);font-weight:500}
.dbody{padding:20px 22px 40px;overflow-y:auto;flex:1}
.secnum{font-size:11.5px;color:var(--text-3);letter-spacing:.4px;
  text-transform:uppercase;margin:0 0 2px}
.dbody h3{font-size:16px;margin:0 0 14px;font-weight:500}
.dbody h4{font-size:14.5px;margin:22px 0 8px;font-weight:500}
.dbody h5{font-size:13.5px;margin:18px 0 6px;font-weight:500;color:var(--text-2)}
.dbody p{margin:0 0 11px}
.dbody ul,.dbody ol{margin:0 0 12px;padding-left:22px}
.dbody li{margin-bottom:4px}
.dbody hr{border:none;border-top:1px solid var(--border);margin:18px 0}
.dbody code{font-family:var(--mono);font-size:12px;background:var(--code-bg);
  padding:1.5px 5px;border-radius:4px}
.codeblock{position:relative;margin:0 0 14px}
.codeblock .codelang{position:absolute;top:6px;right:10px;font-size:10px;
  color:var(--text-3);text-transform:uppercase;letter-spacing:.5px}
.dbody pre{background:var(--code-bg);border:1px solid var(--border);
  border-radius:6px;padding:13px 14px;overflow-x:auto;margin:0}
.dbody pre code{background:none;padding:0;font-size:11.5px;line-height:1.5}
.dbody blockquote{margin:0 0 14px;padding:10px 16px;border-left:3px solid var(--g-blue);
  background:var(--surface);border-radius:0 6px 6px 0}
.dbody blockquote p:last-child{margin-bottom:0}
.tablewrap{overflow-x:auto;margin:0 0 16px}
.dbody table{border-collapse:collapse;width:100%;font-size:12.5px}
.dbody th,.dbody td{border:1px solid var(--border);padding:7px 10px;
  text-align:left;vertical-align:top}
.dbody th{background:var(--surface);font-weight:500}
.dfoot{border-top:1px solid var(--border);padding:11px 22px;font-size:12px;
  color:var(--text-2);display:flex;justify-content:space-between;gap:12px;
  align-items:center;flex-wrap:wrap}
.dfoot a{color:var(--g-blue)}

@media (max-width:1180px){
  .lanes{grid-template-columns:1fr;gap:12px}
  .flowarrow{display:none}
  .grid4{grid-template-columns:repeat(2,1fr)}
}
@media print{
  header{position:static} .scrim,.drawer,button.tbtn{display:none!important}
  .node{break-inside:avoid}
}
"""

JS = """
const S = JSON.parse(document.getElementById('sections').textContent);
const N = JSON.parse(document.getElementById('nodes').textContent);
const scrim = document.getElementById('scrim');
const drawer = document.getElementById('drawer');
let current = null;

function open(id, tabIndex){
  const node = N[id]; if(!node) return;
  current = id;
  document.getElementById('dtitle').textContent = node.title;
  const who = document.getElementById('dwho');
  who.textContent = node.who_label || '';
  who.style.display = node.who_label ? '' : 'none';
  const tabs = document.getElementById('dtabs');
  tabs.innerHTML = '';
  node.refs.forEach((r,i)=>{
    const b = document.createElement('button');
    b.className = 'tab' + (i===(tabIndex||0) ? ' active' : '');
    b.textContent = r[0];
    b.onclick = ()=>open(id,i);
    tabs.appendChild(b);
  });
  const ref = node.refs[tabIndex||0];
  const sec = S[ref[1]] || {title:'Not found', body:'<p>Section '+ref[1]+' not found.</p>'};
  document.getElementById('dbody').innerHTML =
    '<p class="secnum">Section ' + ref[1] + '</p><h3>' + sec.title + '</h3>' + sec.body;
  document.getElementById('dbody').scrollTop = 0;
  document.getElementById('dsrc').textContent = 'Section ' + ref[1] + ' · ' + sec.title;
  drawer.classList.add('open'); scrim.classList.add('open');
  drawer.setAttribute('aria-hidden','false');
}
function close(){
  drawer.classList.remove('open'); scrim.classList.remove('open');
  drawer.setAttribute('aria-hidden','true'); current = null;
}
scrim.onclick = close;
document.getElementById('dclose').onclick = close;
document.addEventListener('keydown', e => { if(e.key === 'Escape') close(); });
document.querySelectorAll('[data-node]').forEach(el => {
  el.onclick = () => open(el.getAttribute('data-node'), 0);
});

const t = document.getElementById('theme');
function setTheme(dark){
  document.body.classList.toggle('dark', dark);
  t.textContent = dark ? 'Light' : 'Dark';
  try{ localStorage.setItem('dpf-theme', dark ? 'dark' : 'light'); }catch(e){}
}
t.onclick = () => setTheme(!document.body.classList.contains('dark'));
try{ if(localStorage.getItem('dpf-theme') === 'dark') setTheme(true); }catch(e){}
"""


# --------------------------------------------------------------------------
# 5. Render
# --------------------------------------------------------------------------

def esc(s: str) -> str:
    return html.escape(s, quote=True)


def render_node(nd: dict) -> str:
    kind = " gate" if nd.get("kind") == "gate" else ""
    chips = "".join(f'<span class="refchip">{esc(l)}</span>' for l, _ in nd["refs"][:4])
    more = len(nd["refs"]) - 4
    if more > 0:
        chips += f'<span class="refchip">+{more}</span>'
    path = f'<div class="path">{esc(nd["path"])}</div>' if nd.get("path") else ""
    return f"""<button class="node {nd['who']}{kind}" data-node="{nd['id']}"
      aria-label="Open details for {esc(nd['title'])}">
      <div class="node-top"><span class="step">{esc(nd['step'])}</span>
        <h3>{esc(nd['title'])}</h3></div>
      <p>{esc(nd['desc'])}</p>{path}
      <div class="who">{esc(nd.get('who_label',''))}</div>
      <div class="reflist">{chips}</div></button>"""


def render_plane(nd: dict) -> str:
    chips = "".join(f'<span class="refchip">{esc(l)}</span>' for l, _ in nd["refs"][:3])
    more = len(nd["refs"]) - 3
    if more > 0:
        chips += f'<span class="refchip">+{more}</span>'
    return f"""<button class="node {nd['who']}" data-node="{nd['id']}"
      aria-label="Open details for {esc(nd['title'])}">
      <div class="node-top"><h3>{esc(nd['title'])}</h3></div>
      <p>{esc(nd['desc'])}</p>
      <div class="reflist">{chips}</div></button>"""


def main() -> int:
    if not SRC.exists():
        print(f"error: {SRC} not found", file=sys.stderr)
        return 1

    md = SRC.read_text(encoding="utf-8")
    sections = parse_sections(md)

    all_nodes = {}
    for nd in NODES + PLANES:
        all_nodes[nd["id"]] = nd
    for nd in FOOTER:
        all_nodes[nd["id"]] = dict(nd, who="auto", who_label="", desc="")

    # Which sections do we actually need to embed?
    needed, missing = set(), []
    for nd in all_nodes.values():
        for label, num in nd["refs"]:
            needed.add(num)
            if num not in sections:
                missing.append((nd["id"], label, num))
    if missing:
        for nid, label, num in missing:
            print(f"warning: node '{nid}' references missing section {num} ({label})",
                  file=sys.stderr)

    payload = {num: {"title": sections[num]["title"],
                     "body": md_to_html(sections[num]["body"])}
               for num in sorted(needed) if num in sections}

    nodes_payload = {nid: {"title": nd["title"],
                           "who_label": nd.get("who_label", ""),
                           "refs": nd["refs"]}
                     for nid, nd in all_nodes.items()}

    # ---- lanes
    lane_html = []
    for li, (lane_id, lane_title, lane_sub) in enumerate(LANES):
        cards = "".join(render_node(nd) for nd in NODES if nd["lane"] == lane_id)
        lane_html.append(
            f'<div class="lane"><div class="lane-head"><h2>{esc(lane_title)}</h2>'
            f'<p>{esc(lane_sub)}</p></div>{cards}</div>')
        if li < len(LANES) - 1:
            lane_html.append('<div class="flowarrow" aria-hidden="true">'
                             '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
                             'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                             'stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></div>')

    planes_html = "".join(render_plane(nd) for nd in PLANES)
    footer_html = "".join(
        f'<button class="chip" data-node="{nd["id"]}">{esc(nd["title"])}</button>'
        for nd in FOOTER)

    legend = "".join(
        f'<span><i class="dot {k}"></i>{esc(v)}</span>'
        for k, v in WHO_LABELS.items())

    def jdump(obj):
        return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")

    page = f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Product Framework — Method</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>Data Product Framework — Method</h1>
    <p>BRD &rarr; TDD &rarr; Build, with gated promotion. Select any step for its
       instructions and worked example.</p>
  </div>
  <div class="legend">{legend}</div>
  <button class="tbtn" id="theme">Dark</button>
</header>

<main>
  <p class="hint"><strong>How to read this:</strong> the four columns are the
     lifecycle. Solid cards are artefacts someone owns; dashed cards are gates that
     must pass before work moves right. Every card opens the relevant section of the
     plan — instructions and worked example — in a side panel.</p>

  <div class="lanes">{''.join(lane_html)}</div>

  <div class="band">
    <h2>Platform planes</h2>
    <p class="sub">Reusable across every data product. The TDD selects from these;
       the BRD never sees them.</p>
    <div class="grid4">{planes_html}</div>
  </div>

  <div class="band">
    <h2>Reference</h2>
    <p class="sub">Supporting sections of the plan.</p>
    <div class="chips">{footer_html}</div>
  </div>
</main>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true" aria-label="Section detail">
  <div class="dhead">
    <div class="row">
      <div style="flex:1">
        <h2 id="dtitle">&nbsp;</h2>
        <p class="who" id="dwho"></p>
      </div>
      <button class="close" id="dclose" aria-label="Close">&times;</button>
    </div>
    <div class="tabs" id="dtabs"></div>
  </div>
  <div class="dbody" id="dbody"></div>
  <div class="dfoot">
    <span id="dsrc"></span>
    <a href="{SRC.name}" target="_blank" rel="noopener">Open {SRC.name}</a>
  </div>
</aside>

<script type="application/json" id="sections">{jdump(payload)}</script>
<script type="application/json" id="nodes">{jdump(nodes_payload)}</script>
<script>{JS}</script>
</body>
</html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({len(page):,} bytes) — "
          f"{len(payload)} sections embedded, {len(all_nodes)} nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
