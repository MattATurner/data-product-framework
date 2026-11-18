#!/usr/bin/env python3
"""Hydrates agent-config.json, registry/platform-defaults.yaml, and optional example tfvars from Layer-0 Terraform outputs or offline setup."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _val(outputs: dict, key: str, default: str = "") -> str:
    entry = outputs.get(key)
    if isinstance(entry, dict):
        return str(entry.get("value") or default)
    return str(entry or default)


def _normalize_url(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    if cleaned.lower() in {"none", "local", "skip", "null", "-"}:
        return ""
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned.rstrip("/")


def update_platform_defaults(path: Path, project_id: str | None, region: str, timezone: str) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^region:\s*[^#\n]+", f"region: {region:<29}", text, count=1)
    if project_id and not project_id.startswith("{"):
        text = re.sub(r"(?m)^gcp_project:\s*[^#\n]+", f"gcp_project: {project_id:<24}", text, count=1)
        text = re.sub(r"(?m)^billing_project:\s*[^#\n]+", f"billing_project: {project_id:<20}", text, count=1)
    text = re.sub(r"(?m)^business_timezone:\s*[^#\n]+", f"business_timezone: {timezone}", text, count=1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Hydrate DPF workspace configuration from Layer-0 Terraform output or offline first-run settings."
    )
    ap.add_argument("tf_output", nargs="?", help="Path to bootstrap/terraform/tf-output.json")
    ap.add_argument("--offline", action="store_true", help="Hydrate local config without a Terraform output file")
    ap.add_argument("--project-id", default=None, help="GCP Project ID when running --offline")
    ap.add_argument("--region", default="us-central1", help="GCP region when running --offline")
    ap.add_argument("--timezone", default="Australia/Perth", help="Business timezone when running --offline")
    ap.add_argument(
        "--presentation-server-url",
        default=None,
        help="Optional Presentation Server base URL (or set DPF_PRESENTATION_SERVER_URL)",
    )
    ap.add_argument(
        "--fhd-server-url",
        default=None,
        help="Optional FHD Server base URL (or set DPF_FHD_SERVER_URL)",
    )
    args = ap.parse_args()

    if not args.tf_output and not args.offline:
        ap.error("Provide <path/to/tf-output.json> or pass --offline.")

    repo_root = Path(__file__).resolve().parent.parent
    agent_cfg_path = repo_root / "registry/agent-config.json"
    existing_cfg: dict = {}
    if agent_cfg_path.is_file():
        try:
            existing_cfg = json.loads(agent_cfg_path.read_text(encoding="utf-8"))
        except Exception:
            existing_cfg = {}

    if args.tf_output:
        tf_out_path = Path(args.tf_output).resolve()
        outputs = json.loads(tf_out_path.read_text(encoding="utf-8"))
        project_id = _val(outputs, "project_id")
        project_number = _val(outputs, "project_number")
        region = _val(outputs, "region", "us-central1")
        timezone = _val(outputs, "business_timezone", "Australia/Perth")
        gcp_account = _val(outputs, "gcp_account_name")
        deployer_sa = _val(outputs, "deployment_service_account")
        dataform_sa = _val(outputs, "dataform_service_account")
        monitor_sa = _val(outputs, "monitor_service_account")
        dataform_repo = _val(outputs, "dataform_repository", "sales-performance")
        state_bucket = _val(outputs, "terraform_output_bucket")
    else:
        project_id = args.project_id or existing_cfg.get("gcp_project_id") or "{project_id}"
        project_number = existing_cfg.get("gcp_project_number") or "{project_number}"
        region = args.region
        timezone = args.timezone
        gcp_account = ""
        deployer_sa = f"dpf-deployer@{project_id}.iam.gserviceaccount.com"
        dataform_sa = f"dataform-runner@{project_id}.iam.gserviceaccount.com"
        monitor_sa = f"dpf-monitor@{project_id}.iam.gserviceaccount.com"
        dataform_repo = existing_cfg.get("default_dataform_repository") or "sales-performance"
        state_bucket = f"{project_id}-dpf-state"

    if args.presentation_server_url is not None:
        pres_url = _normalize_url(args.presentation_server_url)
    elif os.environ.get("DPF_PRESENTATION_SERVER_URL"):
        pres_url = _normalize_url(os.environ.get("DPF_PRESENTATION_SERVER_URL"))
    else:
        pres_url = _normalize_url(existing_cfg.get("presentation_server_url"))

    if args.fhd_server_url is not None:
        fhd_url = _normalize_url(args.fhd_server_url)
    elif os.environ.get("DPF_FHD_SERVER_URL"):
        fhd_url = _normalize_url(os.environ.get("DPF_FHD_SERVER_URL"))
    else:
        fhd_url = _normalize_url(existing_cfg.get("fhd_server_url"))

    # 1. Update agent-config.json
    agent_cfg = {
        "description": "Auto-populated by deploy.sh or first-run setup. Read by coding agents and DPF scripts.",
        "gcp_project_id": project_id,
        "gcp_project_number": project_number,
        "bigquery_region": region,
        "knowledge_catalog_region": region,
        "business_timezone": timezone,
        "deployment_service_account": deployer_sa,
        "dataform_service_account": dataform_sa,
        "monitor_service_account": monitor_sa,
        "default_dataform_repository": dataform_repo,
        "state_bucket": state_bucket,
        "presentation_server_url": pres_url,
        "fhd_server_url": fhd_url,
    }
    agent_cfg_path.write_text(json.dumps(agent_cfg, indent=2) + "\n", encoding="utf-8")
    print(f"  ok | updated {agent_cfg_path.relative_to(repo_root)} (presentation_server_url={pres_url or 'local-only'})")

    # 2. Update registry/platform-defaults.yaml
    defaults_path = repo_root / "registry/platform-defaults.yaml"
    update_platform_defaults(defaults_path, project_id if not args.offline or args.project_id else None, region, timezone)
    print(f"  ok | updated {defaults_path.relative_to(repo_root)} (gcp_project={project_id}, region={region}, timezone={timezone})")

    # 3. Pre-populate examples/sales_performance/terraform/terraform.tfvars if examples are present and live TF ran
    ex_tf_dir = repo_root / "examples/sales_performance/terraform"
    if args.tf_output and ex_tf_dir.is_dir():
        domain = gcp_account.split("@", 1)[1] if "@" in gcp_account else "example.com"
        tfvars_path = ex_tf_dir / "terraform.tfvars"
        tfvars_content = (
            f"# Auto-generated by bootstrap/hydrate_workspace.py (edit group emails if using dedicated Google Groups)\n"
            f'project_id                = "{project_id}"\n'
            f'region                    = "{region}"\n'
            f'consumer_group            = "sales-consumers@{domain}"\n'
            f'analyst_group             = "analysts@{domain}"\n'
            f'contact_reader_group      = "customer-contact-readers@{domain}"\n'
            f'dataform_repository       = "{dataform_repo}"\n'
            f'dataform_service_account  = "{dataform_sa}"\n'
            f'dataform_release_schedule = ""\n'
            f'monitor_service_account   = "{monitor_sa}"\n'
        )
        tfvars_path.write_text(tfvars_content, encoding="utf-8")
        print(f"  ok | updated {tfvars_path.relative_to(repo_root)}")

    # 4. Re-stamp golden copies for worked examples if products or examples are populated and dpf is installed
    if list((repo_root / "products").glob("*/product.yaml")) or list((repo_root / "examples").glob("*/product.yaml")):
        dpf_cmd: list[str] | None = None
        venv_dpf = repo_root / ".venv/bin/dpf"
        which_dpf = shutil.which("dpf")
        if venv_dpf.is_file():
            dpf_cmd = [str(venv_dpf)]
        elif which_dpf:
            dpf_cmd = [which_dpf]
        else:
            probe = subprocess.run(
                [sys.executable, "-c", "import dpf"],
                cwd=repo_root,
                capture_output=True,
            )
            if probe.returncode == 0:
                dpf_cmd = [sys.executable, "-m", "dpf"]

        if dpf_cmd:
            res = subprocess.run(
                [*dpf_cmd, "generate", "--all", "--update-golden"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                print("  ok | re-stamped worked-example golden copies for new project/region/timezone")
            else:
                print("  info | run 'dpf generate --all --update-golden' after activating .venv to sync example golden copies")
        else:
            print("  info | run 'dpf generate --all --update-golden' after installing dpf (.venv) to sync example golden copies")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
