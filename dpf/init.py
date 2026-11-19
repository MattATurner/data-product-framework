"""`dpf init <dir>`: scaffold a clean workspace with the framework and none of the example material."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from dpf.core import Report, Workspace

# Framework parts copied into a new workspace. Example products, their specs, the example
# registry overlay, generated output and evidence are never copied.
TEMPLATE_PATHS = [
    "AGENTS.md", "bootstrap", "products/README.md",
    "framework", ".agents", "registry", "docs/adr",
    "docs/user-guide.md", "dpf", "pyproject.toml", ".github/requirements", "Makefile", ".gitignore",
    ".github/workflows/ci.yml", "tests/contracts", "tests/evals/README.md", "tests/golden/README.md",
]
AGENT_SYMLINKS = ("GEMINI.md", "CLAUDE.md", ".cursorrules", ".clinerules")
EMPTY_DIRS = ["changes", "products", "tests/golden"]
EXCLUDED = ["examples/", "generated/", "evidence/", "tests/golden/*",
            "docs/fhd/", "docs/presentation/", "docs/index.html", "docs/data-product-framework-plan.md",
            "docs/demo-walkthrough.md"]
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".DS_Store",
    ".terraform", ".terraform.lock.hcl", "terraform.tfstate", "terraform.tfstate.*",
    "tf-output.json", "tf.log", "*.egg-info", ".venv", ".pytest_cache",
)

CLEAN_AGENT_CONFIG = {
    "description": "Auto-populated by bootstrap/deploy.sh after Layer-0 Terraform bootstrap. Read by coding agents and DPF scripts.",
    "gcp_project_id": "{project_id}",
    "gcp_project_number": "{project_number}",
    "bigquery_region": "us-central1",
    "knowledge_catalog_region": "us-central1",
    "business_timezone": "Australia/Perth",
    "deployment_service_account": "dpf-deployer@{project_id}.iam.gserviceaccount.com",
    "dataform_service_account": "dataform-runner@{project_id}.iam.gserviceaccount.com",
    "monitor_service_account": "dpf-monitor@{project_id}.iam.gserviceaccount.com",
    "default_dataform_repository": "dpf-workspace",
    "state_bucket": "{project_id}-dpf-state",
    "presentation_server_url": "",
    "fhd_server_url": "",
}


def _reset_hydrated_configs(dst: Path) -> None:
    """Scrub live project IDs, service accounts, and URLs copied from a bootstrapped source workspace."""
    cfg_path = dst / "registry/agent-config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(CLEAN_AGENT_CONFIG, indent=2) + "\n", encoding="utf-8")

    defaults_path = dst / "registry/platform-defaults.yaml"
    if defaults_path.is_file():
        txt = defaults_path.read_text(encoding="utf-8")
        txt = re.sub(r"(?m)^gcp_project:\s*[^#\n]+", "gcp_project: null                     ", txt, count=1)
        txt = re.sub(r"(?m)^billing_project:\s*[^#\n]+", "billing_project: null                 ", txt, count=1)
        defaults_path.write_text(txt, encoding="utf-8")


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
    _reset_hydrated_configs(dst)
    for rel in EMPTY_DIRS:
        (dst / rel).mkdir(parents=True, exist_ok=True)
    for link_name in AGENT_SYMLINKS:
        link_path = dst / link_name
        if not link_path.exists() and not link_path.is_symlink():
            try:
                link_path.symlink_to("AGENTS.md")
            except OSError:
                shutil.copy2(dst / "AGENTS.md", link_path)
    (dst / "README.md").write_text(
        "# Data Product Framework workspace\n\n"
        "Scaffolded by `dpf init`. The registry ships with clean platform defaults and an empty\n"
        "source-system, glossary, entity and conformance catalogue: add your own.\n\n"
        "## First-time setup (Layer 0)\n\n"
        "- Run `./bootstrap/deploy.sh --project-id <id> --region <region> --timezone <tz>` to create a new GCP project,\n"
        "  or `./bootstrap/deploy-existing-project.sh --project-id <id>` to attach to an existing project,\n"
        "  or `python3 bootstrap/hydrate_workspace.py --offline --region <region> --timezone <tz>` for offline use.\n"
        "- See `bootstrap/README.md` or run `@bootstrap/onboarding-prompt.md` in your coding agent.\n\n"
        "## First product\n\n"
        "1. Add source systems to `registry/source_systems.yaml` and agreed terms to `registry/glossary.yaml`.\n"
        "2. With the business, describe, score and choose the use case, then write a BRD or a PRD\n"
        "   (`framework/templates/define/`, see `framework/templates/README.md`).\n"
        "3. Record the BRD in business language (`framework/skills/author-brd`):\n"
        "   `products/<product>/specs/brd/spec.md` and `brd.yaml`.\n"
        "4. `dpf brd validate <product>` until G0 passes.\n"
        "5. `dpf tdd resolve <product>`; write `products/<product>/specs/tdd/spec.md`, `playback.md`, and `products/<product>/product.yaml`\n"
        "   from `framework/templates/design/`.\n"
        "6. The business owner reads `playback.md`; record it with `dpf signoff <product> --by <name> --role business_owner`.\n"
        "7. `dpf check <product> --gate G2`, then `dpf generate <product>` and `dpf check <product> --gate G3`.\n"
        "8. Deploy, `dpf test run <product> --live`, attest, and `dpf check <product> --gate G4`.\n\n"
        "See `docs/user-guide.md`.\n", encoding="utf-8")
    report.info("not copied (example material): " + ", ".join(EXCLUDED))
    return 0
