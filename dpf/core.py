"""Workspace model, reporting, contract validation and digests shared by every dpf command."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Iterable

import yaml

from dpf import __version__
from dpf.specs import Spec, parse_spec

LAYERS = ("staging", "silver", "gold")


# ----------------------------------------------------------------- reporting
class Report:
    """Collects check outcomes. Prints as it goes unless JSON output was requested."""

    OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
    _GLYPH = {"ok": "  ok ", "warn": "warn ", "fail": "FAIL ", "info": "     "}

    def __init__(self, json_mode: bool = False, quiet: bool = False, stream=None):
        self.json_mode = json_mode
        self.quiet = quiet
        self.stream = stream or sys.stdout
        self.entries: list[dict] = []
        self.section = ""
        self.gate = ""

    # -- emitters
    def head(self, title: str, gate: str | None = None) -> None:
        self.section = title
        self._pending = title
        if gate is not None:
            self.gate = gate
        if not (self.json_mode or self.quiet):
            print(f"\n\033[1m{title}\033[0m", file=self.stream)
            self._pending = None

    def _add(self, level: str, msg: str, **ctx: Any) -> None:
        entry = {"gate": self.gate, "section": self.section, "level": level, "message": msg}
        if ctx:
            entry.update(ctx)
        self.entries.append(entry)
        if not self.json_mode and not (self.quiet and level in (self.OK, self.INFO)):
            if getattr(self, "_pending", None):
                print(f"\n\033[1m{self._pending}\033[0m", file=self.stream)
                self._pending = None
            print(f"{self._GLYPH[level]}| {msg}", file=self.stream)

    def ok(self, msg: str, **ctx: Any) -> None:
        self._add(self.OK, msg, **ctx)

    def warn(self, msg: str, **ctx: Any) -> None:
        self._add(self.WARN, msg, **ctx)

    def fail(self, msg: str, **ctx: Any) -> None:
        self._add(self.FAIL, msg, **ctx)

    def info(self, msg: str, **ctx: Any) -> None:
        self._add(self.INFO, msg, **ctx)

    def check(self, cond: bool, ok_msg: str, fail_msg: str | None = None, warn: bool = False) -> bool:
        if cond:
            self.ok(ok_msg)
        elif warn:
            self.warn(fail_msg or ok_msg)
        else:
            self.fail(fail_msg or ok_msg)
        return cond

    # -- summaries
    @property
    def failures(self) -> int:
        return sum(1 for e in self.entries if e["level"] == self.FAIL)

    @property
    def warnings(self) -> int:
        return sum(1 for e in self.entries if e["level"] == self.WARN)

    def messages(self, level: str | None = None) -> list[str]:
        return [e["message"] for e in self.entries if level is None or e["level"] == level]

    def finish(self) -> int:
        if self.json_mode:
            json.dump({"failures": self.failures, "warnings": self.warnings, "entries": self.entries},
                      self.stream, indent=2)
            print(file=self.stream)
        else:
            print(file=self.stream)
            if self.failures:
                print(f"\033[31m{self.failures} failure(s), {self.warnings} warning(s)\033[0m", file=self.stream)
            else:
                print(f"\033[32mall checks passed ({self.warnings} warning(s))\033[0m", file=self.stream)
        return 1 if self.failures else 0


# ----------------------------------------------------------------- io helpers
def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def front_matter(md: Path) -> tuple[dict, str]:
    txt = md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", txt, re.S)
    if not m:
        return {}, txt
    return (yaml.safe_load(m.group(1)) or {}), m.group(2)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalise_text(txt: str) -> str:
    return "\n".join(line.rstrip() for line in txt.replace("\r\n", "\n").strip().splitlines()) + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def kebab(s: str) -> str:
    return s.replace("_", "-")


# ----------------------------------------------------------------- registry
_REGISTRY_KEYS = {  # list key -> identity field, per registry file
    "mcp_servers.yaml": [("servers", "id"), ("tools", "id"), ("no_mcp_option_yet", None)],
    "source_systems.yaml": [("systems", "system_id")],
    "conformance.yaml": [("conformed_dimensions", "name")],
    "entities.yaml": [("entities", "name")],
    "glossary.yaml": [("terms", "id")],
}


def _merge_list(base: list, extra: list, key: str | None) -> list:
    if key is None:
        return list(dict.fromkeys([*base, *extra]))
    seen = {item.get(key): i for i, item in enumerate(base) if isinstance(item, dict)}
    out = list(base)
    for item in extra:
        k = item.get(key) if isinstance(item, dict) else None
        if k in seen:
            out[seen[k]] = item
        else:
            out.append(item)
    return out


class Registry:
    """registry/*.yaml, optionally overlaid (read-only) with an example overlay directory."""

    def __init__(self, base: Path, overlay: Path | None = None):
        self.base, self.overlay = base, overlay
        self.data: dict[str, dict] = {}
        for p in sorted(base.glob("*.yaml")):
            self.data[p.name] = load_yaml(p)
        if overlay and overlay.exists():
            for p in sorted(overlay.glob("*.yaml")):
                extra = load_yaml(p)
                cur = self.data.setdefault(p.name, {})
                for k, v in extra.items():
                    ident = dict(_REGISTRY_KEYS.get(p.name, [])).get(k, "id")
                    if isinstance(v, list) and isinstance(cur.get(k), list):
                        cur[k] = _merge_list(cur[k], v, ident)
                    else:
                        cur[k] = v

    def get(self, file: str, key: str, default=None):
        return (self.data.get(file) or {}).get(key, default)

    @property
    def defaults(self) -> dict:
        return self.data.get("platform-defaults.yaml", {})

    @property
    def tools(self) -> dict[str, dict]:
        out = {s["id"]: s for s in self.get("mcp_servers.yaml", "servers", []) or []}
        out.update({t["id"]: t for t in self.get("mcp_servers.yaml", "tools", []) or []})
        return out

    @property
    def systems(self) -> dict[str, dict]:
        return {s["system_id"]: s for s in self.get("source_systems.yaml", "systems", []) or []}

    @property
    def conformed(self) -> dict[str, dict]:
        return {c["name"]: c for c in self.get("conformance.yaml", "conformed_dimensions", []) or []}

    @property
    def glossary_terms(self) -> list[dict]:
        return self.get("glossary.yaml", "terms", []) or []

    @property
    def rubric(self) -> dict:
        return self.data.get("brd-rubric.yaml", {})

    @property
    def vocabulary(self) -> dict:
        return self.data.get("brd-vocabulary.yaml", {})


# ----------------------------------------------------------------- skills & packs
@dataclass
class Skill:
    path: Path
    fm: dict
    body: str

    @property
    def dpf(self) -> dict:
        return (self.fm.get("metadata") or {}).get("dpf") or {}

    @property
    def id(self) -> str:
        return self.dpf.get("skill_id") or self.fm.get("name") or self.path.parent.name

    def get(self, key: str, default=None):
        return self.dpf.get(key, default)


# ----------------------------------------------------------------- workspace
class Workspace:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    # -- contracts
    @cached_property
    def contracts(self) -> dict[str, dict]:
        out = {}
        for p in sorted((self.root / "contracts").glob("*.schema.json")):
            out[p.name.removesuffix(".schema.json")] = json.loads(p.read_text(encoding="utf-8"))
        return out

    @cached_property
    def _schema_registry(self):
        from referencing import Registry as RefRegistry, Resource
        return RefRegistry().with_resources(
            [(d["$id"], Resource.from_contents(d)) for d in self.contracts.values() if "$id" in d])

    def validate(self, instance: Any, contract: str) -> list[str]:
        """Validate an instance against a contract; return human-readable errors (empty = valid)."""
        from jsonschema import Draft202012Validator, FormatChecker
        schema = self.contracts.get(contract)
        if schema is None:
            return [f"unknown contract '{contract}'"]
        v = Draft202012Validator(schema, registry=self._schema_registry, format_checker=FormatChecker())
        errs = []
        for e in sorted(v.iter_errors(instance), key=lambda e: list(e.absolute_path)):
            where = "/".join(str(p) for p in e.absolute_path) or "(root)"
            errs.append(f"{where}: {e.message}")
        return errs

    # -- framework metadata
    @cached_property
    def skills(self) -> dict[str, Skill]:
        out: dict[str, Skill] = {}
        paths = sorted(self.root.glob("skills/*/SKILL.md")) + sorted(self.root.glob("methodologies/*/skills/*/SKILL.md"))
        for p in paths:
            fm, body = front_matter(p)
            s = Skill(p, fm, body)
            out[s.id] = s
        return out

    @cached_property
    def packs(self) -> dict[str, dict]:
        out = {}
        for p in sorted(self.root.glob("methodologies/*/methodology.yaml")):
            d = load_yaml(p)
            d["_dir"] = p.parent
            out[d.get("id", p.parent.name)] = d
        return out

    @cached_property
    def rules(self) -> dict[str, dict]:
        out = {}
        for p in sorted(self.root.glob("methodologies/*/rules/*.yaml")):
            d = load_yaml(p)
            d["_path"] = p
            out[d.get("id", p.stem)] = d
        return out

    @cached_property
    def adapters(self) -> dict[str, dict]:
        out = {}
        for p in sorted(self.root.glob("engines/*/adapter.yaml")):
            d = load_yaml(p)
            d["_dir"] = p.parent
            out[d.get("engine_id", p.parent.name)] = d
        return out

    @cached_property
    def adrs(self) -> dict[str, Path]:
        out = {}
        for p in sorted(self.root.glob("adr/ADR-*.md")) + sorted(self.root.glob("products/*/adr/ADR-*.md")):
            fm, _ = front_matter(p)
            m = re.match(r"^(ADR-[A-Z0-9-]+?)(?:-[a-z].*)?$", p.stem)
            adr_id = fm.get("id") or (m.group(1) if m else p.stem)
            out[adr_id] = p
        return out

    def registry(self, overlay: str | None = None) -> Registry:
        return Registry(self.root / "registry", (self.root / overlay) if overlay else None)

    # -- products
    def product_ids(self) -> list[str]:
        return sorted(p.parent.name for p in (self.root / "products").glob("*/product.yaml"))

    def product(self, product_id: str) -> "Product":
        path = self.root / "products" / product_id / "product.yaml"
        if not path.exists():
            known = ", ".join(self.product_ids()) or "none"
            raise SystemExit(f"unknown product '{product_id}' (known: {known})")
        return Product(self, product_id, path)

    @property
    def platform_specs(self) -> dict[str, Path]:
        return {p.parent.name: p for p in sorted((self.root / "openspec/specs/platform").glob("*/spec.md"))}


