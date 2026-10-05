"""Policy lint (`dpf lint`): tool tiers, bespoke-code markers, ADR references and terminology.

* Every skill's `tool` is in registry/mcp_servers.yaml and its `tool_tier` equals that tool's tier.
* A tier 4 or 5 skill fails when one of its `needs` is covered by a tier 1-3 server: use the
  server. A need that no server covers must be listed in `no_mcp_option_yet`.
* A tier 5 (bespoke code) skill cites an ADR that exists.
* Code under examples/ and products/ that imports a cloud SDK or database driver carries a
  `# dpf: skill=<id> tier=<n> adr=<ADR>` marker naming a real skill, its tier and an ADR.
* Prose uses "Knowledge Catalog", not the retired product name (identifiers such as
  `google_dataplex_datascan` or `dataplex.googleapis.com` are fine).
"""

from __future__ import annotations

import re
from pathlib import Path

from dpf.core import Report, Workspace
from dpf.generate.render import parse_markers

CLOUD_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(google\.cloud|googleapiclient|oracledb|cx_Oracle|psycopg2?|pymysql|mysql\.connector|"
    r"pyodbc|pymssql|snowflake|boto3|azure|sqlalchemy|apache_beam|pyspark)\b", re.M)
CODE_GLOBS = ("examples/**/*.py", "products/**/*.py")
PROSE_GLOBS = ("*.md", "docs/**/*.md", "openspec/**/*.md", "skills/**/*.md", "methodologies/**/*.md",
               "engines/**/*.md", "adr/**/*.md", "products/**/*.md", "examples/**/*.md", "registry/**/*.yaml",
               "openspec/**/*.yaml", "docs/**/*.html")
RETIRED = {  # retired product name -> current name (prose only)
    r"\bDataplex\b": "Knowledge Catalog",
    r"\bBigLake metastore\b": "Lakehouse runtime catalog",
    r"\bAnalytics Hub\b": "BigQuery sharing",
    r"\bDataproc Serverless\b": "Managed Service for Apache Spark",
    r"\bBigQuery Omni\b": "cross-cloud connections",
}
# The naming table maps current to former names; only the catalog's former name is banned there too.
NAMING_TABLE = {"openspec/project.md", "docs/data-product-framework-plan.md", "docs/index.html"}
SKIP_DIRS = {".venv", "node_modules", "generated", "golden", ".git"}


def _files(root: Path, globs: tuple[str, ...]) -> list[Path]:
    out: set[Path] = set()
    for g in globs:
        for f in root.glob(g):
            if f.is_file() and not (set(f.relative_to(root).parts) & SKIP_DIRS):
                out.add(f)
    return sorted(out)


def _strip_code(text: str) -> str:
    """Blank fenced blocks, inline code and URLs (identifiers there may keep API names); keep line numbers."""
    keep_lines = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    text = re.sub(r"```.*?```", keep_lines, text, flags=re.S)
    text = re.sub(r"<(pre|code)\b.*?</\1>", keep_lines, text, flags=re.S | re.I)
    text = re.sub(r"`[^`\n]*`", "", text)
    return re.sub(r"https?://\S+", "", text)


