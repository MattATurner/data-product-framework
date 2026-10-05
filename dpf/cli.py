"""`dpf` command line: one entry point for define, design, build, test and monitor.

Exit codes: 0 when every check passes, 1 when any check fails, 2 for usage errors.
Every command accepts `--json` (machine-readable report on stdout) and `--root`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dpf import __version__
from dpf.core import Report, Workspace, find_root

GATES = ["G0", "G1", "G2", "G3", "G4"]


def _products(ws: Workspace, args) -> list:
    if getattr(args, "all", False):
        return [ws.product(pid) for pid in ws.product_ids()]
    if not getattr(args, "product", None):
        raise SystemExit("name a product or pass --all")
    return [ws.product(args.product)]


# ----------------------------------------------------------------- commands
def cmd_validate(ws, args, report):
    from dpf.validate import validate
    validate(ws, report)


def cmd_lint(ws, args, report):
    from dpf.lint import lint
    lint(ws, report)


def cmd_brd_validate(ws, args, report):
    from dpf.brd import check_brd
    for p in _products(ws, args):
        check_brd(p, report, write_gaps=not args.no_write)


def cmd_tdd_stale(ws, args, report):
    from dpf.design import stale_reasons
    report.head("TDD currency", gate="G1")
    for pid in ws.product_ids():
        p = ws.product(pid)
        reasons = stale_reasons(p)
        if reasons:
            for r in reasons:
                report.fail(f"{pid}: {r}")
        else:
            report.ok(f"{pid}: TDD, manifest and sign-off are current with {p.brd.get('brd_id')}@{p.brd.get('version')}")


def cmd_tdd_resolve(ws, args, report):
    from dpf.design import resolution_report
    p = ws.product(args.product)
    text = resolution_report(p)
    if report.json_mode:
        report.info(text)
    else:
        print(text)


def cmd_signoff(ws, args, report):
    from dpf.design import write_signoff
    p = ws.product(args.product)
    report.head(f"sign-off — {p.id}", gate="G1")
    so = write_signoff(p, args.by, args.role, args.date, args.note)
    errs = ws.validate(so, "signoff.v1")
    report.check(not errs, f"signed {so['brd']} semantics by {args.by} ({args.role}); covers {', '.join(so['covers'])}; "
                           f"digest {so['semantic_digest'][:19]}…", f"signoff.yaml invalid: {'; '.join(errs[:3])}")


def cmd_compose(ws, args, report):
    from dpf.compose import check_acceptance, compose
    for p in _products(ws, args):
        compose(p, report, write=not args.no_write)
        check_acceptance(p, report)


def cmd_generate(ws, args, report):
    from dpf.generate import declared_engine, generate, golden_dir
    for p in _products(ws, args):
        engines = [args.engine] if args.engine else [None]
        if not args.engine and args.all:
            # Golden copies define which alternative engines are kept reproducible.
            engines += sorted(d.name.split("--", 1)[1] for d in (ws.root / "tests/golden").glob(f"{p.id}--*") if d.is_dir())
        for eng in engines:
            if eng == declared_engine(p):
                eng = None
            generate(p, report, engine=eng, check=args.check, update_golden=args.update_golden, write=not args.no_write)


def cmd_trace(ws, args, report):
    from dpf.trace import check_trace, render_markdown
    for p in _products(ws, args):
        m = check_trace(p, report, write=not args.no_write)
        if m and args.print and not report.json_mode:
            print(render_markdown(m))


def cmd_test(ws, args, report):
    from dpf.generate import build
    from dpf.testing import attest, plan_table, run_tests
    p = ws.product(args.product)
    if args.test_cmd == "plan":
        b = build(p)
        if report.json_mode:
            json.dump(b.spec, sys.stdout, indent=2)
            print()
            sys.exit(0 if b.ok else 1)
        print(plan_table(b))
        sys.exit(0 if b.ok else 1)
    if args.test_cmd == "run":
        run_tests(p, report, live=args.live, environment=args.env, only=args.only)
    elif args.test_cmd == "attest":
        attest(p, report, args.test, args.by, args.role, args.note, args.env)


def cmd_monitor(ws, args, report):
    from dpf.monitor import load, monitor
    p = ws.product(args.product)
    monitor(p, report, load(args.evidence) if args.evidence else None, open_change_on_breach=args.open_change)


def cmd_check(ws, args, report):
    from dpf.brd import check_brd
    from dpf.compose import check_acceptance, compose
    from dpf.design import check_design
    from dpf.generate import generate
    from dpf.lint import lint
    from dpf.testing import check_evidence
    from dpf.trace import check_trace
    from dpf.validate import validate

    upto = GATES.index(args.gate)
    products = _products(ws, args)  # an unknown product is a usage error before any check runs
    if upto >= 3:
        validate(ws, report)
        lint(ws, report)
    for p in products:
        check_brd(p, report, write_gaps=False)
        if upto >= 1:
            check_design(p, report)
        if upto >= 2:
            compose(p, report, write=False)
            check_acceptance(p, report)
        if upto >= 3:
            b = generate(p, report, check=True, write=False)
            check_trace(p, report, b)
        if upto >= 4:
            check_evidence(p, report, b)


def cmd_eval(ws, args, report):
    from dpf.evals import run_evals
    run_evals(ws, report, only=args.id)


def cmd_init(ws, args, report):
    from dpf.init import init
    init(ws, Path(args.target), report)


# ----------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print a machine-readable report")
    common.add_argument("--quiet", action="store_true", help="print failures and warnings only")
    common.add_argument("--root", help="workspace root (default: discovered from the current directory)")

    ap = argparse.ArgumentParser(prog="dpf", description="Data Product Framework: spec-driven data products "
                                 "through define (G0), design (G1), build (G2, G3), test (G4) and monitor.")
    ap.add_argument("--version", action="version", version=f"dpf {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def product_args(sp, all_ok=True):
        sp.add_argument("product", nargs="?", help="product id (products/<id>/product.yaml)")
        if all_ok:
            sp.add_argument("--all", action="store_true", help="every product in the workspace")

    sp = sub.add_parser("validate", parents=[common], help="validate the framework's own contracts, skills, packs and ADRs")
    sp.set_defaults(fn=cmd_validate)
    sp = sub.add_parser("lint", parents=[common], help="tool tiers, bespoke-code markers, ADR references, terminology")
    sp.set_defaults(fn=cmd_lint)

    brd = sub.add_parser("brd", help="business requirements (G0)")
    bsub = brd.add_subparsers(dest="brd_cmd", required=True)
    sp = bsub.add_parser("validate", parents=[common], help="G0: the BRD is complete, approved and free of modelling vocabulary")
    product_args(sp)
    sp.add_argument("--no-write", action="store_true", help="do not write the gap register")
    sp.set_defaults(fn=cmd_brd_validate)

    tdd = sub.add_parser("tdd", help="technical design (G1)")
    tsub = tdd.add_subparsers(dest="tdd_cmd", required=True)
    sp = tsub.add_parser("stale", parents=[common], help="list TDDs, manifests and sign-offs behind their BRD")
    sp.set_defaults(fn=cmd_tdd_stale)
    sp = tsub.add_parser("resolve", parents=[common], help="print how the BRD answers drive design decisions")
    product_args(sp, all_ok=False)
    sp.set_defaults(fn=cmd_tdd_resolve)

    sp = sub.add_parser("signoff", parents=[common], help="record the business owner's signature on semantics.md")
    product_args(sp, all_ok=False)
    sp.add_argument("--by", required=True, help="name of the person signing")
    sp.add_argument("--role", required=True, help="their role, e.g. business_owner")
    sp.add_argument("--date", help="YYYY-MM-DD (default: today)")
    sp.add_argument("--note")
    sp.set_defaults(fn=cmd_signoff)

    sp = sub.add_parser("compose", parents=[common], help="G2: select skills per stage and map scenarios to tests")
    product_args(sp)
    sp.add_argument("--no-write", action="store_true", help="do not write generated/<product>/dag.*")
    sp.set_defaults(fn=cmd_compose)

    sp = sub.add_parser("generate", parents=[common], help="G3: render every artefact into generated/<product>/")
    product_args(sp)
    sp.add_argument("--engine", help="render with another engine adapter (e.g. dbt) into generated/<product>--<engine>/")
    sp.add_argument("--check", action="store_true", help="compare with the golden copy in tests/golden/ and prove determinism")
    sp.add_argument("--update-golden", action="store_true", help="replace the golden copy with this build")
    sp.add_argument("--no-write", action="store_true", help="render in memory only")
    sp.set_defaults(fn=cmd_generate)

    sp = sub.add_parser("trace", parents=[common], help="requirement -> decision -> element -> artefact -> test -> evidence")
    product_args(sp)
    sp.add_argument("--no-write", action="store_true", help="do not write generated/<product>/trace.{json,md}")
    sp.add_argument("--print", action="store_true", help="print the matrix as markdown")
    sp.set_defaults(fn=cmd_trace)

    test = sub.add_parser("test", help="test plan, runs and attestations (G4 evidence)")
    tsub = test.add_subparsers(dest="test_cmd", required=True)
    sp = tsub.add_parser("plan", parents=[common], help="list every test case with what it satisfies")
    product_args(sp, all_ok=False)
    sp.set_defaults(fn=cmd_test)
    sp = tsub.add_parser("run", parents=[common], help="run static checks; with --live, run SQL cases and record evidence")
    product_args(sp, all_ok=False)
    sp.add_argument("--live", action="store_true", help="run automated cases against the deployed build (BigQuery)")
    sp.add_argument("--env", default="test", help="environment name recorded with the evidence")
    sp.add_argument("--only", nargs="*", help="case ids to run")
    sp.set_defaults(fn=cmd_test)
    sp = tsub.add_parser("attest", parents=[common], help="record a human attestation for an acceptance test")
    product_args(sp, all_ok=False)
    sp.add_argument("test", help="acceptance test id, e.g. AT-5")
    sp.add_argument("--by", required=True)
    sp.add_argument("--role", required=True, help="must match attested_by_role in acceptance.yaml")
    sp.add_argument("--note")
    sp.add_argument("--env", default="test")
    sp.set_defaults(fn=cmd_test)

    sp = sub.add_parser("monitor", parents=[common], help="evaluate run evidence against the observability policy")
    product_args(sp, all_ok=False)
    sp.add_argument("--evidence", help="run-evidence.v1 JSON file (default: observe the deployed product)")
    sp.add_argument("--open-change", action="store_true", help="on a breach, open an OpenSpec change under openspec/changes/")
    sp.set_defaults(fn=cmd_monitor)

    sp = sub.add_parser("check", parents=[common], help="run every gate up to --gate (cumulative)")
    product_args(sp)
    sp.add_argument("--gate", choices=GATES, default="G3", help="highest gate to check (default G3)")
    sp.set_defaults(fn=cmd_check)

    sp = sub.add_parser("eval", parents=[common], help="run the behavioural evals in tests/evals/")
    sp.add_argument("--id", nargs="*", help="eval ids to run (default: all)")
    sp.set_defaults(fn=cmd_eval)

    sp = sub.add_parser("init", parents=[common], help="scaffold a clean workspace with the framework and no example material")
    sp.add_argument("target")
    sp.set_defaults(fn=cmd_init)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    ws = Workspace(Path(args.root).resolve() if args.root else find_root())
    report = Report(json_mode=args.json, quiet=args.quiet)
    try:
        args.fn(ws, args, report)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise
    return report.finish()


if __name__ == "__main__":
    raise SystemExit(main())
