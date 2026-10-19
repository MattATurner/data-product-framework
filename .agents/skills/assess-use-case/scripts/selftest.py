#!/usr/bin/env python3
"""Self-test for assess-use-case: the fixtures and a PDF round trip.

Run it after changing templates/src/use-case.form.yaml, templates/scoring.yaml,
registry/brd-vocabulary.yaml or this skill:

  python3 .agents/skills/assess-use-case/scripts/selftest.py [--root DIR]

For each case in fixtures/expected.yaml it checks the provisional verdict and the mechanical
findings. Then it fills the blank 1-use-case.pdf with the worked example's answers, reads the
PDF back and requires the PDF and YAML readers to agree. Cases that need pypdf are skipped,
with a note, when it is not installed (pip install --require-hashes -r requirements/templates.txt).
The judgement findings in expected.yaml are for agent evals and are not checked here.
Exit code 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_use_case as cu  # noqa: E402

FIXTURES = cu.SKILL / "fixtures"


def have_pypdf() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def resolve(p: str, root: Path) -> Path:
    return Path(p.replace("{skill}", str(cu.SKILL))) if "{skill}" in p else root / p


def run_case(case: dict, root: Path) -> list[str]:
    errors = []
    r = cu.assess(resolve(case["input"], root), root)
    exp = case["mechanical"]
    if r["provisional_verdict"] != exp["verdict"]:
        errors.append(f"verdict {r['provisional_verdict']!r}, expected {exp['verdict']!r}")
    if "findings" in exp:
        got = {(f["check"], f["field"], f["severity"]) for f in r["findings"]}
        want = {(f["check"], f["field"], f["severity"]) for f in exp["findings"]}
        for m in sorted(want - got):
            errors.append(f"missing finding {m}")
        for x in sorted(got - want):
            errors.append(f"unexpected finding {x}")
    if "min_blocking" in exp and r["counts"]["blocking"] < exp["min_blocking"]:
        errors.append(f"{r['counts']['blocking']} blocking findings, expected at least {exp['min_blocking']}")
    return errors


def fill_pdf(template: Path, answers: dict, form: dict, out: Path) -> None:
    """Fill the blank form the way a PDF reader would, from normalised answers."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    writer = PdfWriter(clone_from=PdfReader(str(template)))
    vals: dict[str, object] = {}

    def state(options, value):
        labels = [cu.option_label(o)[1].lower() for o in options]
        return NameObject("/%d" % labels.index(value.lower()))

    for item in form.get("control", []):
        v = answers.get(item["id"], "")
        if v:
            vals[item["id"]] = state(item["options"], v) if item.get("kind") == "choice" else v
    for sec in form["sections"]:
        for f in sec["fields"]:
            kind, fid, v = f.get("kind", "line"), f["id"], answers.get(f["id"])
            if kind in ("line", "area") and v:
                vals[fid] = v
            elif kind == "choice" and v:
                vals[fid] = state(f["options"], v)
            elif kind == "checks":
                for oid in v or []:
                    vals[f"{fid}.{oid}"] = NameObject("/on")
            elif kind == "grid":
                for row in v or []:
                    for c in f["columns"]:
                        if row.get(c["id"]):
                            vals[f"{fid}.{row['_row']}.{c['id']}"] = row[c["id"]]
    for i, role in enumerate((form.get("signoff") or {}).get("rows", []), 1):
        for col, v in (answers.get("signoff", {}).get(role) or {}).items():
            if v:
                vals[f"signoff.{i}.{col}"] = v

    # Set /V on each terminal field by its full name; buttons get the matching /AS on their widgets.
    def walk(field, prefix=""):
        field = field.get_object()
        name = field.get("/T")
        full = f"{prefix}.{name}" if prefix and name else (name or prefix)
        kids = field.get("/Kids")
        if full in vals:
            v = vals[full]
            field[NameObject("/V")] = v if isinstance(v, NameObject) else TextStringObject(str(v))
            for k in (kids or [field]):
                k = k.get_object()
                if isinstance(v, NameObject) and "/AP" in k:
                    on = v in k["/AP"].get("/N", {})
                    k[NameObject("/AS")] = v if on else NameObject("/Off")
            return
        for k in kids or []:
            if "/T" in k.get_object():
                walk(k, full)

    for f in writer._root_object["/AcroForm"]["/Fields"]:
        walk(f)
    writer.set_need_appearances_writer(True)
    with open(out, "wb") as fh:
        writer.write(fh)


def round_trip(spec: dict, root: Path) -> list[str]:
    form = cu.load_yaml(root / cu.FORM)
    from_yaml = cu.assess(root / spec["answers"], root)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "filled-use-case.pdf"
        fill_pdf(root / spec["template"], from_yaml["answers"], form, pdf)
        from_pdf = cu.assess(pdf, root)
    errors = []
    a, b = from_yaml["answers"], from_pdf["answers"]
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            errors.append(f"answer {k!r}: YAML {a.get(k)!r} but PDF {b.get(k)!r}")
    fa = {(f["check"], f["field"], f["severity"]) for f in from_yaml["findings"]}
    fb = {(f["check"], f["field"], f["severity"]) for f in from_pdf["findings"]}
    if fa != fb:
        errors.append(f"findings differ: YAML only {sorted(fa - fb)}, PDF only {sorted(fb - fa)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, help="workspace root (default: found from the current directory)")
    a = ap.parse_args(argv)
    root = (a.root or cu.find_root(Path.cwd()) or cu.find_root(cu.SKILL))
    if root is None:
        print(f"error: no DPF workspace found ({cu.FORM} is missing); pass --root", file=sys.stderr)
        return 2
    root = root.resolve()
    spec = yaml.safe_load((FIXTURES / "expected.yaml").read_text(encoding="utf-8"))
    pdf_ok, failed = have_pypdf(), 0
    for case in spec.get("cases", []):
        if case.get("needs") == "pypdf" and not pdf_ok:
            print(f"skip  {case['id']} (needs pypdf)")
            continue
        if not resolve(case["input"], root).is_file():
            print(f"skip  {case['id']} ({case['input']} is not in this workspace)")
            continue
        errors = run_case(case, root)
        failed += bool(errors)
        print(("FAIL" if errors else "ok  ") + f"  {case['id']}")
        for e in errors:
            print(f"      {e}")
    rt = spec.get("pdf_round_trip")
    if rt:
        if not pdf_ok:
            print("skip  pdf-round-trip (needs pypdf)")
        elif not (root / rt["answers"]).is_file():
            print(f"skip  pdf-round-trip ({rt['answers']} is not in this workspace)")
        else:
            errors = round_trip(rt, root)
            failed += bool(errors)
            print(("FAIL" if errors else "ok  ") + "  pdf-round-trip")
            for e in errors:
                print(f"      {e}")
    print("all passed" if not failed else f"{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
