"""`dpf` command line: one entry point for describe, design, build, accept and monitor.

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
GATE_ALIASES = {
    "proto": "proto", "prototype": "proto",
    "G0": "G0", "describe": "G0", "define": "G0",
    "G1": "G1", "design": "G1",
    "G2": "G2", "compose": "G2",
    "G3": "G3", "build": "G3",
    "G4": "G4", "accept": "G4", "test": "G4",
}


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
    so = write_signoff(p, args.by, args.role, args.date, args.note, args.link)
    errs = ws.validate(so, "signoff.v1")
    report.check(not errs, f"signed {so['brd']} semantics by {args.by} ({args.role}); covers {', '.join(so['covers'])}; "
                           f"digest {so['semantic_digest'][:19]}…", f"signoff.yaml invalid: {'; '.join(errs[:3])}")


def cmd_compose(ws, args, report):
    from dpf.compose import check_acceptance, compose
    for p in _products(ws, args):
        compose(p, report, write=not args.no_write)
        check_acceptance(p, report)


def cmd_generate(ws, args, report):
    from dpf.generate import RENDERERS, declared_engine, generate
    for p in _products(ws, args):
        engines = [args.engine] if args.engine else [None]
        if not args.engine and args.all and not args.env:
            # Golden copies define which alternative engines are kept reproducible.
            engines += sorted(
                suffix for d in (ws.root / "tests/golden").glob(f"{p.id}--*")
                if d.is_dir() and (suffix := d.name.split("--", 1)[1]) in RENDERERS
            )
        for eng in engines:
            if eng == declared_engine(p):
                eng = None
            generate(p, report, engine=eng, check=args.check, update_golden=args.update_golden,
                     write=not args.no_write, env=args.env, semantic_targets=args.semantic_layer)


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
        attest(p, report, args.test, args.by, args.role, args.note, args.env, args.link)


def cmd_monitor(ws, args, report):
    from dpf.monitor import load, monitor
    p = ws.product(args.product)
    monitor(p, report, load(args.evidence) if args.evidence else None, open_change_on_breach=args.open_change)


def cmd_check(ws, args, report):
    from dpf.brd import check_brd
    from dpf.compose import check_acceptance, compose
    from dpf.design import check_design, check_prototype
    from dpf.generate import generate
    from dpf.lint import lint
    from dpf.testing import check_evidence
    from dpf.trace import check_trace
    from dpf.validate import validate

    resolved = GATE_ALIASES[args.gate]
    products = _products(ws, args)  # an unknown product is a usage error before any check runs
    if resolved == "proto":
        for p in products:
            check_prototype(p, report)
        return
    upto = GATES.index(resolved)
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


def cmd_proto(ws, args, report):
    import yaml
    from dpf.core import load_yaml, write_text

    if not getattr(args, "product", None):
        raise SystemExit("name a product")
    pid = args.product
    pdir = ws.root / "products" / pid
    if args.proto_cmd == "init":
        report.head(f"proto · init — {pid}", gate="proto")
        if (pdir / "product.yaml").exists():
            report.fail(f"products/{pid}/product.yaml already exists")
            return
        sys_id = args.source or "erp_orders"
        entity = args.entity or "orders"
        man = {
            "product_id": pid,
            "version": "0.1.0",
            "status": "prototype",
            "owner": f"{pid}-owner@example.com",
            "domain": args.domain or "commerce",
            "classification": "INTERNAL",
            "deployment": {
                "gcp_project": args.project or "example-dpf-dev",
                "region": "europe-west2",
                "datasets": {
                    "raw": f"{pid}_raw",
                    "staging": f"{pid}_staging",
                    "gold": f"{pid}_gold",
                    "assertions": f"{pid}_assertions",
                    "control": f"{pid}_control",
                },
            },
            "sources": [{
                "system_id": sys_id,
                "engine": "postgres",
                "capture_mode": "watermark",
                "watermark_column": "updated_at",
                "schedule": "0 * * * *",
                "entities": [entity],
            }],
            "layers": {
                "raw": {"storage": "bigquery_native"},
                "staging": {
                    "methodology": None,
                    "engine": "dataform",
                    "storage": "bigquery_native",
                    "models": [{
                        "name": f"stg_{entity}",
                        "role": "staging",
                        "grain_statement": f"One row per {entity} natural key",
                        "grain_columns": ["id"],
                        "natural_key": ["id"],
                        "dedupe_order": ["source_modified_ts DESC", "_ingest_ts DESC"],
                        "history_semantics": "current_only",
                        "materialisation": "view",
                        "body": f"sql/stg_{entity}.sql",
                    }],
                },
                "gold": {
                    "methodology": "direct",
                    "engine": "dataform",
                    "storage": "bigquery_native",
                    "models": [{
                        "name": f"obt_{pid}",
                        "role": "business_view",
                        "grain_statement": f"One row per {entity} record in {pid}",
                        "grain_columns": ["id"],
                        "history_semantics": "current_only",
                        "materialisation": "view",
                        "body": f"sql/obt_{pid}.sql",
                    }],
                },
            },
            "output_ports": [{
                "name": f"{pid}_port",
                "model": f"obt_{pid}",
                "type": "bigquery_view",
                "access": "dataset_grant",
            }],
            "quality": {"gate_behaviour": "warn", "rules": []},
            "orchestration": {
                "engine": "dataform",
                "timezone": "UTC",
                "schedules": [{"id": "hourly", "cron": "15 * * * *"}],
            },
        }
        write_text(pdir / "product.yaml", yaml.safe_dump(man, sort_keys=False))
        write_text(pdir / "sql" / f"stg_{entity}.sql",
                   f"SELECT\n  id,\n  updated_at AS source_modified_ts,\n  _ingest_ts\nFROM {{{{ ref('raw_{entity}') }}}}\n")
        write_text(pdir / "sql" / f"obt_{pid}.sql",
                   f"SELECT\n  id,\n  source_modified_ts\nFROM {{{{ ref('stg_{entity}') }}}}\n")
        report.ok(f"scaffolded prototype products/{pid}/product.yaml (run `dpf check {pid} --gate proto` and `dpf generate {pid}`)")
    elif args.proto_cmd == "import-dataform":
        from dpf.dataform_import import import_dataform
        import_dataform(
            ws,
            pid,
            Path(args.src),
            report,
            domain=args.domain,
            project=args.project,
            region=args.region,
            source_id=args.source,
        )
    elif args.proto_cmd == "import-looker":
        from dpf.looker_import import import_looker
        import_looker(
            ws,
            pid,
            Path(args.src),
            report,
            domain=args.domain,
            project=args.project,
            region=args.region,
            dataset=args.dataset,
        )
    elif args.proto_cmd == "promote":
        report.head(f"proto · promote — {pid}", gate="proto")
        mpath = pdir / "product.yaml"
        if not mpath.exists():
            report.fail(f"products/{pid}/product.yaml does not exist")
            return
        man = load_yaml(mpath)
        slug = pid.replace("_", "-")
        domain = man.get("domain", "commerce")
        brd_rel = f"products/{domain}/{slug}/brd"
        tdd_rel = f"products/{domain}/{slug}/tdd"
        man["status"] = "draft"
        man.setdefault("brd_id", f"BRD-{slug.upper()}-001")
        man.setdefault("tdd_id", f"TDD-{slug.upper()}-001")
        man.setdefault("satisfies", f"{man['brd_id']}@1.0.0")
        man.setdefault("specs", {"brd": brd_rel, "tdd": tdd_rel})
        first_model = f"obt_{pid}"
        if man.get("upstream") and not man.get("layers"):
            up0 = (man.get("upstream") or [{}])[0]
            first_model = (up0.get("models") or [t.get("name") for t in (up0.get("tables") or [])] or [first_model])[0]
        obs_default = {
            "freshness": [{"id": "OB-1", "model": first_model, "max_staleness": "PT24H"}],
            "alerting": {"notification_channel_var": "alert_channel"},
            "slo": {"objective": 0.99, "window": "P28D"},
        }
        if man.get("sources"):
            obs_default["schema_drift"] = {"on_additive": "land_and_record", "on_breaking": "quarantine_and_alert"}
        man.setdefault("observability", obs_default)
        man.setdefault("governance", {"register": "knowledge_catalog", "registered_via": "knowledge-catalog-mcp"})
        write_text(mpath, yaml.safe_dump(man, sort_keys=False))
        brd_dir = ws.root / "openspec/specs" / brd_rel
        tdd_dir = ws.root / "openspec/specs" / tdd_rel
        if not (brd_dir / "spec.md").exists():
            write_text(brd_dir / "spec.md", f"# {pid} — Business Requirements\n\n## Purpose\n\n**BRD:** {man['brd_id']} · **Version:** 1.0.0\n\n## Requirements\n\n### Requirement: Core output\n**ID:** R-1\n\nThe product SHALL provide {pid} records for business reporting.\n\n#### Scenario: Records are available\n**ID:** AX-1\n- **WHEN** the dataset is refreshed\n- **THEN** each record SHALL appear once\n")
        if not (brd_dir / "brd.yaml").exists():
            brd_doc = {
                "brd_id": man["brd_id"],
                "product_id": pid,
                "status": "draft",
                "version": "1.0.0",
                "business_owner": man.get("owner", f"{pid}-owner@example.com"),
                "data_steward": man.get("steward", "data-analytics"),
                "domain": domain,
                "sensitivity": man.get("classification", "INTERNAL"),
                "residency": "[NEEDS-DECISION: residency]",
                "business_questions": [{"id": "BQ-1", "text": "[NEEDS-DECISION: BQ-1]", "decision_supported": "[NEEDS-DECISION]", "consumers": [man.get("owner", "analytics")]}],
                "required_outputs": [{"id": "OUT-1", "type": "dataset", "figures": ["record count"], "attributes": ["id"], "slices": ["id"], "satisfies": ["R-1"]}],
                "level_of_detail": {"drill_to": "a single record", "distinct_by": "each record appears once", "satisfies": ["R-1"]},
                "history_behaviour": [{"id": "HB-1", "attribute": "record details", "question": "If details change, should past records show old or current values?", "answer": "Current values are fine.", "satisfies": ["R-1"]}],
                "totalling": {"can_be_summed_across": ["days"], "satisfies": ["R-1"]},
                "timeliness": {"freshness_need": "daily", "justification": "[NEEDS-DECISION: timeliness]", "expected_users": "analytics team", "satisfies": ["R-1"]},
                "exceptions": [],
                "fitness": {"unusable_row": "[NEEDS-DECISION: fitness]", "on_bad_data": "quarantine and warn", "satisfies": ["R-1"]},
                "sources_believed": [{"system": (man.get("sources") or [{}])[0].get("system_id", "source"), "holds": ", ".join((man.get("sources") or [{}])[0].get("entities") or ["records"]), "authority": "system of record"}],
                "protection": {"who_may_access": [man.get("owner", "analytics")], "satisfies": ["R-1"]},
                "external_readers": {"required": False, "access": "internal only", "satisfies": ["R-1"]},
                "non_goals": ["[NEEDS-DECISION: non_goals]"],
                "open_questions": [],
            }
            write_text(brd_dir / "brd.yaml", yaml.safe_dump(brd_doc, sort_keys=False))
        if not (tdd_dir / "spec.md").exists():
            tdd_tmpl = ws.templates_dir / "design/tdd-spec.md"
            tdd_txt = (tdd_tmpl.read_text(encoding="utf-8")
                       .replace("{Product name}", pid)
                       .replace("{product name}", pid)
                       .replace("{product_id}", pid)
                       .replace("{product}", pid)
                       .replace("{DOMAIN}", domain.upper())
                       .replace("{domain}", domain)) if tdd_tmpl.exists() else f"# {pid} — Technical Design\n\n## Purpose\n\n**TDD:** {man['tdd_id']} · **Satisfies:** {man['satisfies']}\n"
            write_text(tdd_dir / "spec.md", tdd_txt)
        if not (tdd_dir / "playback.md").exists():
            sem_tmpl = ws.templates_dir / "design/semantics.md"
            pb_txt = (sem_tmpl.read_text(encoding="utf-8")
                      .replace("{Product name}", pid)
                      .replace("{product}", pid)
                      .replace("{DOMAIN}", domain.upper())
                      .replace("{domain}", domain)) if sem_tmpl.exists() else f"# Business playback — {pid}\n\nPlain-language playback of {pid} for business owner sign-off.\n"
            write_text(tdd_dir / "playback.md", pb_txt)
        report.ok(f"promoted {pid} to status: draft and scaffolded {brd_rel} and {tdd_rel} (with playback.md)")


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
    sp.add_argument("--link", action="append", help="link to an approval email, wiki page or ticket (repeatable)")
    sp.set_defaults(fn=cmd_signoff)

    sp = sub.add_parser("compose", parents=[common], help="G2: select skills per stage and map scenarios to tests")
    product_args(sp)
    sp.add_argument("--no-write", action="store_true", help="do not write generated/<product>/dag.*")
    sp.set_defaults(fn=cmd_compose)

    sp = sub.add_parser("generate", parents=[common], help="G3: render every artefact into generated/<product>/")
    product_args(sp)
    sp.add_argument("--engine", help="render with another engine adapter (e.g. dbt) into generated/<product>--<engine>/")
    sp.add_argument("--env", help="render with environment overrides from deployment.environments.<env>")
    sp.add_argument("--semantic-layer", nargs="*", choices=["cube", "metricflow", "atscale", "osi", "lookml"],
                    help="override semantic layer targets (cube, metricflow, atscale, osi, lookml)")
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
    sp.add_argument("--link", action="append", help="link to supporting evidence, email or wiki page (repeatable)")
    sp.add_argument("--env", default="test")
    sp.set_defaults(fn=cmd_test)

    sp = sub.add_parser("monitor", parents=[common], help="evaluate run evidence against the observability policy")
    product_args(sp, all_ok=False)
    sp.add_argument("--evidence", help="run-evidence.v1 JSON file (default: observe the deployed product)")
    sp.add_argument("--open-change", action="store_true", help="on a breach, open an OpenSpec change under openspec/changes/")
    sp.set_defaults(fn=cmd_monitor)

    sp = sub.add_parser("check", parents=[common], help="run every gate up to --gate (cumulative)")
    product_args(sp)
    sp.add_argument("--gate", choices=list(GATE_ALIASES), default="G3",
                    help="highest gate to check: proto/prototype, G0/describe/define, G1/design, G2/compose, G3/build (default), G4/accept/test")
    sp.set_defaults(fn=cmd_check)

    proto = sub.add_parser("proto", help="fast prototyping cheat code (status: prototype)")
    psub = proto.add_subparsers(dest="proto_cmd", required=True)
    sp = psub.add_parser("init", parents=[common], help="scaffold a minimal status: prototype product without BRD/TDD")
    product_args(sp, all_ok=False)
    sp.add_argument("--source", help="source system_id (default: erp_orders)")
    sp.add_argument("--entity", help="source entity name (default: orders)")
    sp.add_argument("--domain", help="domain name (default: commerce)")
    sp.add_argument("--project", help="GCP project id (default: example-dpf-dev)")
    sp.set_defaults(fn=cmd_proto)
    sp = psub.add_parser("import-dataform", parents=[common],
                         help="import a Dataform / Data Engineering Agent workspace into status: prototype")
    product_args(sp, all_ok=False)
    sp.add_argument("--from", dest="src", required=True, help="path to Dataform repository or definitions/ directory")
    sp.add_argument("--source", help="source system_id (default: <product>_src)")
    sp.add_argument("--domain", help="domain name (default: commerce)")
    sp.add_argument("--project", help="GCP project id (overrides workflow_settings.yaml)")
    sp.add_argument("--region", help="GCP region (overrides workflow_settings.yaml)")
    sp.set_defaults(fn=cmd_proto)
    sp = psub.add_parser("import-looker", parents=[common],
                         help="import an existing LookML directory (views, explores, dashboards) into status: prototype")
    product_args(sp, all_ok=False)
    sp.add_argument("--from", dest="src", required=True, help="path to LookML project directory")
    sp.add_argument("--domain", help="domain name (default: analytics)")
    sp.add_argument("--project", help="GCP project id (overrides manifest.lkml / sql_table_name)")
    sp.add_argument("--dataset", help="default BigQuery dataset when sql_table_name is unqualified")
    sp.add_argument("--region", help="GCP region (default: europe-west2)")
    sp.set_defaults(fn=cmd_proto)
    sp = psub.add_parser("promote", parents=[common], help="promote a prototype product to status: draft and scaffold BRD/TDD")
    product_args(sp, all_ok=False)
    sp.set_defaults(fn=cmd_proto)

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
