"""Helpers shared by the engine, Terraform and document renderers."""

from __future__ import annotations

import json
import re

from dpf.core import Product
from dpf.graph import REF, VAR, ProductGraph

TIMESTAMP_SUFFIXES = ("_ts", "_timestamp", "_at")


def sub_refs(sql: str, fn) -> str:
    return REF.sub(lambda m: fn(m.group(1)), sql)


def sub_vars(sql: str, fn) -> str:
    return VAR.sub(lambda m: fn(m.group(1)), sql)


def marker(fields: dict, prefix: str = "--") -> str:
    """Header line `dpf trace` reads: space-separated key=value pairs, list values comma-joined."""
    parts = []
    for k, v in fields.items():
        if isinstance(v, (list, tuple)):
            v = ",".join(str(x) for x in v)
        if v in (None, ""):
            continue
        parts.append(f"{k}={str(v).replace(' ', '_')}")
    return f"{prefix} dpf: " + " ".join(parts)


MARKER = re.compile(r"^\s*(?:--|#|//)\s*dpf:\s*(.+)$", re.M)


def parse_markers(text: str) -> list[dict[str, str]]:
    out = []
    for m in MARKER.finditer(text):
        fields = {}
        for tok in m.group(1).split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                fields[k] = v
        out.append(fields)
    return out


def timezone(p: Product) -> str:
    return (p.manifest.get("orchestration") or {}).get("timezone") or p.registry.defaults.get("business_timezone", "UTC")


def project_vars(p: Product) -> dict[str, str]:
    """Compilation variables every engine project defines (all strings)."""
    out = {f"{k}_dataset": v for k, v in ((p.manifest.get("deployment") or {}).get("datasets") or {}).items()}
    out["business_timezone"] = timezone(p)
    for t in (p.manifest.get("governance") or {}).get("policy_tags", []) or []:
        out[f"policy_tag_{t['tag']}"] = ""
    return out


def is_timestamp(col: str | None) -> bool:
    return bool(col) and col.endswith(TIMESTAMP_SUFFIXES)


def js(value) -> str:
    """A JavaScript literal (JSON is valid JavaScript)."""
    return json.dumps(value, ensure_ascii=False)


def py_list(values: list[str]) -> str:
    return "[" + ", ".join("'" + v.replace("'", "\\'") + "'" for v in values) + "]"


def undefined_vars(p: Product, g: ProductGraph, sqls: list[str]) -> list[str]:
    known = set(project_vars(p))
    found = []
    for sql in sqls:
        found += [v for v in VAR.findall(sql or "") if v not in known]
    return sorted(set(found))


def kebab_id(*parts: str, limit: int = 63) -> str:
    s = "-".join(re.sub(r"[^a-z0-9]+", "-", x.lower()).strip("-") for x in parts if x)
    return s[:limit].rstrip("-")


def snake_id(*parts: str) -> str:
    return "_".join(re.sub(r"[^a-z0-9]+", "_", x.lower()).strip("_") for x in parts if x)


def duration_minutes(iso: str) -> int:
    m = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", iso or "")
    if not m:
        raise ValueError(f"not an ISO 8601 duration: {iso}")
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mi + (1 if s else 0)


def dts_schedule(iso: str) -> str:
    """Data Transfer Service schedule text for a check interval."""
    minutes = duration_minutes(iso)
    if minutes % 60 == 0:
        return f"every {minutes // 60} hours"
    return f"every {max(minutes, 15)} minutes"
