"""OpenSpec markdown parser.

Understands the OpenSpec spec format (`## Purpose`, `## Requirements`, `### Requirement:`,
`#### Scenario:` with `- **WHEN**` / `- **THEN**` bullets) plus DPF metadata lines, which keep
identifiers out of headings so OpenSpec delta matching on requirement names stays stable:

    ### Requirement: Order line grain
    **Decision:** D-3 · **Satisfies:** R-2, R-3 · **Model:** fct_order_line · **Grain:** order_id, order_line_no
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

META_LINE = re.compile(r"^\s*\*\*[A-Za-z][A-Za-z ]*:\*\*")
META_PAIR = re.compile(r"\*\*([A-Za-z][A-Za-z ]*):\*\*\s*(.*?)\s*(?=\s·\s\*\*|$)")
NORMATIVE = re.compile(r"\b(SHALL|MUST)\b")
STEP = re.compile(r"^\s*-\s+\*\*(GIVEN|WHEN|THEN|AND|BECAUSE)\*\*\s+(.*)$")


def parse_meta(line: str) -> dict[str, str]:
    out = {}
    for k, v in META_PAIR.findall(line.strip()):
        out[k.strip().lower().replace(" ", "_")] = v.strip()
    return out


def split_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in re.split(r"[,\s]+", value) if v.strip()]


@dataclass
class Scenario:
    name: str
    meta: dict = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)
    line_no: int = 0

    @property
    def steps(self) -> list[tuple[str, str]]:
        return [(m.group(1), m.group(2)) for m in (STEP.match(l) for l in self.lines) if m]

    @property
    def keywords(self) -> set[str]:
        return {k for k, _ in self.steps}


@dataclass
class Requirement:
    name: str
    meta: dict = field(default_factory=dict)
    body_lines: list[str] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    line_no: int = 0

    @property
    def body(self) -> str:
        return "\n".join(self.body_lines).strip()

    @property
    def normative(self) -> bool:
        return bool(NORMATIVE.search(self.body))

    def ids(self, key: str) -> list[str]:
        return split_ids(self.meta.get(key))


@dataclass
class Spec:
    path: Path | None
    title: str = ""
    purpose: str = ""
    purpose_meta: dict = field(default_factory=dict)
    requirements: list[Requirement] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def has_purpose(self) -> bool:
        return "Purpose" in self.sections

    @property
    def has_requirements(self) -> bool:
        return "Requirements" in self.sections

    def requirement(self, req_id: str, key: str = "id") -> Requirement | None:
        for r in self.requirements:
            if r.meta.get(key) == req_id:
                return r
        return None


def parse_spec(text: str, path: Path | None = None) -> Spec:
    spec = Spec(path=path, raw=text)
    section = None
    section_lines: dict[str, list[str]] = {}
    req: Requirement | None = None
    scen: Scenario | None = None

    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("# ") and not spec.title:
            spec.title = line[2:].strip()
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            section_lines.setdefault(section, [])
            req, scen = None, None
            continue
        if section is not None:
            section_lines[section].append(line)

        if section == "Requirements" or (section or "").endswith("Requirements"):
            if line.startswith("### Requirement:"):
                req = Requirement(name=line.split(":", 1)[1].strip(), line_no=n)
                spec.requirements.append(req)
                scen = None
                continue
            if line.startswith("#### Scenario:") and req is not None:
                scen = Scenario(name=line.split(":", 1)[1].strip(), line_no=n)
                req.scenarios.append(scen)
                continue
            if req is None:
                continue
            if META_LINE.match(line):
                meta = parse_meta(line)
                (scen.meta if scen else req.meta).update(meta)
                continue
            if scen is not None:
                scen.lines.append(line)
            else:
                req.body_lines.append(line)
        elif section == "Purpose" and META_LINE.match(line):
            spec.purpose_meta.update(parse_meta(line))

    spec.sections = {k: "\n".join(v).strip() for k, v in section_lines.items()}
    purpose = [l for l in section_lines.get("Purpose", []) if not META_LINE.match(l)]
    spec.purpose = "\n".join(purpose).strip()
    return spec
