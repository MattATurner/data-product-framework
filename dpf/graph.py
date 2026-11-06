"""The product's model graph: raw relations, declared models and the edges between them.

Edges come from `{{ ref('x') }}` in authored bodies and from pack attributes (a dimension's
`source`, a fact's `source` and `dim_refs`, a nested view's `nesting` children). Compose,
design checks, methodology rules and the generators all read the same graph.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from functools import cached_property

from dpf.core import LAYERS, Product, retarget_env

REF = re.compile(r"\{\{\s*ref\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)\s*\}\}")
VAR = re.compile(r"\{\{\s*var\(\s*['\"]([A-Za-z0-9_]+)['\"]\s*\)\s*\}\}")
LAYER_RANK = {"raw": 0, "upstream": 0, "staging": 1, "silver": 2, "gold": 3}


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
        for u in p.manifest.get("upstream", []) or []:
            self._build_upstream(u)
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

    def _build_upstream(self, u: dict) -> None:
        p = self.p
        if u.get("product"):
            up_id = u["product"]
            if up_id == p.id:
                self.problems.append(f"upstream product '{up_id}' cannot reference itself")
                return
            up_path = p.ws.root / "products" / up_id / "product.yaml"
            if not up_path.exists():
                self.problems.append(f"upstream product '{up_id}' is not found in products/{up_id}/product.yaml")
                return
            up_prod = p.ws.product(up_id)
            if p.active_env and p.active_env in ((up_prod.manifest.get("deployment") or {}).get("environments") or {}):
                up_prod = retarget_env(up_prod, p.active_env)
            up_g = ProductGraph(up_prod)
            up_dep = up_prod.manifest.get("deployment") or {}
            up_ds = up_dep.get("datasets") or {}
            up_pts = (up_prod.manifest.get("governance") or {}).get("policy_tags") or []
            for mname in u.get("models") or []:
                up_node = up_g.get(mname)
                if up_node is None or up_node.kind not in ("model", "upstream"):
                    self.problems.append(f"upstream product '{up_id}' does not declare model '{mname}'")
                    continue
                if up_node.layer == "staging":
                    self.problems.append(
                        f"upstream product '{up_id}': staging model '{mname}' cannot be bound across product boundaries")
                    continue
                mdict = copy.deepcopy(up_node.model)
                ds_key = up_node.model.get("dataset") or up_node.layer
                mdict["_upstream_source"] = up_id
                mdict["_upstream_kind"] = "product"
                mdict["_upstream_project"] = up_node.model.get("_upstream_project") or up_dep.get("gcp_project") or ""
                mdict["_upstream_dataset"] = up_node.model.get("_upstream_dataset") or up_ds.get(ds_key) or ds_key
                mdict["_phys_table"] = up_node.model.get("_phys_table") or mname
                mdict["_output_columns"] = up_g.output_columns(mname)
                mdict["_policy_tags"] = [copy.deepcopy(pt) for pt in up_pts if pt.get("model") == mname]
                if u.get("brd_requirement_id"):
                    mdict["brd_requirement_id"] = list(u["brd_requirement_id"])
                if mname in self.nodes:
                    self.problems.append(f"upstream model '{mname}' is declared twice")
                self.nodes[mname] = Node(
                    name=mname, layer="upstream", kind="upstream", model=mdict,
                    pack=up_node.pack, role=up_node.role, engine=None,
                    emits="semantic-model.v1", source=up_id)
            return
        fid = u.get("foundation") or "unknown"
        reg_f = p.registry.foundations.get(fid) or {}
        gcp_project = u.get("gcp_project") or reg_f.get("gcp_project") or ""
        dataset = u.get("dataset") or reg_f.get("dataset") or ""
        tables = u.get("tables") if u.get("tables") is not None else (reg_f.get("tables") or [])
        if not gcp_project or not dataset or not tables:
            self.problems.append(
                f"upstream foundation '{fid}' is missing gcp_project, dataset or tables "
                "(declare inline or in registry/foundations.yaml)")
            return
        for t in tables:
            tname = t["name"]
            role = t.get("role") or "analytical_table"
            pack = t.get("methodology") or ("kimball" if role in ("fact", "dimension", "calendar") else "direct")
            mdict = copy.deepcopy(t)
            mdict["_upstream_source"] = fid
            mdict["_upstream_kind"] = "foundation"
            mdict["_upstream_project"] = gcp_project
            mdict["_upstream_dataset"] = t.get("dataset") or dataset
            mdict["_phys_table"] = t.get("table_name") or tname
            mdict["_output_columns"] = [c["name"] for c in (t.get("columns") or [])] or None
            mdict["_policy_tags"] = [copy.deepcopy(pt) for pt in (t.get("policy_tags") or [])]
            reqs = t.get("brd_requirement_id") or u.get("brd_requirement_id") or reg_f.get("brd_requirement_id") or []
            if reqs:
                mdict["brd_requirement_id"] = list(reqs)
            if tname in self.nodes:
                self.problems.append(f"upstream table '{tname}' is declared twice")
            self.nodes[tname] = Node(
                name=tname, layer="upstream", kind="upstream", model=mdict,
                pack=pack, role=role, engine=None, emits="semantic-model.v1", source=fid)

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
    def upstream_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == "upstream"]

    @property
    def semantic_nodes(self) -> list[Node]:
        out: list[Node] = []
        for name in self.topo():
            n = self.nodes[name]
            if n.kind == "upstream" or (n.kind == "model" and n.layer != "staging" and n.role != "ml_model"):
                out.append(n)
        return out

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
        return [n.name for n in (*self.upstream_nodes, *self.models) if n.role == "fact"]

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
        if not n or n.kind not in ("model", "upstream"):
            return None
        if n.kind == "upstream" and n.model.get("_output_columns"):
            return list(n.model["_output_columns"])
        m, attrs = n.model, n.model.get("attributes") or {}
        if n.role == "dimension":
            cols = [m.get("surrogate_key") or f"sk_{name.removeprefix('dim_')}"] + list(m.get("natural_key") or [])
            cols += list(attrs.get("tracked") or []) + list(attrs.get("current") or [])
            if int(attrs.get("scd_type", 1) or 1) == 2:
                cols += ["valid_from", "valid_to", "is_current", "version_no"]
            return [c for c in dict.fromkeys(cols) if c]
        if n.role == "calendar":
            return ["date_key", "calendar_date", "year", "quarter", "year_quarter", "month", "year_month",
                    "month_name", "day_of_week", "day_name", "is_weekend"]
        if n.role == "fact":
            cols = list(m.get("natural_key") or m.get("grain_columns") or [])
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
        if n.kind == "upstream":
            cols = list(m.get("grain_columns") or [])
            if m.get("surrogate_key"):
                cols.append(m["surrogate_key"])
            cols += list(m.get("natural_key") or [])
            cols += [x["name"] for x in attrs.get("measures", []) or []]
            return [c for c in dict.fromkeys(cols) if c] or None
        return select_columns(self.p.body(m))


def layers_in_use(product: Product) -> list[str]:
    return [layer for layer in LAYERS if product.layer_cfg(layer).get("models")]