class Product:
    def __init__(self, ws: Workspace, pid: str, path: Path):
        self.ws, self.id, self.path = ws, pid, path
        self.dir = path.parent

    @cached_property
    def manifest(self) -> dict:
        return load_yaml(self.path)

    # -- specs
    @property
    def brd_dir(self) -> Path:
        return self.ws.root / "openspec/specs" / self.manifest["specs"]["brd"]

    @property
    def tdd_dir(self) -> Path:
        return self.ws.root / "openspec/specs" / self.manifest["specs"]["tdd"]

    @cached_property
    def brd(self) -> dict:
        p = self.brd_dir / "brd.yaml"
        return load_yaml(p) if p.exists() else {}

    @cached_property
    def brd_spec(self) -> Spec:
        return parse_spec((self.brd_dir / "spec.md").read_text(encoding="utf-8"), self.brd_dir / "spec.md")

    @cached_property
    def tdd_spec(self) -> Spec:
        return parse_spec((self.tdd_dir / "spec.md").read_text(encoding="utf-8"), self.tdd_dir / "spec.md")

    @property
    def semantics_path(self) -> Path:
        return self.tdd_dir / "semantics.md"

    @cached_property
    def signoff(self) -> dict | None:
        p = self.tdd_dir / "signoff.yaml"
        return load_yaml(p) if p.exists() else None

    @cached_property
    def acceptance(self) -> dict | None:
        rel = self.manifest.get("acceptance")
        if not rel:
            return None
        p = self.dir / rel
        return load_yaml(p) if p.exists() else None

    @cached_property
    def registry(self) -> Registry:
        return self.ws.registry(self.manifest.get("registry_overlay"))

    # -- model helpers
    def models(self, layers: Iterable[str] = LAYERS) -> list[tuple[str, dict]]:
        out = []
        for layer in layers:
            cfg = (self.manifest.get("layers") or {}).get(layer) or {}
            for m in cfg.get("models", []) or []:
                out.append((layer, m))
        return out

    def model(self, name: str) -> tuple[str, dict] | None:
        for layer, m in self.models():
            if m.get("name") == name:
                return layer, m
        return None

    def layer_cfg(self, layer: str) -> dict:
        return (self.manifest.get("layers") or {}).get(layer) or {}

    def body(self, model: dict) -> str | None:
        rel = model.get("body")
        if not rel:
            return None
        p = self.dir / rel
        return p.read_text(encoding="utf-8") if p.exists() else None

    @property
    def generated_dir(self) -> Path:
        return self.ws.root / "generated" / self.id

    @property
    def evidence_dir(self) -> Path:
        return self.ws.root / "evidence" / self.id

    # -- requirement ids
    @cached_property
    def requirement_ids(self) -> list[str]:
        ids = [r.meta.get("id") for r in self.brd_spec.requirements if r.meta.get("id")]
        return sorted(set(ids), key=lambda x: int(x.split("-")[1]))

    @cached_property
    def scenario_ids(self) -> dict[str, str]:
        """AX id -> owning R id."""
        out = {}
        for r in self.brd_spec.requirements:
            for s in r.scenarios:
                if s.meta.get("id"):
                    out[s.meta["id"]] = r.meta.get("id")
        return out

    # -- digests
    def semantic_digest(self) -> str:
        models = sorted(
            [{"name": m["name"], "grain_statement": m.get("grain_statement"),
              "grain_columns": sorted(m.get("grain_columns") or []),
              "history_semantics": m.get("history_semantics")} for _, m in self.models()],
            key=lambda d: d["name"])
        sem = normalise_text(self.semantics_path.read_text(encoding="utf-8")) if self.semantics_path.exists() else ""
        return sha256(canonical({"semantics": sem, "models": models}))

    def build_digest(self, engine: str | None = None) -> str:
        """Digest of every input the build is generated from. Evidence is bound to it."""
        parts: dict[str, Any] = {
            "dpf": __version__,
            "generator": sha256("".join(normalise_text(f.read_text(encoding="utf-8")) for f in
                                        sorted((Path(__file__).parent / "generate").glob("*.py")))),
            "engine_override": engine,
            "manifest": self.manifest,
            "acceptance": self.acceptance,
            "signoff": self.signoff,
            "brd_version": self.brd.get("version"),
            "bodies": {m["name"]: self.body(m) for _, m in self.models() if m.get("body")},
            "registry": self.registry.data,
            "packs": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in self.ws.packs.items()},
            "rules": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in self.ws.rules.items()},
            "adapters": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in self.ws.adapters.items()},
        }
        return sha256(canonical(parts))


