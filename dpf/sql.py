"""Shared BigQuery SQL lexical utilities, string escaping, and safe path resolution.

Zero-dependency, deterministic tokenizer used across G1 design checks, ProductGraph
column projection, semantic-layer inference, and engine renderers so SQL comments inside
string literals, identifier boundaries (e.g. `valid_from`), CTEs, and UNION ALL queries
are handled consistently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Token:
    kind: str    # COMMENT | JINJA | STRING | BACKTICK | LPAREN | RPAREN | COMMA | SEMI | STAR | WORD | OTHER
    value: str
    start: int
    end: int


def tokenize_sql(sql: str) -> list[Token]:
    """Lex BigQuery Standard SQL (plus Jinja `{{ ... }}` / `{% ... %}`) into tokens."""
    tokens: list[Token] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]

        # Jinja delimiters: {{ ... }}, {% ... %}, {# ... #}
        if c == "{" and i + 1 < n and sql[i + 1] in "{%#":
            close = {"{": "}}", "%": "%}", "#": "#}"}[sql[i + 1]]
            end = sql.find(close, i + 2)
            j = n if end < 0 else end + 2
            tokens.append(Token("JINJA", sql[i:j], i, j))
            i = j
            continue

        # Line comment: -- ...
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            end = sql.find("\n", i + 2)
            j = n if end < 0 else end
            tokens.append(Token("COMMENT", sql[i:j], i, j))
            i = j
            continue

        # Block comment: /* ... */
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            j = n if end < 0 else end + 2
            tokens.append(Token("COMMENT", sql[i:j], i, j))
            i = j
            continue

        # Raw / bytes string prefix: r'...', b'...', rb'...', etc.
        if c in "rRbB" and i + 1 < n:
            k = i
            while k < n and k - i < 2 and sql[k] in "rRbB":
                k += 1
            if k < n and sql[k] in ("'", '"') and (i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")):
                is_raw = any(ch in "rR" for ch in sql[i:k])
                quote = sql[k]
                j = _scan_string(sql, k, quote, raw=is_raw)
                tokens.append(Token("STRING", sql[i:j], i, j))
                i = j
                continue

        # Quoted string literal ('...', "...", '''...''', """...""")
        if c in ("'", '"'):
            j = _scan_string(sql, i, c, raw=False)
            tokens.append(Token("STRING", sql[i:j], i, j))
            i = j
            continue

        # Backtick identifier (`...`)
        if c == "`":
            j = i + 1
            while j < n:
                if sql[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if sql[j] == "`":
                    j += 1
                    break
                j += 1
            tokens.append(Token("BACKTICK", sql[i:j], i, j))
            i = j
            continue

        if c == "(":
            tokens.append(Token("LPAREN", c, i, i + 1))
            i += 1
            continue
        if c == ")":
            tokens.append(Token("RPAREN", c, i, i + 1))
            i += 1
            continue
        if c == ",":
            tokens.append(Token("COMMA", c, i, i + 1))
            i += 1
            continue
        if c == ";":
            tokens.append(Token("SEMI", c, i, i + 1))
            i += 1
            continue
        if c == "*":
            tokens.append(Token("STAR", c, i, i + 1))
            i += 1
            continue

        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            tokens.append(Token("WORD", sql[i:j], i, j))
            i = j
            continue

        # Whitespace or other punctuation (batch contiguous OTHER chars for speed)
        j = i + 1
        while j < n and sql[j] not in "-/'\"`(),;*{" and not (sql[j].isalpha() or sql[j] == "_"):
            if sql[j] in "rRbB":
                break
            j += 1
        tokens.append(Token("OTHER", sql[i:j], i, j))
        i = j

    return tokens


def _scan_string(sql: str, start: int, quote: str, *, raw: bool) -> int:
    n = len(sql)
    triple = sql[start:start + 3] == quote * 3
    delim = quote * 3 if triple else quote
    j = start + len(delim)
    while j < n:
        if not raw and sql[j] == "\\" and j + 1 < n:
            j += 2
            continue
        if sql[j:j + len(delim)] == delim:
            return j + len(delim)
        j += 1
    return n


def strip_sql_comments(sql: str) -> str:
    """Strip SQL comments without altering string literals, backtick identifiers, or line counts."""
    out: list[str] = []
    for tok in tokenize_sql(sql):
        if tok.kind == "COMMENT":
            out.append("\n" * tok.value.count("\n") or " ")
        else:
            out.append(tok.value)
    return "".join(out)


def strip_sql_literals(sql: str) -> str:
    """Strip SQL comments and replace quoted string literals with `''`."""
    out: list[str] = []
    for tok in tokenize_sql(sql):
        if tok.kind == "COMMENT":
            out.append("\n" * tok.value.count("\n") or " ")
        elif tok.kind == "STRING":
            out.append("''")
        else:
            out.append(tok.value)
    return "".join(out)


def blank_literals_and_parens(sql: str) -> str:
    """Strip SQL comments, string literals, and parenthesised subqueries, leaving depth-0 SQL."""
    out: list[str] = []
    depth = 0
    for tok in tokenize_sql(sql):
        if tok.kind == "COMMENT":
            if depth == 0:
                out.append("\n" * tok.value.count("\n") or " ")
            continue
        if tok.kind == "LPAREN":
            depth += 1
            if depth == 1:
                out.append(" () ")
            continue
        if tok.kind == "RPAREN":
            depth = max(0, depth - 1)
            continue
        if depth > 0:
            continue
        if tok.kind in ("STRING", "BACKTICK"):
            out.append(" '' ")
        else:
            out.append(tok.value)
    return "".join(out)


def _sig_tokens(sql: str) -> list[Token]:
    """Return non-comment, non-pure-whitespace tokens."""
    return [t for t in tokenize_sql(sql) if t.kind != "COMMENT" and not (t.kind == "OTHER" and not t.value.strip())]


def _skip_parens(toks: list[Token], idx: int) -> int:
    """Given toks[idx].kind == 'LPAREN', return index immediately after matching RPAREN."""
    depth = 0
    n = len(toks)
    while idx < n:
        if toks[idx].kind == "LPAREN":
            depth += 1
        elif toks[idx].kind == "RPAREN":
            depth -= 1
            if depth == 0:
                return idx + 1
        idx += 1
    return n


def _extract_ctes(toks: list[Token]) -> tuple[dict[str, list[Token]], int]:
    """If query starts with `WITH`, return ({cte_name_lower: inner_tokens}, index_after_ctes)."""
    ctes: dict[str, list[Token]] = {}
    i, n = 0, len(toks)
    if i >= n or toks[i].kind != "WORD" or toks[i].value.upper() != "WITH":
        return ctes, 0
    i += 1
    if i < n and toks[i].kind == "WORD" and toks[i].value.upper() == "RECURSIVE":
        i += 1
    while i < n:
        if toks[i].kind not in ("WORD", "BACKTICK"):
            break
        cte_name = toks[i].value.strip("`").lower()
        i += 1
        if i < n and toks[i].kind == "WORD" and toks[i].value.upper() == "AS":
            i += 1
        if i < n and toks[i].kind == "LPAREN":
            end = _skip_parens(toks, i)
            ctes[cte_name] = toks[i + 1 : end - 1]
            i = end
        else:
            break
        if i < n and toks[i].kind == "COMMA":
            i += 1
            continue
        break
    return ctes, i


def _select_clause_tokens(toks: list[Token]) -> list[Token] | None:
    """Extract the depth-0 SELECT projection tokens of the primary query (first branch on UNION)."""
    _, start = _extract_ctes(toks)
    i, n = start, len(toks)
    # Unwrap leading outer parentheses if the entire main query is parenthesised
    while i < n and toks[i].kind == "LPAREN":
        end = _skip_parens(toks, i)
        toks = toks[i + 1 : end - 1]
        _, start = _extract_ctes(toks)
        i, n = start, len(toks)

    depth = 0
    sel_start: int | None = None
    stop_words = {"FROM", "WHERE", "GROUP", "HAVING", "QUALIFY", "WINDOW", "ORDER", "LIMIT",
                  "UNION", "INTERSECT", "EXCEPT"}
    while i < n:
        t = toks[i]
        if t.kind == "LPAREN":
            depth += 1
        elif t.kind == "RPAREN":
            depth = max(0, depth - 1)
        elif depth == 0:
            if sel_start is None and t.kind == "WORD" and t.value.upper() == "SELECT":
                sel_start = i + 1
            elif sel_start is not None:
                if t.kind == "SEMI" or (t.kind == "WORD" and t.value.upper() in stop_words):
                    return toks[sel_start:i]
        i += 1
    if sel_start is not None:
        return toks[sel_start:]
    return None


def select_columns(sql: str | None) -> list[str] | None:
    """Output column names of a SELECT body, or None if `*` / `* EXCEPT` makes them static-unknown.

    Properly handles:
    - Columns ending in `_from` (e.g. `valid_from`) without truncating the SELECT list
    - Comments inside string literals, triple-quoted strings, and backtick identifiers
    - `WITH` CTEs and `UNION ALL` (using the first SELECT per BigQuery semantics)
    """
    if not sql:
        return None
    toks = _sig_tokens(sql)
    sel = _select_clause_tokens(toks)
    if not sel:
        return None

    # Strip leading DISTINCT / ALL / AS STRUCT / AS VALUE
    idx = 0
    while idx < len(sel) and sel[idx].kind == "WORD" and sel[idx].value.upper() in ("DISTINCT", "ALL"):
        idx += 1
    if idx + 1 < len(sel) and sel[idx].kind == "WORD" and sel[idx].value.upper() == "AS" \
            and sel[idx + 1].kind == "WORD" and sel[idx + 1].value.upper() in ("STRUCT", "VALUE"):
        idx += 2
    sel = sel[idx:]
    if not sel:
        return None

    # Split on depth-0 commas
    items: list[list[Token]] = []
    cur: list[Token] = []
    depth = 0
    for t in sel:
        if t.kind == "LPAREN":
            depth += 1
            cur.append(t)
        elif t.kind == "RPAREN":
            depth = max(0, depth - 1)
            cur.append(t)
        elif t.kind == "COMMA" and depth == 0:
            if cur:
                items.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        items.append(cur)

    cols: list[str] = []
    for item in items:
        # Any depth-0 STAR (*, t.*, * EXCEPT (...), * REPLACE (...)) makes projection unknown
        d = 0
        has_star = False
        for t in item:
            if t.kind == "LPAREN":
                d += 1
            elif t.kind == "RPAREN":
                d = max(0, d - 1)
            elif d == 0 and t.kind == "STAR":
                has_star = True
                break
        if has_star:
            return None

        # Explicit alias: `... AS <ident>` at depth 0
        alias: str | None = None
        if len(item) >= 2 and item[-2].kind == "WORD" and item[-2].value.upper() == "AS" \
                and item[-1].kind in ("WORD", "BACKTICK"):
            alias = item[-1].value.strip("`")
        elif item[-1].kind in ("WORD", "BACKTICK"):
            # Implicit alias or bare/qualified column reference (e.g. `t.col` or `SUM(x) total`)
            alias = item[-1].value.strip("`")
        if alias:
            cols.append(alias)
    return cols


def _clause_violations_in_tokens(toks: list[Token]) -> tuple[bool, bool]:
    """Return (has_qualify_or_limit, has_nontrivial_where) at depth 0 of `toks`."""
    has_ql = False
    has_where = False
    depth = 0
    n = len(toks)
    i = 0
    while i < n:
        t = toks[i]
        if t.kind == "LPAREN":
            depth += 1
        elif t.kind == "RPAREN":
            depth = max(0, depth - 1)
        elif depth == 0 and t.kind == "WORD":
            up = t.value.upper()
            if up in ("QUALIFY", "LIMIT"):
                has_ql = True
            elif up == "WHERE":
                # Check if the entire WHERE predicate is just `TRUE` (followed by clause end / EOF)
                rest = []
                j = i + 1
                rd = 0
                clause_end = {"GROUP", "HAVING", "QUALIFY", "WINDOW", "ORDER", "LIMIT",
                              "UNION", "INTERSECT", "EXCEPT"}
                while j < n:
                    rt = toks[j]
                    if rt.kind == "LPAREN":
                        rd += 1
                    elif rt.kind == "RPAREN":
                        rd = max(0, rd - 1)
                    elif rd == 0 and (rt.kind == "SEMI" or (rt.kind == "WORD" and rt.value.upper() in clause_end)):
                        break
                    rest.append(rt)
                    j += 1
                if not (len(rest) == 1 and rest[0].kind == "WORD" and rest[0].value.upper() == "TRUE"):
                    has_where = True
        i += 1
    return has_ql, has_where


def _primary_from_ctes(toks: list[Token], cte_names: set[str]) -> set[str]:
    """Return CTE names referenced in primary `FROM <cte>` (or `INNER JOIN <cte>`) clauses, not LEFT JOIN lookups."""
    used: set[str] = set()
    depth = 0
    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind == "LPAREN":
            depth += 1
        elif t.kind == "RPAREN":
            depth = max(0, depth - 1)
        elif depth == 0 and t.kind == "WORD" and t.value.upper() == "FROM":
            if i + 1 < n and toks[i + 1].kind in ("WORD", "BACKTICK"):
                cand = toks[i + 1].value.strip("`").lower()
                if cand in cte_names:
                    used.add(cand)
    return used


def find_staging_violations(sql: str) -> dict[str, list[str]]:
    """Inspect a staging SQL body (top-level + primary-stream CTEs) for silent row-dropping clauses.

    Returns dict with keys:
      - `qualify_limit`: list of scopes (`"top-level"` or `"CTE '<name>'"`) with QUALIFY or LIMIT
      - `where`: list of scopes (`"top-level"` or `"CTE '<name>'"`) with non-trivial WHERE
    Note: `LEFT JOIN (SELECT ... QUALIFY ...)` lookup subqueries are intentionally exempt because
    they deduplicate lookup attributes without dropping rows from the primary staged stream.
    """
    toks = _sig_tokens(sql)
    ctes, main_start = _extract_ctes(toks)
    main_toks = toks[main_start:]

    qualify_limit: list[str] = []
    where_scopes: list[str] = []

    ql, wh = _clause_violations_in_tokens(main_toks)
    if ql:
        qualify_limit.append("top-level")
    if wh:
        where_scopes.append("top-level")

    # Trace primary-stream CTEs transitively from the main FROM clause
    if ctes:
        cte_keys = set(ctes)
        to_visit = list(_primary_from_ctes(main_toks, cte_keys))
        visited: set[str] = set()
        while to_visit:
            cname = to_visit.pop()
            if cname in visited:
                continue
            visited.add(cname)
            ctoks = ctes[cname]
            c_ql, c_wh = _clause_violations_in_tokens(ctoks)
            if c_ql:
                qualify_limit.append(f"CTE '{cname}'")
            if c_wh:
                where_scopes.append(f"CTE '{cname}'")
            to_visit.extend(_primary_from_ctes(ctoks, cte_keys) - visited)

    return {"qualify_limit": qualify_limit, "where": where_scopes}


def sql_escape_str(value: str) -> str:
    """Escape a Python string for embedding inside a BigQuery single-quoted SQL string literal."""
    return (str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\r", "\\r")
            .replace("\n", "\\n"))


def safe_subpath(base: Path, rel: str | Path) -> Path:
    """Resolve `rel` under `base`, raising ValueError on absolute paths or `..` traversal."""
    rel_p = Path(rel)
    if rel_p.is_absolute():
        raise ValueError(f"path '{rel}' must be relative to {base}")
    base_res = base.resolve()
    resolved = (base_res / rel_p).resolve()
    if not resolved.is_relative_to(base_res):
        raise ValueError(f"path '{rel}' escapes workspace boundary {base}")
    return resolved


def id_sort_key(item: str) -> tuple[str, int, str]:
    """Safe sort key for DPF IDs like `R-12`, `AX-3`, `D-4` without crashing on non-numeric suffixes."""
    m = re.match(r"^([A-Za-z]+)-(\d+)$", item)
    if m:
        return (m.group(1), int(m.group(2)), item)
    return (item, 0, item)
