"""G2 — compose the pipeline from skills (`dpf compose`).

Every stage is instantiated per scope: source-scoped stages once per source, model-scoped
stages once per declared model, product-scoped stages once. A skill is selected for an
instance when its `selects_when` matches the instance (dotted paths into product, source,
model and layer; list values mean any of). Source- and model-scoped instances need exactly
one skill; product-scoped stages run every matching skill. Edges are type-checked: what a
node consumes must be produced upstream (or be an authored or runtime input).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from dpf.core import Product, Report, write_json, write_text
from dpf.graph import ProductGraph

STAGES = ["extract", "land", "stage", "integrate", "consume", "govern", "test", "assemble", "render",
          "orchestrate", "publish", "register", "monitor"]
DESIGN_STAGES = ["define", "design"]
SOURCE_STAGES = {"extract", "land"}
MODEL_STAGES = {"stage", "integrate", "consume"}
# Contracts that are authored, or observed at run time, rather than produced by a build node.
INPUT_CONTRACTS = {"brd.v1", "product-manifest.v1", "signoff.v1", "acceptance.v1", "source-binding.v1",
                   "observability-policy.v1", "run-evidence.v1", "test-evidence.v1"}


@dataclass
class DagNode:
    id: str
    stage: str
    scope: str
    instance: str
    skill: str
    tool: str
    tier: int
    consumes: list[str]
    produces: list[str]
    implements: str | None = None
    detail: dict = field(default_factory=dict)


def _lookup(ctx: dict, dotted: str):
    cur = ctx
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def matches(selects_when: dict | None, ctx: dict) -> bool:
    for key, want in (selects_when or {}).items():
        have = _lookup(ctx, key)
        if isinstance(want, list):
            if have not in want:
                return False
        elif have != want:
            return False
    return True


class Composer:
    def __init__(self, p: Product, report: Report):
        self.p, self.r = p, report
        self.g = ProductGraph(p)
        self.nodes: list[DagNode] = []
        self.edges: list[dict] = []
        self.ok = True

    def fail(self, msg: str) -> None:
        self.ok = False
        self.r.fail(msg)

    # ------------------------------------------------------------------ compose
    def compose(self) -> dict:
        p, ws = self.p, self.p.ws
        man = p.manifest
        skills = ws.skills
        layers = man.get("layers") or {}

        def skill_node(s, stage, scope, instance, detail=None) -> DagNode:
            d = s.dpf
            return DagNode(id=f"{stage}:{instance}" if scope != "product" else f"{stage}:{s.id}",
                           stage=stage, scope=scope, instance=instance, skill=s.id, tool=d.get("tool"),
                           tier=d.get("tool_tier"), consumes=list(d.get("consumes") or []),
                           produces=list(d.get("produces") or []), implements=d.get("implements"),
                           detail=detail or {})

        # -- source-scoped
        for src in man.get("sources", []) or []:
            ctx = {"product": man, "source": src}
            for stage in ("extract", "land"):
                cands = [s for s in skills.values() if s.get("stage") == stage and s.get("scope") == "source"
                         and matches(s.get("selects_when"), ctx)]
                inst = src["system_id"]
                if len(cands) != 1:
                    self.fail(f"{stage}:{inst}: {'no skill matches' if not cands else 'ambiguous: ' + ', '.join(c.id for c in cands)}"
                              f" (engine={src.get('engine')}, capture_mode={src.get('capture_mode')}, "
                              f"raw storage={(layers.get('raw') or {}).get('storage')})")
                    continue
                self.nodes.append(skill_node(cands[0], stage, "source", inst,
                                             {"entities": src.get("entities"), "capture_mode": src.get("capture_mode")}))
            self._edge(f"extract:{src['system_id']}", f"land:{src['system_id']}", "landing-manifest.v1")

        # -- model-scoped
        stage_of = (p.registry.defaults.get("layer_stages") or {"staging": "stage", "silver": "integrate", "gold": "consume"})
        for n in self.g.models:
            layer_cfg = dict(layers.get(n.layer) or {})
            layer_cfg["methodology"] = n.pack if n.pack != "platform" else None
            ctx = {"product": man, "model": n.model, "layer": layer_cfg}
            cands = [s for s in skills.values() if s.get("scope") == "model" and matches(s.get("selects_when"), ctx)]
            if n.pack != "platform":
                cands = [s for s in cands if s.get("methodology") in (None, n.pack)]
            stage = stage_of.get(n.layer, "integrate")
            if len(cands) != 1:
                self.fail(f"{stage}:{n.name}: {'no skill implements' if not cands else 'ambiguous skills for'} "
                          f"role '{n.role}' in pack '{n.pack}'" + (f" ({', '.join(c.id for c in cands)})" if cands else ""))
                continue
            node = skill_node(cands[0], stage, "model", n.name,
                              {"layer": n.layer, "role": n.role, "pack": n.pack, "engine": n.engine})
            self.nodes.append(node)
            self._engine_checks(n)

        # -- model edges (typed)
        by_instance = {nd.instance: nd for nd in self.nodes if nd.scope in ("model", "source")}
        for n in self.g.models:
            consumer = by_instance.get(n.name)
            if consumer is None:
                continue
            for i in n.inputs:
                src = self.g.get(i)
                if src is None:
                    self.fail(f"{n.name}: input '{i}' is not declared")
                    continue
                if src.kind == "raw":
                    producer_id, contract = f"land:{src.source}", "raw-table.v1"
                else:
                    producer_id, contract = f"{stage_of.get(src.layer)}:{src.name}", src.emits
                if contract not in consumer.consumes:
                    self.fail(f"{consumer.id}: skill {consumer.skill} consumes {', '.join(consumer.consumes) or 'nothing'} "
                              f"but '{i}' provides {contract}")
                self._edge(producer_id, consumer.id, contract)

        # -- product-scoped
        produced = {c for nd in self.nodes for c in nd.produces}
        for stage in STAGES:
            if stage in SOURCE_STAGES or stage in MODEL_STAGES:
                continue
            cands = [s for s in skills.values() if s.get("stage") == stage and s.get("scope", "product") == "product"
                     and matches(s.get("selects_when"), {"product": man})]
            if not cands:
                self.fail(f"{stage}: no skill is available for this stage")
                continue
            for s in sorted(cands, key=lambda x: x.id):
                nd = skill_node(s, stage, "product", p.id)
                self.nodes.append(nd)
            produced |= {c for s in cands for c in (s.get("produces") or [])}
        for nd in [x for x in self.nodes if x.scope == "product"]:
            for c in nd.consumes:
                if c in INPUT_CONTRACTS:
                    continue
                producers = [x for x in self.nodes if c in x.produces and STAGES.index(x.stage) <= STAGES.index(nd.stage)]
                if not producers:
                    self.fail(f"{nd.id}: consumes {c}, which no earlier stage produces")
                for x in producers:
                    if x.scope != "product" or x.id != nd.id:
                        self._edge(x.id, nd.id, c)

        # -- design-time skills (listed, not part of the build DAG)
        design = []
        for stage in DESIGN_STAGES:
            for s in sorted(skills.values(), key=lambda x: x.id):
                if s.get("stage") == stage and matches(s.get("selects_when"), {"product": man}):
                    design.append({"stage": stage, "skill": s.id, "gate": s.get("gate"), "tool": s.get("tool"),
                                   "tier": s.get("tool_tier")})
        self._orchestration_checks()
        dedup = {(e["from"], e["to"], e["contract"]): e for e in self.edges}
        return {
            "product_id": p.id,
            "stages": STAGES,
            "design_skills": design,
            "nodes": [nd.__dict__ for nd in self.nodes],
            "edges": sorted(dedup.values(), key=lambda e: (e["from"], e["to"], e["contract"])),
            "model_order": [x for x in self.g.topo() if self.g.nodes[x].kind == "model"],
        }

    def _edge(self, a: str, b: str, contract: str) -> None:
        self.edges.append({"from": a, "to": b, "contract": contract})

    def _engine_checks(self, n) -> None:
        ws = self.p.ws
        engine = n.engine
        adapter = ws.adapters.get(engine or "")
        if adapter is None:
            self.fail(f"{n.name}: engine '{engine}' has no adapter (engines/{engine}/adapter.yaml)")
            return
        if adapter.get("status") != "implemented" or n.role not in (adapter.get("implemented_roles") or []):
            self.fail(f"{n.name}: the {engine} adapter does not implement role '{n.role}' (status {adapter.get('status')})")
        if n.pack != "platform":
            pack = ws.packs.get(n.pack) or {}
            planned = {r["id"] for r in pack.get("planned_roles", []) or []}
            if n.role in planned:
                self.fail(f"{n.name}: role '{n.role}' is planned in pack '{n.pack}'")
            supported = (pack.get("supported_engines") or {}).get(n.role) or []
            if engine not in supported:
                self.fail(f"{n.name}: pack '{n.pack}' does not support engine '{engine}' for role '{n.role}' "
                          f"(supported: {', '.join(supported) or 'none'})")
            attrs = n.model.get("attributes") or {}
            if n.role == "fact" and attrs.get("fact_type", "transaction") != "transaction":
                self.fail(f"{n.name}: fact_type '{attrs.get('fact_type')}' is not implemented (transaction only)")

    def _orchestration_checks(self) -> None:
        man = self.p.manifest
        orch = (man.get("orchestration") or {}).get("engine")
        engines = {n.engine for n in self.g.models}
        if orch == "dataform" and engines - {"dataform"}:
            self.r.warn(f"orchestration engine 'dataform' cannot schedule {', '.join(sorted(engines - {'dataform'}))} "
                        "models; schedule them with the engine's own runner (see the generated orchestration notes)")


def compose(p: Product, report: Report, write: bool = True) -> tuple[bool, dict]:
    report.head(f"G2 · compose pipeline — {p.id}", gate="G2")
    c = Composer(p, report)
    dag = c.compose()
    if c.ok:
        report.ok(f"composed {len(dag['nodes'])} nodes and {len(dag['edges'])} typed edges across "
                  f"{len({n['stage'] for n in dag['nodes']})} stages")
        tiers = sorted({(n['skill'], n['tier'], n['tool']) for n in dag["nodes"]})
        bespoke = [f"{s} ({t})" for s, tier, t in tiers if tier == 5]
        if bespoke:
            report.info(f"tier 5 (bespoke code): {', '.join(bespoke)}")
    if write:
        write_json(p.generated_dir / "dag.json", dag)
        write_text(p.generated_dir / "dag.md", render_dag_md(dag))
    return c.ok, dag


def check_acceptance(p: Product, report: Report) -> bool:
    """G2: every business scenario (AX) is verified by an acceptance test (AT) in acceptance.yaml."""
    report.head(f"G2 · acceptance mapping — {p.id}", gate="G2")
    acc = p.acceptance
    if acc is None:
        report.fail(f"no acceptance mapping: add products/{p.id}/acceptance.yaml and set `acceptance:` in product.yaml")
        return False
    errs = p.ws.validate(acc, "acceptance.v1")
    if errs:
        report.fail(f"acceptance.yaml does not conform to acceptance.v1: {'; '.join(errs[:3])}")
        return False
    known = p.scenario_ids
    tests = acc.get("tests", []) or []
    ok = True
    verified: set[str] = set()
    seen: set[str] = set()
    for t in tests:
        if t["id"] in seen:
            report.fail(f"{t['id']} is declared twice")
            ok = False
        seen.add(t["id"])
        unknown = [a for a in t["verifies"] if a not in known]
        if unknown:
            report.fail(f"{t['id']} verifies {', '.join(unknown)}, which the BRD does not define")
            ok = False
        verified |= {a for a in t["verifies"] if a in known}
        if t.get("model") and t["model"] not in {m["name"] for _, m in p.models()}:
            report.fail(f"{t['id']} targets model '{t['model']}', which is not declared")
            ok = False
    missing = sorted(set(known) - verified, key=lambda x: int(x.split("-")[1]))
    report.check(not missing, f"every business scenario is verified by an acceptance test ({len(known)} AX, {len(tests)} AT)",
                 f"business scenario(s) with no acceptance test: {', '.join(missing)}")
    by_method: dict[str, int] = {}
    for t in tests:
        by_method[t["method"]] = by_method.get(t["method"], 0) + 1
    report.info("acceptance tests: " + ", ".join(f"{v} {k}" for k, v in sorted(by_method.items())))
    return ok and not missing


def render_dag_md(dag: dict) -> str:
    lines = [f"# Composed pipeline — {dag['product_id']}", "",
             "Generated by `dpf compose`. Each node is a skill selected for a stage instance; each edge is "
             "typed by the contract it carries.", "", "```mermaid", "flowchart LR"]
    ids = {}
    for i, n in enumerate(dag["nodes"]):
        if n["scope"] == "product" and n["stage"] in ("publish", "register", "monitor", "orchestrate", "render",
                                                      "assemble", "test", "govern"):
            label = f"{n['stage']}<br/>{n['skill']}"
        else:
            label = f"{n['instance']}<br/>{n['skill']}"
        ids[n["id"]] = f"n{i}"
        lines.append(f'  n{i}["{label}"]')
    for e in dag["edges"]:
        if e["from"] in ids and e["to"] in ids:
            lines.append(f"  {ids[e['from']]} -->|{e['contract']}| {ids[e['to']]}")
    lines += ["```", "", "| Stage | Instance | Skill | Tool (tier) | Consumes | Produces |", "|---|---|---|---|---|---|"]
    for n in dag["nodes"]:
        lines.append(f"| {n['stage']} | {n['instance']} | `{n['skill']}` | {n['tool']} ({n['tier']}) | "
                     f"{', '.join(n['consumes']) or '—'} | {', '.join(n['produces']) or '—'} |")
    if dag.get("design_skills"):
        lines += ["", "Design-time skills (run before the build, gated):", ""]
        lines += [f"- `{d['skill']}` ({d['stage']}{', gate ' + d['gate'] if d.get('gate') else ''})" for d in dag["design_skills"]]
    return "\n".join(lines) + "\n"


def dag_json(dag: dict) -> str:
    return json.dumps(dag, indent=2)