def iter_elements(manifest: dict) -> Iterable[tuple[str, dict]]:
    """Every traceable design element in a manifest as (element_ref, element)."""
    for s in manifest.get("sources", []) or []:
        yield f"source:{s.get('system_id')}", s
    for layer in LAYERS:
        for m in ((manifest.get("layers") or {}).get(layer) or {}).get("models", []) or []:
            yield f"model:{m.get('name')}", m
    for p in manifest.get("output_ports", []) or []:
        yield f"port:{p.get('name')}", p
    for r in (manifest.get("quality") or {}).get("rules", []) or []:
        yield f"rule:{r.get('id')}", r
    for s in (manifest.get("orchestration") or {}).get("schedules", []) or []:
        yield f"schedule:{s.get('id')}", s
    obs = manifest.get("observability") or {}
    for kind in ("freshness", "volume"):
        for o in obs.get(kind, []) or []:
            yield f"observability:{o.get('id')}", o
    if obs.get("schema_drift"):
        yield "observability:schema_drift", obs["schema_drift"]
    if obs.get("quality_scans"):
        yield "observability:quality_scans", obs["quality_scans"]
    for t in (manifest.get("governance") or {}).get("policy_tags", []) or []:
        yield f"policy:{t.get('id')}", t


def find_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for cand in [p, *p.parents]:
        if (cand / "contracts").is_dir() and (cand / "openspec").is_dir():
            return cand
    return Path(__file__).resolve().parent.parent
