"""Deploy and verify governed LookML projects and dashboards via `looker-cli` (ADR-018).

Zero hard-coded Looker hosts, GCP project IDs, connection names, or folder IDs:
all environment bindings resolve from CLI flags, environment variables,
`~/.config/looker-cli/config.yaml`, and the product manifest (`deployment.environments`).
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from dpf.core import Product, Report, Workspace, retarget_env
from dpf.generate import build


def find_looker_cli() -> str | None:
    env_bin = os.environ.get("LOOKER_CLI")
    if env_bin and Path(env_bin).is_file():
        return env_bin
    found = shutil.which("looker-cli")
    if found:
        return found
    local_bin = Path.home() / ".local" / "bin" / "looker-cli"
    return str(local_bin) if local_bin.is_file() else None


def resolve_looker_base_url(profile: str | None = None, host_override: str | None = None) -> str | None:
    host = host_override or os.environ.get("LOOKER_HOST")
    if host:
        return host.rstrip("/") if host.startswith("http") else f"https://{host.rstrip('/')}"
    cfg_path = Path.home() / ".config" / "looker-cli" / "config.yaml"
    if not cfg_path.is_file():
        return None
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        prof_name = profile or os.environ.get("LOOKER_PROFILE") or cfg.get("default") or "default"
        prof = (cfg.get("profiles") or {}).get(prof_name) or {}
        h = str(prof.get("host") or "").strip()
        if not h:
            return None
        return h.rstrip("/") if h.startswith("http") else f"https://{h.rstrip('/')}"
    except Exception:
        return None


def resolve_target_product(
    ws: Workspace,
    product_id: str,
    *,
    env: str | None = None,
    project_id: str | None = None,
) -> Product:
    p = ws.product(product_id)
    if env:
        p = retarget_env(p, env)
    override_proj = project_id or os.environ.get("DPF_GCP_PROJECT")
    if override_proj:
        man = copy.deepcopy(p.manifest)
        man.setdefault("deployment", {})["gcp_project"] = override_proj
        clone = Product(p.ws, p.id, p.path)
        clone.active_env = p.active_env
        clone.__dict__["manifest"] = man
        p = clone
    return p


class LookerCliRunner:
    def __init__(
        self,
        binary: str,
        *,
        profile: str | None = None,
        host: str | None = None,
        port: str | None = None,
    ):
        self.binary = binary
        self.profile = profile or os.environ.get("LOOKER_PROFILE")
        self.host = host or os.environ.get("LOOKER_HOST")
        self.port = port or os.environ.get("LOOKER_PORT")

    def base_flags(self) -> list[str]:
        flags: list[str] = []
        if self.profile:
            flags += ["--profile", self.profile]
        if self.host:
            flags += ["--host", self.host]
        if self.port:
            flags += ["--port", str(self.port)]
        return flags

    def run(self, args: list[str], *, dev_session: bool = False, timeout: int = 90) -> subprocess.CompletedProcess[str]:
        if dev_session:
            subprocess.run(
                [self.binary, *self.base_flags(), "session", "update", "dev"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        return subprocess.run(
            [self.binary, *self.base_flags(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run_json(self, args: list[str], *, dev_session: bool = False, timeout: int = 90) -> tuple[bool, Any, str]:
        proc = self.run(args, dev_session=dev_session, timeout=timeout)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, None, err or out or f"exit code {proc.returncode}"
        if not out:
            return True, None, ""
        try:
            return True, json.loads(out), ""
        except json.JSONDecodeError:
            return True, out, ""


def _primary_dataset(p: Product, spec: dict) -> str:
    dep_ds = (p.manifest.get("deployment") or {}).get("datasets") or {}
    for exp in spec.get("explores") or []:
        base = exp.get("from")
        cube = next((c for c in (spec.get("cubes") or []) if c["name"] == base), None)
        if cube and cube.get("table_ref"):
            parts = str(cube["table_ref"]).split(".")
            if len(parts) == 3 and parts[1]:
                return parts[1]
    return dep_ds.get("silver") or dep_ds.get("gold") or next(iter(dep_ds.values()), f"{p.id}_gold")


def _resolve_folder_id(cli: LookerCliRunner, folder: str) -> tuple[str | None, str]:
    if folder.isdigit():
        return folder, ""
    ok, payload, err = cli.run_json(["folder", "top"])
    if not ok:
        return None, f"failed to list top-level Looker folders: {err}"
    target = folder.strip().lower()
    if isinstance(payload, list):
        for f in payload:
            if isinstance(f, dict) and str(f.get("name", "")).strip().lower() == target:
                return str(f.get("id")), ""
        if target == "shared":
            for f in payload:
                if isinstance(f, dict) and f.get("is_shared_root"):
                    return str(f.get("id")), ""
    elif isinstance(payload, str):
        shared_fallback: str | None = None
        for ln in payload.splitlines():
            if not ln.strip().startswith("|"):
                continue
            cols = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cols) >= 3 and cols[0].isdigit():
                fid, fname, is_shared = cols[0], cols[1], cols[2].lower() == "true"
                if fname.lower() == target:
                    return fid, ""
                if is_shared and not shared_fallback:
                    shared_fallback = fid
        if target == "shared" and shared_fallback:
            return shared_fallback, ""
    return None, f"Looker folder '{folder}' not found"


def deploy_looker(
    ws: Workspace,
    product_id: str,
    report: Report,
    *,
    env: str | None = None,
    project_id: str | None = None,
    profile: str | None = None,
    host: str | None = None,
    port: str | None = None,
    folder: str = "Shared",
    update_connection: bool = False,
    verify_queries: bool = True,
) -> dict[str, Any]:
    report.head(f"looker · deploy — {product_id}", gate="looker")
    cli_bin = find_looker_cli()
    if not cli_bin:
        report.fail("looker-cli is not installed on PATH (install looker-cli and run `looker-cli session login --oauth`)")
        return {}

    p = resolve_target_product(ws, product_id, env=env, project_id=project_id)
    b = build(p)
    if not b.ok:
        for prob in b.problems:
            report.fail(prob)
        return {}

    lookml_files = {
        k.removeprefix("semantic_layer/lookml/"): v
        for k, v in sorted(b.files.items())
        if k.startswith("semantic_layer/lookml/")
    }
    if not lookml_files:
        report.fail(f"product '{product_id}' does not emit semantic_layer/lookml/ artefacts")
        return {}

    spec = json.loads(b.files["semantic-layer.json"])
    looker_cfg = spec.get("looker") or {}
    lkr_project = looker_cfg.get("project_name") or p.id
    conn_name = looker_cfg.get("connection") or f"bigquery_{p.id}"
    auth_mode = looker_cfg.get("auth_mode") or "oauth"
    gcp_proj = ((p.manifest.get("deployment") or {}).get("gcp_project") or "").strip()
    if not gcp_proj:
        report.fail(
            "deployment.gcp_project is unset; pass --project-id <gcp_project>, set DPF_GCP_PROJECT, or configure deployment.environments"
        )
        return {}
    dataset = _primary_dataset(p, spec)

    cli = LookerCliRunner(cli_bin, profile=profile, host=host, port=port)
    ok_me, me_obj, me_err = cli.run_json(["user", "me"])
    if not ok_me:
        prof_hint = f" --profile {profile}" if profile else ""
        report.fail(
            f"looker-cli is not authenticated ({me_err}); run `looker-cli{prof_hint} session login --oauth`"
        )
        return {}
    user_label = me_obj.get("email") or me_obj.get("display_name") or "authenticated user" if isinstance(me_obj, dict) else "authenticated user"
    report.ok(f"authenticated to Looker as {user_label}")

    # 1. Connection check / upsert
    ok_conn, _, _ = cli.run_json(["connection", "cat", conn_name])
    if not ok_conn or update_connection:
        has_agg = any(e.get("aggregate_tables") for e in (spec.get("explores") or [])) or bool(looker_cfg.get("allow_pdt"))
        conn_doc: dict[str, Any] = {
            "name": conn_name,
            "dialect_name": "bigquery_standard_sql",
            "host": gcp_proj,
            "database": dataset,
            "schema": dataset,
            "uses_application_default_credentials": auth_mode == "service_account",
        }
        if has_agg:
            dep_ds = (p.manifest.get("deployment") or {}).get("datasets") or {}
            conn_doc["temp_dataset"] = dep_ds.get("control") or dataset
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(conn_doc, tf, indent=2)
            conn_tmp = tf.name
        try:
            imp_args = ["connection", "import", conn_tmp] + (["--force"] if ok_conn else [])
            ok_imp, _, imp_err = cli.run_json(imp_args)
            if not ok_imp:
                report.fail(f"failed to import BigQuery connection '{conn_name}' (-> {gcp_proj}.{dataset}): {imp_err}")
                return {}
            report.ok(f"configured BigQuery connection '{conn_name}' -> {gcp_proj}.{dataset} ({auth_mode})")
        finally:
            Path(conn_tmp).unlink(missing_ok=True)
    else:
        report.ok(f"verified BigQuery connection '{conn_name}'")

    # 1b. Provision required Looker user attributes for policy-tag access grants (service_account mode)
    if auth_mode == "service_account":
        from dpf.generate.render import snake_id

        seen_attrs: set[str] = set()
        for c in spec.get("cubes") or []:
            for pt in c.get("policy_tags") or []:
                tag = pt.get("tag")
                if not tag:
                    continue
                attr_name = snake_id("dpf", tag, "access")
                if attr_name in seen_attrs:
                    continue
                seen_attrs.add(attr_name)
                ok_attr, _, _ = cli.run_json(["attribute", "cat", attr_name])
                if not ok_attr:
                    ok_ca, _, a_err = cli.run_json([
                        "attribute", "create", attr_name, f"DPF {tag} Access",
                        "--default-value", "masked",
                        "--can-edit=false",
                        "--force",
                    ])
                    if not ok_ca:
                        report.fail(f"failed to create Looker user attribute '{attr_name}': {a_err}")
                        return {}
                    report.ok(f"created Looker user attribute '{attr_name}' (default: masked)")

    # 2. Project check / bare Git setup
    ok_proj, proj_obj, _ = cli.run_json(["project", "cat", lkr_project], dev_session=True)
    if not ok_proj:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump({"name": lkr_project}, tf)
            proj_tmp = tf.name
        try:
            ok_create, _, c_err = cli.run_json(["project", "import", proj_tmp], dev_session=True)
            if not ok_create:
                report.fail(f"failed to create Looker project '{lkr_project}': {c_err}")
                return {}
            report.ok(f"created Looker project '{lkr_project}'")
        finally:
            Path(proj_tmp).unlink(missing_ok=True)
        ok_proj, proj_obj, _ = cli.run_json(["project", "cat", lkr_project], dev_session=True)

    uses_git = bool(isinstance(proj_obj, dict) and proj_obj.get("uses_git"))
    if not uses_git:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump({"git_service_name": "bare"}, tf)
            git_tmp = tf.name
        try:
            ok_git, _, g_err = cli.run_json(["project", "update", lkr_project, git_tmp], dev_session=True)
            if ok_git:
                uses_git = True
                report.ok(f"configured bare Git repository for Looker project '{lkr_project}'")
            else:
                report.warn(f"could not configure bare Git on '{lkr_project}' ({g_err}); continuing in dev workspace")
        finally:
            Path(git_tmp).unlink(missing_ok=True)

    # 3. Upload LookML directories and files
    subdirs = sorted({rel.split("/", 1)[0] for rel in lookml_files if "/" in rel})
    for dname in subdirs:
        cli.run(["project", "directory", "create", lkr_project, dname], dev_session=True)

    with tempfile.TemporaryDirectory() as tdir:
        troot = Path(tdir)
        for rel, content in lookml_files.items():
            local_f = troot / rel
            local_f.parent.mkdir(parents=True, exist_ok=True)
            local_f.write_text(content, encoding="utf-8")
            proc_up = cli.run(["project", "file", "update", lkr_project, rel, str(local_f)], dev_session=True)
            if proc_up.returncode != 0:
                proc_cr = cli.run(["project", "file", "create", lkr_project, rel, str(local_f)], dev_session=True)
                if proc_cr.returncode != 0:
                    err_msg = (proc_cr.stderr or proc_cr.stdout or proc_up.stderr or "").strip()
                    report.fail(f"failed to sync '{rel}' to Looker project '{lkr_project}': {err_msg}")
                    return {}
    report.ok(f"synced {len(lookml_files)} LookML file(s) to '{lkr_project}'")

    # 4. Server-side LookML validation
    ok_val, val_obj, val_err = cli.run_json(["api", "project", "validate_project", lkr_project], dev_session=True)
    if not ok_val:
        report.fail(f"Looker validate_project failed on '{lkr_project}': {val_err}")
        return {}
    val_errors = (val_obj.get("errors") or []) if isinstance(val_obj, dict) else []
    fatal_vals = [e for e in val_errors if str(e.get("severity", "error")).lower() in ("fatal", "error")]
    if fatal_vals:
        for fe in fatal_vals[:10]:
            report.fail(
                f"LookML error in {fe.get('file_path', lkr_project)}:{fe.get('line_number', '?')}: {fe.get('message')}"
            )
        return {}
    report.ok(f"Looker validate_project passed with 0 errors ({len(val_errors)} warning(s))")

    # 5. Register LookML model connection allowlist, then commit and deploy to production
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(
            {
                "name": p.id,
                "project_name": lkr_project,
                "allowed_db_connection_names": [conn_name],
            },
            tf,
            indent=2,
        )
        model_tmp = tf.name
    try:
        ok_mod, _, mod_err = cli.run_json(["model", "import", model_tmp, "--force"], dev_session=True)
        if ok_mod:
            report.ok(f"registered LookML model '{p.id}' -> connection '{conn_name}'")
        else:
            report.warn(f"model registration note for '{p.id}': {mod_err}")
    finally:
        Path(model_tmp).unlink(missing_ok=True)

    if uses_git:
        cli.run(
            ["project", "commit", lkr_project, "-m", f"dpf looker deploy {p.id} ({b.digest[:19]})"],
            dev_session=True,
        )
        proc_dep = cli.run(["project", "deploy", lkr_project], dev_session=True)
        if proc_dep.returncode == 0:
            report.ok(f"deployed Looker project '{lkr_project}' to production")
        else:
            report.fail(f"Looker project deploy failed: {(proc_dep.stderr or proc_dep.stdout or '').strip()}")
            cli.run(["session", "update", "production"], dev_session=False)
            return {}
        cli.run(["session", "update", "production"], dev_session=False)

    # 6. Import / sync LookML dashboards as UDDs
    folder_id, f_err = _resolve_folder_id(cli, folder)
    if not folder_id:
        report.fail(f_err)
        return {}

    base_url = resolve_looker_base_url(profile=profile, host_override=host)
    dashboards_out: list[dict[str, Any]] = []
    for dash in spec.get("dashboards") or []:
        dname = dash["name"]
        lookml_id = f"{p.id}::{dname}"
        ok_imp_d, imp_obj, d_err = cli.run_json(
            ["dashboard", "import", "lookml", lookml_id, folder_id, "--sync", "--plain"],
            dev_session=not uses_git,
        )
        udd_id: str | None = None
        if ok_imp_d:
            if isinstance(imp_obj, dict) and imp_obj.get("id"):
                udd_id = str(imp_obj["id"])
            elif isinstance(imp_obj, (int, str)) and str(imp_obj).strip():
                raw_id = str(imp_obj).strip().splitlines()[-1].strip()
                if raw_id:
                    udd_id = raw_id
        if not udd_id:
            report.fail(f"failed to import/sync LookML dashboard '{lookml_id}' into folder {folder_id}: {d_err}")
            return {}
        dash_url = f"{base_url}/dashboards/{udd_id}" if base_url else f"/dashboards/{udd_id}"
        report.ok(f"synced dashboard '{dname}' -> UDD {udd_id} ({dash_url})")
        dashboards_out.append({"name": dname, "udd_id": udd_id, "url": dash_url})

    if verify_queries and dashboards_out:
        verify_looker_dashboards(cli, dashboards_out, report, dev_session=not uses_git)

    return {
        "product_id": p.id,
        "looker_project": lkr_project,
        "connection": conn_name,
        "gcp_project": gcp_proj,
        "dataset": dataset,
        "dashboards": dashboards_out,
    }


def verify_looker_dashboards(
    cli: LookerCliRunner,
    dashboards: list[dict[str, Any]],
    report: Report,
    *,
    dev_session: bool = False,
) -> list[dict[str, Any]]:
    tile_results: list[dict[str, Any]] = []
    for d in dashboards:
        udd_id = str(d["udd_id"])
        ok_cat, cat_obj, cat_err = cli.run_json(
            ["dashboard", "cat", udd_id],
            dev_session=dev_session,
        )
        if not ok_cat or not isinstance(cat_obj, dict):
            report.fail(f"failed to inspect elements of dashboard {udd_id}: {cat_err}")
            continue
        elems = cat_obj.get("dashboard_elements") or []
        for el in elems:
            rm = el.get("result_maker") if isinstance(el.get("result_maker"), dict) else {}
            qid = (
                el.get("query_id")
                or (el.get("query") or {}).get("id")
                or rm.get("query_id")
                or ((rm.get("query") or {}).get("id") if isinstance(rm.get("query"), dict) else None)
            )
            if not qid:
                continue
            title = el.get("title") or f"query:{qid}"
            ok_q, q_rows, q_err = cli.run_json(["query", "runquery", str(qid), "--format", "json"], dev_session=dev_session, timeout=120)
            if not ok_q:
                report.fail(f"tile '{title}' (query {qid}) failed in BigQuery/Looker: {q_err}")
                tile_results.append({"dashboard": d["name"], "tile": title, "query_id": qid, "status": "failed", "error": q_err})
                continue
            if isinstance(q_rows, dict) and (q_rows.get("looker_error") or q_rows.get("errors")):
                err_txt = str(q_rows.get("looker_error") or q_rows.get("errors"))
                report.fail(f"tile '{title}' (query {qid}) returned SQL error: {err_txt}")
                tile_results.append({"dashboard": d["name"], "tile": title, "query_id": qid, "status": "failed", "error": err_txt})
                continue
            row_count = len(q_rows) if isinstance(q_rows, list) else 1
            report.ok(f"tile '{title}' (query {qid}): {row_count} row(s) returned")
            tile_results.append({"dashboard": d["name"], "tile": title, "query_id": qid, "status": "passed", "rows": row_count})
    return tile_results


def verify_looker(
    ws: Workspace,
    product_id: str,
    report: Report,
    *,
    env: str | None = None,
    project_id: str | None = None,
    profile: str | None = None,
    host: str | None = None,
    port: str | None = None,
    folder: str = "Shared",
) -> dict[str, Any]:
    report.head(f"looker · verify — {product_id}", gate="looker")
    cli_bin = find_looker_cli()
    if not cli_bin:
        report.fail("looker-cli is not installed on PATH")
        return {}
    p = resolve_target_product(ws, product_id, env=env, project_id=project_id)
    b = build(p)
    if not b.ok:
        for prob in b.problems:
            report.fail(prob)
        return {}
    spec = json.loads(b.files["semantic-layer.json"])
    lkr_project = ((spec.get("looker") or {}).get("project_name")) or p.id
    cli = LookerCliRunner(cli_bin, profile=profile, host=host, port=port)

    # Validate against production workspace (never mask undeployed dev-branch LookML)
    cli.run(["session", "update", "production"], dev_session=False)
    ok_val, val_obj, val_err = cli.run_json(["api", "project", "validate_project", lkr_project], dev_session=False)
    if not ok_val:
        report.fail(f"Looker validate_project failed on '{lkr_project}': {val_err}")
        return {}
    val_errors = (val_obj.get("errors") or []) if isinstance(val_obj, dict) else []
    fatal_vals = [e for e in val_errors if str(e.get("severity", "error")).lower() in ("fatal", "error")]
    if fatal_vals:
        for fe in fatal_vals[:10]:
            report.fail(
                f"LookML error in {fe.get('file_path', lkr_project)}:{fe.get('line_number', '?')}: {fe.get('message')}"
            )
        return {}
    report.ok(f"Looker validate_project passed on '{lkr_project}' with 0 errors")

    base_url = resolve_looker_base_url(profile=profile, host_override=host)
    dashboards: list[dict[str, Any]] = []
    folder_id, _ = _resolve_folder_id(cli, folder)
    dash_list: list[dict[str, Any]] = []
    if folder_id:
        ok_fcat, fcat_obj, _ = cli.run_json(["folder", "cat", folder_id], dev_session=False)
        if ok_fcat and isinstance(fcat_obj, dict):
            dash_list = list(fcat_obj.get("dashboards") or [])
    for dash in spec.get("dashboards") or []:
        dname = dash["name"]
        title = dash["title"]
        match = next(
            (
                item for item in dash_list
                if isinstance(item, dict)
                and (
                    item.get("lookml_link_id") == f"{p.id}::{dname}"
                    or str(item.get("title", "")).strip() == title
                )
            ),
            None,
        )
        if not match or not match.get("id"):
            report.fail(f"dashboard '{dname}' is not imported in Looker yet (run `dpf looker deploy {product_id}`)")
            continue
        uid = str(match["id"])
        dashboards.append({
            "name": dname,
            "udd_id": uid,
            "url": f"{base_url}/dashboards/{uid}" if base_url else f"/dashboards/{uid}",
        })

    tiles = verify_looker_dashboards(cli, dashboards, report, dev_session=False) if dashboards else []
    return {"product_id": p.id, "looker_project": lkr_project, "dashboards": dashboards, "tiles": tiles}
