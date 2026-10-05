"""G3 — generate every artefact from the manifest (`dpf generate`).

One pipeline for every engine: compose (skills per stage) -> product graph -> test
specification -> engine-neutral render plan -> engine adapter + Terraform + documents.
Output is deterministic: the same inputs give byte-identical files, which `--check`
compares against the golden copy in tests/golden/ and `MANIFEST.json` binds to the build
digest that test evidence must match.
"""

from __future__ import annotations

import copy
import io
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dpf import __version__
from dpf.core import Product, Report, sha256, write_text
from dpf.compose import compose, render_dag_md
from dpf.graph import ProductGraph
from dpf.generate import dataform, dbt, docs, terraform
from dpf.generate.plan import Action, build_plan
from dpf.generate.render import undefined_vars
from dpf.generate.testspec import build_test_spec

RENDERERS = {"dataform": dataform.render, "dbt": dbt.render}


@dataclass
class Build:
    product: Product
    engine: str | None = None
    ok: bool = True
    problems: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    spec: dict = field(default_factory=dict)
    dag: dict = field(default_factory=dict)
    digest: str = ""
    graph: ProductGraph | None = None

    @property
    def name(self) -> str:
        p = self.product
        return p.id if not self.engine or self.engine == declared_engine(p) else f"{p.id}--{self.engine}"


def declared_engine(p: Product) -> str | None:
    engines = {p.layer_cfg(layer).get("engine") for layer in ("staging", "silver", "gold") if p.layer_cfg(layer).get("models")}
    return engines.pop() if len(engines) == 1 else None


def retarget(p: Product, engine: str) -> Product:
    """The same product with every layer (and orchestration) rendered by another engine."""
    man = copy.deepcopy(p.manifest)
    for layer in ("staging", "silver", "gold"):
        if (man.get("layers") or {}).get(layer):
            man["layers"][layer]["engine"] = engine
    if man.get("orchestration"):
        man["orchestration"]["engine"] = engine
    q = Product(p.ws, p.id, p.path)
    q.__dict__["manifest"] = man
    return q


def skill_map(dag: dict) -> dict[str, str]:
    out = {}
    for n in dag.get("nodes", []):
        if n["scope"] == "model":
            out[n["instance"]] = n["skill"]
        elif n["scope"] == "source":
            out[f"{n['stage']}:{n['instance']}"] = n["skill"]
        else:
            out.setdefault(f"{n['stage']}:product", n["skill"])
    return out


def build(p: Product, engine: str | None = None) -> Build:
    """Render the whole build in memory. Never writes."""
    b = Build(product=p, engine=engine)
    q = retarget(p, engine) if engine and engine != declared_engine(p) else p
    r = Report(quiet=True, stream=io.StringIO())
    ok, dag = compose(q, r, write=False)
    b.dag = dag
    if not ok:
        b.ok = False
        b.problems += [f"compose: {m}" for m in r.messages(Report.FAIL)]
        return b
    eng = declared_engine(q)
    if eng is None:
        b.ok = False
        b.problems.append("models use more than one engine; the generators render one engine per product")
        return b
    if eng not in RENDERERS:
        b.ok = False
        b.problems.append(f"no renderer for engine '{eng}'")
        return b
    g = ProductGraph(q)
    b.graph = g
    b.digest = q.build_digest(engine if engine and engine != declared_engine(p) else None)
    b.spec = build_test_spec(q, g, b.digest)
    b.actions = build_plan(q, g, b.spec, skill_map(dag))
    missing = undefined_vars(q, g, [a.sql for a in b.actions])
    if missing:
        b.ok = False
        b.problems.append(f"bodies use undefined vars: {', '.join(missing)}")
    files: dict[str, str] = {}
    files.update(RENDERERS[eng](q, g, b.actions))
    files.update(terraform.render(q, g, b.actions, eng))
    files["test-spec.json"] = docs.dumps(b.spec)
    files["dag.json"] = docs.dumps(dag)
    files["dag.md"] = render_dag_md(dag)
    files["data-product.json"] = docs.dumps(docs.data_product(q))
    files["catalog-registration.json"] = docs.dumps(docs.catalog_registration(q, g))
    files["observability-policy.json"] = docs.dumps(docs.observability_policy(q))
    files["quality-policy.json"] = docs.dumps(docs.quality_policy(q, g))
    for n in g.models:
        if n.layer == "staging":
            files[f"staging/{n.name}.json"] = docs.dumps(docs.staging_model(q, g, n.name))
        else:
            files[f"semantic/{n.name}.json"] = docs.dumps(docs.semantic_model(q, g, n.name))
    for n in g.raw:
        files[f"raw/{n.name}.json"] = docs.dumps(docs.raw_table(q, g, n.name))
    files["README.md"] = docs.readme(q, eng, b.actions, sorted(files), b.digest)
    files = dict(sorted(files.items()))
    files["MANIFEST.json"] = docs.dumps({
        "product_id": p.id, "engine": eng, "dpf_version": __version__, "build_digest": b.digest,
        "files": {path: sha256(content) for path, content in files.items()}})
    b.files = files
    b.problems += validate_documents(p, files)
    b.ok = b.ok and not b.problems
    return b