def lint_tiers(ws: Workspace, report: Report) -> None:
    report.head("lint · tool tiers", gate="lint")
    reg = ws.registry()
    tools = reg.tools
    servers = [s for s in reg.get("mcp_servers.yaml", "servers", []) or [] if int(s.get("tier", 9)) <= 3]
    no_option = set(reg.get("mcp_servers.yaml", "no_mcp_option_yet", []) or [])
    bad = 0
    for sid, s in sorted(ws.skills.items()):
        tool, tier = s.get("tool"), s.get("tool_tier")
        t = tools.get(tool)
        if t is None:
            report.fail(f"{sid}: tool '{tool}' is not in registry/mcp_servers.yaml")
            bad += 1
            continue
        if int(t["tier"]) != int(tier or 0):
            report.fail(f"{sid}: tool_tier {tier} but {tool} is tier {t['tier']} in the registry")
            bad += 1
        if s.get("inspection_tool") and s.get("inspection_tool") not in tools:
            report.fail(f"{sid}: inspection_tool '{s.get('inspection_tool')}' is not in the registry")
            bad += 1
        if int(tier or 0) >= 4:
            for need in s.get("needs") or []:
                covering = [x["id"] for x in servers if need in (x.get("covers") or [])]
                if covering:
                    report.fail(f"{sid}: needs '{need}', which {', '.join(covering)} (tier ≤3) covers; use it instead of tier {tier}")
                    bad += 1
                elif need not in no_option and need not in (t.get("covers") or []):
                    report.fail(f"{sid}: need '{need}' is covered by no registered tool; add it to a tool's covers "
                                "or to no_mcp_option_yet after checking for an MCP option")
                    bad += 1
        if int(tier or 0) == 5:
            adr = s.get("adr")
            if not adr:
                report.fail(f"{sid}: tier 5 (bespoke code) needs an ADR")
                bad += 1
            elif adr not in ws.adrs:
                report.fail(f"{sid}: cites {adr}, which has no ADR file")
                bad += 1
    if not bad:
        report.ok(f"{len(ws.skills)} skills: tiers match the registry, no tier 4/5 skill bypasses an MCP server, "
                  "bespoke skills cite ADRs")


def lint_code(ws: Workspace, report: Report) -> None:
    report.head("lint · bespoke code markers", gate="lint")
    checked = 0
    for f in _files(ws.root, CODE_GLOBS):
        text = f.read_text(encoding="utf-8", errors="replace")
        imports = sorted(set(CLOUD_IMPORT.findall(text)))
        if not imports:
            continue
        checked += 1
        rel = f.relative_to(ws.root)
        allm = parse_markers(text)
        if any(m.get("role") == "fixture" for m in allm):
            report.ok(f"{rel}: test fixture (role=fixture), not pipeline code")
            continue
        marks = [m for m in allm if "skill" in m]
        if not marks:
            report.fail(f"{rel}: imports {', '.join(imports)} but has no `# dpf: skill=<id> tier=<n> adr=<ADR>` marker")
            continue
        m = marks[0]
        skill = ws.skills.get(m["skill"])
        if skill is None:
            report.fail(f"{rel}: marker names skill '{m['skill']}', which does not exist")
            continue
        if str(skill.get("tool_tier")) != m.get("tier"):
            report.fail(f"{rel}: marker says tier {m.get('tier')} but skill {m['skill']} is tier {skill.get('tool_tier')}")
        if m.get("tier") == "5":
            adr = m.get("adr")
            if not adr or adr not in ws.adrs:
                report.fail(f"{rel}: bespoke code must cite an existing ADR (marker adr={adr})")
                continue
        report.ok(f"{rel}: {m['skill']} tier {m.get('tier')}" + (f", {m['adr']}" if m.get("adr") else ""))
    if not checked:
        report.ok("no cloud SDK or database driver imports under examples/ or products/")


def lint_terms(ws: Workspace, report: Report) -> None:
    report.head("lint · terminology", gate="lint")
    hits = []
    for f in _files(ws.root, PROSE_GLOBS):
        rel = str(f.relative_to(ws.root))
        text = _strip_code(f.read_text(encoding="utf-8", errors="replace"))
        rules = {k: v for k, v in RETIRED.items() if rel not in NAMING_TABLE or v == "Knowledge Catalog"}
        for i, line in enumerate(text.splitlines(), 1):
            for pat, current in rules.items():
                m = re.search(pat, line)
                if m:
                    hits.append(f"{rel}:{i} '{m.group(0)}' (say {current})")
    report.check(not hits, "prose uses current product names (Knowledge Catalog, BigQuery sharing, ...)",
                 f"retired product name(s) in prose: {'; '.join(hits[:8])}" + (f" (+{len(hits) - 8} more)" if len(hits) > 8 else ""))


def lint(ws: Workspace, report: Report) -> int:
    lint_tiers(ws, report)
    lint_code(ws, report)
    lint_terms(ws, report)
    return report.failures
