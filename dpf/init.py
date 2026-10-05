"""`dpf init <dir>`: scaffold a clean workspace with the framework and none of the example material."""

from __future__ import annotations

import shutil
from pathlib import Path

from dpf.core import Report, Workspace

# Framework parts copied into a new workspace. Example products, their specs, the example
# registry overlay, generated output and evidence are never copied.
TEMPLATE_PATHS = [
    "openspec/config.yaml", "openspec/schemas", "openspec/project.md", "openspec/AGENTS.md",
    "openspec/changes/README.md", "openspec/specs/platform", "contracts", "methodologies", "engines",
    "skills", "registry", "adr", "dpf", "tools/dpf", "pyproject.toml", "Makefile", ".gitignore",
    ".github/workflows/ci.yml", "tests/contracts", "tests/evals/README.md", "tests/golden/README.md",
    "docs/user-guide.md",
]
EMPTY_DIRS = ["openspec/specs/products", "openspec/changes", "products", "generated", "evidence", "tests/golden"]
EXCLUDED = ["openspec/specs/products/*", "products/*", "examples/", "generated/", "evidence/", "tests/golden/*",
            "docs/presentation/", "docs/index.html", "docs/data-product-framework-plan.md"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def init(ws: Workspace, target: Path, report: Report) -> int:
    dst = target.resolve()
    report.head(f"init — {dst}", gate="init")
    if dst.exists() and any(dst.iterdir()):
        report.fail(f"{dst} exists and is not empty")
        return 1
    for rel in TEMPLATE_PATHS:
        src = ws.root / rel
        if not src.exists():
            report.warn(f"{rel}: not in this workspace, skipped")
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, out, dirs_exist_ok=True, ignore=IGNORE)
        else:
            shutil.copy2(src, out)
        report.ok(rel)
    for rel in EMPTY_DIRS:
        d = dst / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    (dst / "README.md").write_text(
        "# Data Product Framework workspace\n\n"
        "Scaffolded by `dpf init`. The registry ships with the platform defaults and an empty\n"
        "source-system, glossary, entity and conformance catalogue: add your own.\n\n"
        "## First product\n\n"
        "1. Set `gcp_project`, `region` and `business_timezone` in `registry/platform-defaults.yaml`.\n"
        "2. Add source systems to `registry/source_systems.yaml` and agreed terms to `registry/glossary.yaml`.\n"
        "3. Write the BRD in business language (`skills/author-brd`):\n"
        "   `openspec/specs/products/<domain>/<product>/brd/spec.md` and `brd.yaml`.\n"
        "4. `dpf brd validate <product>` until G0 passes.\n"
        "5. `dpf tdd resolve <product>`; write the TDD spec, `semantics.md` and `products/<product>/product.yaml`.\n"
        "6. The business owner reads `semantics.md`; record it with `dpf signoff <product> --by <name> --role business_owner`.\n"
        "7. `dpf check <product> --gate G2`, then `dpf generate <product>` and `dpf check <product> --gate G3`.\n"
        "8. Deploy, `dpf test run <product> --live`, attest, and `dpf check <product> --gate G4`.\n\n"
        "See `docs/user-guide.md`.\n", encoding="utf-8")
    report.info("not copied (example material): " + ", ".join(EXCLUDED))
    return 0
