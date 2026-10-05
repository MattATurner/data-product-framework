"""Behavioural evals (`dpf eval`): each eval mutates a copy of the workspace and asserts the verdict.

tests/evals/<id>/eval.yaml:

    id: grain-violation
    asserts: The TDD grain and the manifest grain must agree, or G1 fails.
    mutate:                                   # applied in order to a temporary copy
      - set: {file: products/x/product.yaml, path: "layers.silver.models[name=fct].grain_columns", value: [a]}
      - replace: {file: <path>, old: "text", new: "text"}
      - delete: {file: <path>, path: "a.b[0]"}
      - append: {file: <path>, text: "..."}
      - write: {file: <path>, text: "..."}
      - remove: {file: <path>}
    run: {command: check, product: sales_performance, gate: G1}
         # or lint | validate | compose | generate (check/engine) | trace | monitor (evidence, open_change)
    expect:
      outcome: fail                           # fail: at least one failure; pass: none
      messages: ["substring of a FAIL line"]  # each must appear in a failure (or `level: warn`)
      absent: ["substring that must not appear in any failure"]
      files: ["openspec/changes/monitor-*/proposal.md"]   # globs that must exist afterwards
      dag_node: {id: "extract:ora_local", skill: extract-rdbms-watermark}

Evals run on every change to skills, packs, generators or the model behind an agent: they
are the regression suite for the framework's judgement, not just its code.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from dpf.core import Report, Workspace, load_yaml

COPY = ["contracts", "registry", "methodologies", "engines", "skills", "openspec", "products", "adr",
        "examples", "tests/golden", "evidence"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "out", "node_modules")
TOKEN = re.compile(r"^([^\[\]]+)(?:\[([^\]]+)\])?$")


def _walk(doc, path: str, create: bool = False):
    """Return (container, key) for the last segment of a dotted path with [i] / [k=v] selectors."""
    parts = path.split(".")
    cur = doc
    for i, part in enumerate(parts):
        m = TOKEN.match(part)
        if not m:
            raise ValueError(f"bad path segment '{part}'")
        key, sel = m.groups()
        last = i == len(parts) - 1
        if sel is None:
            if last:
                return cur, key
            if key not in cur and create:
                cur[key] = {}
            cur = cur[key]
            continue
        seq = cur[key]
        if "=" in sel:
            k, v = sel.split("=", 1)
            idx = next((j for j, x in enumerate(seq) if str(x.get(k)) == v), None)
            if idx is None:
                raise KeyError(f"no element with {k}={v} under {key}")
        else:
            idx = int(sel)
        if last:
            return seq, idx
        cur = seq[idx]
    raise ValueError(path)


def apply_mutation(root: Path, m: dict) -> None:
    (op, arg), = m.items()
    f = root / arg["file"]
    if op in ("set", "delete"):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        cont, key = _walk(doc, arg["path"], create=(op == "set"))
        if op == "set":
            cont[key] = arg["value"]
        else:
            del cont[key]
        f.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    elif op == "replace":
        text = f.read_text(encoding="utf-8")
        if arg["old"] not in text:
            raise ValueError(f"replace: text not found in {arg['file']}: {arg['old'][:60]!r}")
        f.write_text(text.replace(arg["old"], arg["new"], arg.get("count", -1)), encoding="utf-8")
    elif op == "append":
        f.write_text(f.read_text(encoding="utf-8") + arg["text"], encoding="utf-8")
    elif op == "write":
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(arg["text"], encoding="utf-8")
    elif op == "remove":
        f.unlink()
    else:
        raise ValueError(f"unknown mutation '{op}'")


def _execute(ws: Workspace, run: dict, eval_dir: Path) -> tuple[Report, dict]:
    from dpf.brd import check_brd
    from dpf.compose import check_acceptance, compose
    from dpf.design import check_design
    from dpf.generate import generate
    from dpf.lint import lint
    from dpf.monitor import load, monitor
    from dpf.testing import check_evidence
    from dpf.trace import check_trace
    from dpf.validate import validate

    r = Report(quiet=True, stream=io.StringIO())
    extra: dict = {}
    cmd = run["command"]
    p = ws.product(run["product"]) if run.get("product") else None
    if cmd == "check":
        gates = ["G0", "G1", "G2", "G3", "G4"]
        upto = gates.index(run.get("gate", "G3"))
        check_brd(p, r, write_gaps=False)
        if upto >= 1:
            check_design(p, r)
        if upto >= 2:
            compose(p, r, write=False)
            check_acceptance(p, r)
        if upto >= 3:
            b = generate(p, r, check=True, write=False)
            check_trace(p, r, b)
        if upto >= 4:
            check_evidence(p, r, b)
    elif cmd == "brd":
        check_brd(p, r, write_gaps=True)
    elif cmd == "lint":
        lint(ws, r)
    elif cmd == "validate":
        validate(ws, r)
    elif cmd == "compose":
        ok, dag = compose(p, r, write=False)
        extra["dag"] = dag
        if run.get("acceptance", True):
            check_acceptance(p, r)
    elif cmd == "generate":
        generate(p, r, engine=run.get("engine"), check=run.get("check", True), write=False)
    elif cmd == "trace":
        check_trace(p, r)
    elif cmd == "monitor":
        monitor(p, r, load(str(eval_dir / run["evidence"])), open_change_on_breach=run.get("open_change", False))
    else:
        raise ValueError(f"unknown command '{cmd}'")
    return r, extra


def run_eval(ws: Workspace, eval_dir: Path) -> tuple[bool, list[str], dict]:
    spec = load_yaml(eval_dir / "eval.yaml")
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix=f"dpf-eval-{spec['id']}-") as tmp:
        root = Path(tmp)
        for rel in COPY:
            src = ws.root / rel
            if src.is_dir():
                shutil.copytree(src, root / rel, ignore=IGNORE)
            elif src.exists():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, root / rel)
        for m in spec.get("mutate", []) or []:
            apply_mutation(root, m)
        twin = Workspace(root)
        r, extra = _execute(twin, spec["run"], eval_dir)
        exp = spec.get("expect") or {}
        level = exp.get("level", "fail")
        lines = r.messages(level)
        failures = r.messages("fail")
        outcome = "fail" if failures else "pass"
        if exp.get("outcome") and exp["outcome"] != outcome:
            problems.append(f"expected outcome {exp['outcome']}, got {outcome}"
                            + (f" ({failures[0][:140]})" if failures else ""))
        for s in exp.get("messages", []) or []:
            if not any(s in line for line in lines):
                problems.append(f"no {level} message contains {s!r}")
        for s in exp.get("absent", []) or []:
            if any(s in line for line in failures):
                problems.append(f"a failure unexpectedly contains {s!r}")
        for g in exp.get("files", []) or []:
            if not list(root.glob(g)):
                problems.append(f"no file matches {g}")
        node = exp.get("dag_node")
        if node:
            found = next((n for n in (extra.get("dag") or {}).get("nodes", []) if n["id"] == node["id"]), None)
            if found is None:
                problems.append(f"no DAG node {node['id']}")
            elif node.get("skill") and found["skill"] != node["skill"]:
                problems.append(f"DAG node {node['id']} uses {found['skill']}, expected {node['skill']}")
        return not problems, problems, {"id": spec["id"], "asserts": spec.get("asserts", ""), "failures": failures}


def run_evals(ws: Workspace, report: Report, only: list[str] | None = None) -> int:
    report.head("evals", gate="eval")
    dirs = sorted(d.parent for d in (ws.root / "tests/evals").glob("*/eval.yaml"))
    if only:
        missing = sorted(set(only) - {d.name for d in dirs})
        if missing:
            report.fail(f"no eval with id {', '.join(missing)} under tests/evals/")
            return 1
        dirs = [d for d in dirs if d.name in only]
    if not dirs:
        # A workspace fresh from `dpf init` has no product for an eval to mutate yet.
        report.warn("no evals under tests/evals/ yet: add them once the first product passes G3")
        return 0
    for d in dirs:
        try:
            ok, problems, info = run_eval(ws, d)
        except Exception as exc:  # noqa: BLE001 - an eval that cannot run is a failure
            report.fail(f"{d.name}: could not run: {type(exc).__name__}: {exc}")
            continue
        report.check(ok, f"{d.name}: {info['asserts'].strip().splitlines()[0] if info['asserts'] else 'passed'}",
                     f"{d.name}: {'; '.join(problems)}")
    return report.failures
