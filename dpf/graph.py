"""The product's model graph: raw relations, declared models and the edges between them.

Edges come from `{{ ref('x') }}` in authored bodies and from pack attributes (a dimension's
`source`, a fact's `source` and `dim_refs`, a nested view's `nesting` children). Compose,
design checks, methodology rules and the generators all read the same graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property

from dpf.core import LAYERS, Product

REF = re.compile(r"\{\{\s*ref\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)\s*\}\}")
VAR = re.compile(r"\{\{\s*var\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)\s*\}\}")
LAYER_RANK = {"raw": 0, "staging": 1, "silver": 2, "gold": 3}


def body_refs(body: str | None) -> list[str]:
    return list(dict.fromkeys(REF.findall(body or "")))


def body_vars(body: str | None) -> list[str]:
    return list(dict.fromkeys(VAR.findall(body or "")))


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def select_columns(sql: str | None) -> list[str] | None:
    """Best-effort output column names of the final top-level SELECT of a body.

    Good enough for design checks (does a model expose column X?). Returns None when the
    select list cannot be read (for example `SELECT *`).
    """
    if not sql:
        return None
    text = strip_sql_comments(sql)
    # find top-level SELECT ... FROM pairs (depth 0)
    depth, i, n = 0, 0, len(text)
    last_select = None
    tokens = []
    while i < n:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c in "'\"":
            j = text.find(c, i + 1)
            i = n if j < 0 else j
        elif depth == 0 and text[i:i + 6].upper() == "SELECT" and (i == 0 or not text[i - 1].isalnum() and text[i - 1] != "_"):
            last_select = i + 6
        elif depth == 0 and last_select is not None and text[i:i + 4].upper() == "FROM" and not text[i - 1].isalnum() \
                and (i + 4 >= n or not text[i + 4].isalnum()):
            tokens.append(text[last_select:i])
            last_select = None
        i += 1
    if not tokens:
        return None
    select_list = tokens[-1]
    items, depth, cur = [], 0, ""
    for c in select_list:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += c
    items.append(cur)
    cols = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        if item.upper().startswith("DISTINCT "):
            item = item[9:].strip()
        if item.endswith("*") or re.search(r"\*\s+EXCEPT", item, re.I):
            return None
        m = re.search(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", item, re.I)
        if m:
            cols.append(m.group(1))
            continue
        m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", item)
        if m:
            cols.append(m.group(1))
    return cols


@dataclass
class Node:
    name: str
    layer: str                    # raw | staging | silver | gold
    kind: str                     # raw | model
    model: dict = field(default_factory=dict)
    pack: str = "platform"
    role: str = "raw"
    engine: str | None = None
    emits: str = "raw-table.v1"
    inputs: list[str] = field(default_factory=list)
    source: str | None = None     # raw relations: owning source system


class ProductGraph:
    def __init__(self, product: Product):
        self.p = product
        self.nodes: dict[str, Node] = {}
        self.problems: list[str] = []
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.p
        reg = p.registry
        raw_fmt = (reg.defaults.get("naming") or {}).get("raw_table", "raw_{entity}")
        for s in p.manifest.get("sources", []) or []:
            for ent in s.get("entities", []) or []:
                name = raw_fmt.format(entity=ent, source_system=s.get("system_id"))
                if name in self.nodes:
                    self.problems.append(f"raw relation '{name}' is produced by two sources")
                self.nodes[name] = Node(name=name, layer="raw", kind="raw", source=s.get("system_id"),
                                        engine=None, emits="raw-table.v1")
        for layer, m in p.models():
            pack = "platform" if layer == "staging" else self.layer_pack(layer)
            node = Node(name=m["name"], layer=layer, kind="model", model=m, pack=pack, role=m.get("role", ""),
                        engine=p.layer_cfg(layer).get("engine"), emits=self.role_emits(pack, m.get("role", "")))
            if node.name in self.nodes:
                self.problems.append(f"model name '{node.name}' is declared twice")
            self.nodes[node.name] = node
        for node in self.nodes.values():
            if node.kind == "model":
                node.inputs = self._inputs(node)

    def layer_pack(self, layer: str) -> str:
        cfg = self.p.layer_cfg(layer)
        default = ((self.p.registry.defaults.get("defaults") or {}).get("methodology") or {}).get(layer, "direct")
        return cfg.get("methodology") or default

    def role_def(self, pack: str, role: str) -> dict | None:
        if pack == "platform":
            for r in self.p.registry.defaults.get("platform_roles", []) or []:
                if r.get("id") == role:
                    return r
            return None
        for r in (self.p.ws.packs.get(pack) or {}).get("roles", []) or []:
            if r.get("id") == role:
                return r
        return None

    def role_emits(self, pack: str, role: str) -> str:
        d = self.role_def(pack, role)
        return (d or {}).get("emits", "semantic-model.v1")

    def _inputs(self, node: Node) -> list[str]:
        m = node.model
        attrs = m.get("attributes") or {}
        found: list[str] = []
        found += body_refs(self.p.body(m))
        if attrs.get("source"):
            found.append(attrs["source"])
        for ref in attrs.get("dim_refs", []) or []:
            if ref.get("dimension"):
                found.append(ref["dimension"])
        for child in m.get("nesting", []) or []:
            if child.get("child"):
                found.append(child["child"])
        return list(dict.fromkeys(found))

    # ------------------------------------------------------------------ queries
    @property
    def models(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == "model"]

    @property
    def raw(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == "raw"]

    def get(self, name: str) -> Node | None:
        return self.nodes.get(name)

    def upstream(self, name: str, transitive: bool = True) -> list[str]:
        seen: list[str] = []
        stack = list(self.nodes[name].inputs) if name in self.nodes else []
        while stack:
            cur = stack.pop(0)
            if cur in seen:
                continue
            seen.append(cur)
            if transitive and cur in self.nodes:
                stack.extend(self.nodes[cur].inputs)
        return seen

    def downstream(self, name: str, transitive: bool = True) -> list[str]:
        out: list[str] = []
        frontier = [name]
        while frontier:
            cur = frontier.pop(0)
            for n in self.models:
                if cur in n.inputs and n.name not in out:
                    out.append(n.name)
                    if transitive:
                        frontier.append(n.name)
        return out

    @cached_property
    def cycle(self) -> list[str] | None:
        state: dict[str, int] = {}
        path: list[str] = []

        def visit(n: str) -> list[str] | None:
            state[n] = 1
            path.append(n)
            for i in self.nodes[n].inputs if n in self.nodes else []:
                if state.get(i) == 1:
                    return path[path.index(i):] + [i]
                if i in self.nodes and state.get(i) is None:
                    found = visit(i)
                    if found:
                        return found
            state[n] = 2
            path.pop()
            return None

        for name in self.nodes:
            if state.get(name) is None:
                found = visit(name)
                if found:
                    return found
        return None

    def topo(self) -> list[str]:
        order: list[str] = []
        seen: set[str] = set()

        def visit(n: str) -> None:
            if n in seen or n not in self.nodes:
                return
            seen.add(n)
            for i in self.nodes[n].inputs:
                visit(i)
            order.append(n)

        for name in sorted(self.nodes, key=lambda k: (LAYER_RANK[self.nodes[k].layer], k)):
            visit(name)
        return order

    def unresolved_inputs(self) -> list[tuple[str, str]]:
        return [(n.name, i) for n in self.models for i in n.inputs if i not in self.nodes]

    def facts(self) -> list[str]:
        return [n.name for n in self.models if n.role == "fact"]

    def scd2_sources(self) -> dict[str, list[str]]:
        """staging model -> type 2 dimensions that read its history."""
        out: dict[str, list[str]] = {}
        for n in self.models:
            attrs = n.model.get("attributes") or {}
            if n.role == "dimension" and int(attrs.get("scd_type", 1) or 1) == 2 and attrs.get("source"):
                out.setdefault(attrs["source"], []).append(n.name)
        return out

    def quarantine_rules(self, model: str) -> list[dict]:
        return [r for r in (self.p.manifest.get("quality") or {}).get("rules", []) or []
                if r.get("model") == model and r.get("on_fail") == "quarantine"]

    def output_columns(self, name: str) -> list[str] | None:
        """Columns a model exposes: generated roles from their declarations, authored ones from the body."""
        n = self.nodes.get(name)
        if not n or n.kind != "model":
            return None
        m, attrs = n.model, n.model.get("attributes") or {}
        if n.role == "dimension":
            cols = [m.get("surrogate_key") or f"sk_{name.removeprefix('dim_')}"] + list(m.get("natural_key") or [])
            cols += list(attrs.get("tracked") or []) + list(attrs.get("current") or [])
            if int(attrs.get("scd_type", 1) or 1) == 2:
                cols += ["valid_from", "valid_to", "is_current", "version_no"]
            return cols
        if n.role == "calendar":
            return ["date_key", "calendar_date", "year", "quarter", "year_quarter", "month", "year_month",
                    "month_name", "day_of_week", "day_name", "is_weekend"]
        if n.role == "fact":
            cols = list(m.get("natural_key") or [])
            for ref in attrs.get("dim_refs", []) or []:
                dim = self.nodes.get(ref.get("dimension"))
                if dim and dim.role == "dimension":
                    cols += [ref.get("natural_key"), dim.model.get("surrogate_key")]
                elif dim and dim.role == "calendar":
                    cols += ["date_key"]
            cols += [attrs.get("event_date")] if attrs.get("event_date") else []
            cols += [x["name"] for x in attrs.get("measures", []) or []]
            cols += list(attrs.get("degenerate") or [])
            cols += [x["name"] for x in attrs.get("flags", []) or []]
            return [c for c in dict.fromkeys(cols) if c]
        return select_columns(self.p.body(m))


def layers_in_use(product: Product) -> list[str]:
    return [layer for layer in LAYERS if product.layer_cfg(layer).get("models")]
