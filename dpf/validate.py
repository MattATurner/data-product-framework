"""Framework self-validation (`dpf validate`): the toolkit's own parts fit together.

* contracts are valid JSON Schema 2020-12 documents with an `$id`, and every `$ref` resolves;
* every SKILL.md front-matter conforms to skill.v1, follows the Agent Skills format (the
  `name` equals the skill's directory) and implements a platform capability spec that exists;
* methodology packs conform to methodology-pack.v1; every role names an existing skill and
  every engine it claims has an adapter that implements the role; every rule a pack lists
  exists and conforms to rule.v1;
* engine adapters conform to engine-adapter.v1;
* ADRs carry `id`, `status` and `decides` front-matter, and every ADR cited anywhere exists;
* products' manifests, BRD answers and acceptance mappings conform to their contracts.
"""

from __future__ import annotations

import json

from dpf.core import Report, Workspace, front_matter, load_yaml


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def validate_contracts(ws: Workspace, report: Report) -> None:
    from jsonschema import Draft202012Validator
    from referencing.exceptions import Unresolvable

    report.head("validate · contracts", gate="validate")
    bad = 0
    for name, schema in ws.contracts.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - reported
            report.fail(f"{name}: not a valid JSON Schema 2020-12 document: {str(exc).splitlines()[0]}")
            bad += 1
            continue
        if not schema.get("$id", "").endswith(f"/{name}.json"):
            report.fail(f"{name}: $id should end with /{name}.json")
            bad += 1
        refs = set()

        def walk(o):
            if isinstance(o, dict):
                if isinstance(o.get("$ref"), str):
                    refs.add(o["$ref"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(schema)
        resolver = ws._schema_registry.resolver(base_uri=schema.get("$id", ""))
        for ref in sorted(refs):
            try:
                resolver.lookup(ref)
            except Unresolvable:
                report.fail(f"{name}: $ref {ref} does not resolve")
                bad += 1
    if not bad:
        report.ok(f"{len(ws.contracts)} contracts are valid JSON Schema 2020-12 and every $ref resolves")


def validate_skills(ws: Workspace, report: Report) -> None:
    report.head("validate · skills", gate="validate")
    caps = set(ws.platform_specs)
    bad = 0
    for sid, s in sorted(ws.skills.items()):
        rel = s.path.relative_to(ws.root)
        errs = ws.validate(s.fm, "skill.v1")
        if errs:
            report.fail(f"{rel}: {'; '.join(errs[:3])}")
            bad += 1
            continue
        if s.fm.get("name") != s.path.parent.name:
            report.fail(f"{rel}: Agent Skills `name` must equal the directory name '{s.path.parent.name}'")
            bad += 1
        if s.get("implements") not in caps:
            report.fail(f"{rel}: implements '{s.get('implements')}', which has no platform spec")
            bad += 1
        if "/" in sid and sid.split("/")[0] != (s.get("methodology") or ""):
            report.fail(f"{rel}: skill_id {sid} is namespaced but methodology is '{s.get('methodology')}'")
            bad += 1
        if not s.body.strip():
            report.fail(f"{rel}: has no instructions after the front-matter")
            bad += 1
    if not bad:
        report.ok(f"{len(ws.skills)} skills conform to skill.v1 and the Agent Skills format")


def validate_packs(ws: Workspace, report: Report) -> None:
    report.head("validate · methodology packs and engine adapters", gate="validate")
    bad = 0
    for aid, a in ws.adapters.items():
        errs = ws.validate(_strip(a), "engine-adapter.v1")
        if errs:
            report.fail(f"engines/{aid}/adapter.yaml: {'; '.join(errs[:3])}")
            bad += 1
    for pid, pack in ws.packs.items():
        errs = ws.validate(_strip(pack), "methodology-pack.v1")
        if errs:
            report.fail(f"methodologies/{pid}/methodology.yaml: {'; '.join(errs[:3])}")
            bad += 1
            continue
        for role in pack.get("roles", []) or []:
            skill = role.get("skill")
            if skill and skill not in ws.skills:
                report.fail(f"{pid}: role '{role['id']}' names skill '{skill}', which does not exist")
                bad += 1
            for eng in (pack.get("supported_engines") or {}).get(role["id"], []) or []:
                a = ws.adapters.get(eng)
                if a is None:
                    report.fail(f"{pid}: role '{role['id']}' claims engine '{eng}', which has no adapter")
                    bad += 1
                elif a.get("status") != "implemented" or role["id"] not in (a.get("implemented_roles") or []):
                    report.fail(f"{pid}: role '{role['id']}' claims engine '{eng}', whose adapter does not implement it")
                    bad += 1
        for rid in pack.get("rules", []) or []:
            rule = ws.rules.get(rid)
            if rule is None:
                report.fail(f"{pid}: lists rule '{rid}', which has no file under methodologies/*/rules/")
                bad += 1
                continue
            rerr = ws.validate(_strip(rule), "rule.v1")
            if rerr:
                report.fail(f"rule {rid}: {'; '.join(rerr[:3])}")
                bad += 1
    if not bad:
        report.ok(f"{len(ws.packs)} packs and {len(ws.adapters)} adapters conform; every claimed role × engine is implemented")


def validate_adrs(ws: Workspace, report: Report) -> None:
    report.head("validate · ADRs", gate="validate")
    bad = 0
    for aid, path in ws.adrs.items():
        fm, _ = front_matter(path)
        missing = [k for k in ("id", "status", "decides") if not fm.get(k)]
        if missing:
            report.fail(f"{path.relative_to(ws.root)}: front-matter lacks {', '.join(missing)}")
            bad += 1
    cited: dict[str, str] = {}
    for sid, s in ws.skills.items():
        if s.get("adr"):
            cited[s.get("adr")] = f"skill {sid}"
    for pid in ws.product_ids():
        for adr in load_yaml(ws.root / "products" / pid / "product.yaml").get("adrs") or []:
            cited[adr] = f"product {pid}"
    for adr, where in sorted(cited.items()):
        if adr not in ws.adrs:
            report.fail(f"{where} cites {adr}, which has no ADR file")
            bad += 1
    if not bad:
        report.ok(f"{len(ws.adrs)} ADRs carry id/status/decides; all {len(cited)} cited ADRs exist")


def validate_products(ws: Workspace, report: Report) -> None:
    report.head("validate · product documents", gate="validate")
    for pid in ws.product_ids():
        p = ws.product(pid)
        errs = ws.validate(p.manifest, "product-manifest.v1")
        report.check(not errs, f"{pid}: product.yaml conforms to product-manifest.v1",
                     f"{pid}: product.yaml: {'; '.join(errs[:3])}")
        if p.brd_dir.exists():
            berr = ws.validate(p.brd, "brd.v1")
            report.check(not berr, f"{pid}: brd.yaml conforms to brd.v1", f"{pid}: brd.yaml: {'; '.join(berr[:3])}")
        else:
            report.fail(f"{pid}: BRD directory openspec/specs/{p.manifest['specs']['brd']} is missing")
        if p.acceptance is not None:
            aerr = ws.validate(p.acceptance, "acceptance.v1")
            report.check(not aerr, f"{pid}: acceptance.yaml conforms to acceptance.v1",
                         f"{pid}: acceptance.yaml: {'; '.join(aerr[:3])}")
        if p.signoff is not None:
            serr = ws.validate(p.signoff, "signoff.v1")
            report.check(not serr, f"{pid}: signoff.yaml conforms to signoff.v1",
                         f"{pid}: signoff.yaml: {'; '.join(serr[:3])}")


def validate(ws: Workspace, report: Report) -> int:
    validate_contracts(ws, report)
    validate_skills(ws, report)
    validate_packs(ws, report)
    validate_adrs(ws, report)
    validate_products(ws, report)
    return report.failures


def contract_json(ws: Workspace, name: str) -> str:
    return json.dumps(ws.contracts[name], indent=2)