CONTRACT_OF = {
    "test-spec.json": "test-spec.v1", "data-product.json": "data-product.v1",
    "catalog-registration.json": "catalog-registration.v1", "observability-policy.json": "observability-policy.v1",
    "quality-policy.json": "quality-policy.v1",
}


def validate_documents(p: Product, files: dict[str, str]) -> list[str]:
    problems = []
    for path, content in files.items():
        contract = CONTRACT_OF.get(path) or {"semantic": "semantic-model.v1", "staging": "staging-model.v1",
                                             "raw": "raw-table.v1"}.get(path.split("/")[0]) if path.endswith(".json") else None
        if not contract:
            continue
        errs = p.ws.validate(json.loads(content), contract)
        problems += [f"{path} does not conform to {contract}: {e}" for e in errs[:3]]
    return problems


def golden_dir(b: Build) -> Path:
    return b.product.ws.root / "tests" / "golden" / b.name


def out_dir(b: Build) -> Path:
    return b.product.ws.root / "generated" / b.name


def diff_tree(files: dict[str, str], root: Path) -> list[str]:
    diffs = []
    existing = {str(f.relative_to(root)) for f in root.rglob("*") if f.is_file()} if root.exists() else set()
    for path, content in files.items():
        f = root / path
        if path not in existing:
            diffs.append(f"missing {path}")
        elif f.read_text(encoding="utf-8") != content:
            diffs.append(f"differs {path}")
    diffs += [f"unexpected {x}" for x in sorted(existing - set(files))]
    return diffs


def write_tree(files: dict[str, str], root: Path, clean: bool) -> None:
    if clean and root.exists():
        old = root / "MANIFEST.json"
        previous = json.loads(old.read_text(encoding="utf-8")).get("files", {}) if old.exists() else {}
        for path in set(previous) | {"MANIFEST.json"}:
            if path not in files and (root / path).exists():
                (root / path).unlink()
    for path, content in files.items():
        write_text(root / path, content)


def generate(p: Product, report: Report, engine: str | None = None, check: bool = False,
             update_golden: bool = False, write: bool = True) -> Build:
    b = build(p, engine)
    report.head(f"G3 · generate artefacts — {b.name}", gate="G3")
    for prob in b.problems:
        report.fail(prob)
    if not b.files:
        return b
    report.ok(f"rendered {len(b.files)} files ({sum(1 for a in b.actions if a.kind == 'assertion')} assertions, "
              f"{len(b.spec.get('cases', []))} test cases); build digest {b.digest[:19]}…")
    if write:
        write_tree(b.files, out_dir(b), clean=True)
        report.info(f"wrote {out_dir(b).relative_to(p.ws.root)}/")
    if update_golden:
        gd = golden_dir(b)
        if gd.exists():
            shutil.rmtree(gd)
        write_tree(b.files, gd, clean=False)
        report.info(f"updated golden copy {gd.relative_to(p.ws.root)}/")
    if check:
        gd = golden_dir(b)
        if not gd.exists():
            report.fail(f"no golden copy at {gd.relative_to(p.ws.root)}/ (run `dpf generate {p.id}"
                        f"{' --engine ' + engine if engine else ''} --update-golden`)")
        else:
            diffs = diff_tree(b.files, gd)
            again = build(p, engine)
            stable = again.files == b.files
            report.check(stable, "generation is deterministic (two runs are byte-identical)",
                         "generation is not deterministic: two runs differ")
            report.check(not diffs, f"matches golden copy {gd.relative_to(p.ws.root)}/ ({len(b.files)} files)",
                         f"differs from golden copy: {'; '.join(diffs[:6])}"
                         + (f" (+{len(diffs) - 6} more)" if len(diffs) > 6 else ""))
    return b
