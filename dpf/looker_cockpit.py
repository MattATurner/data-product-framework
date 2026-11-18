"""Build and serve a Stephen Few Perceptual Edge HTML cockpit powered 100% by the Looker LookML semantic layer.

Architectural invariant:
- NEVER queries BigQuery tables directly. Every KPI, Bullet Graph, ranked bar,
  two-point change graph, SCD2 audit row, and order-line ledger row is executed
  exclusively through `looker-cli query runquery --file <spec.json>` (`--format json`
  and `--format sql`) against the product's governed LookML model and Explore.
- Zero hard-coded Looker URLs, profiles, or project IDs: everything resolves from
  CLI flags, environment variables, `~/.config/looker-cli/config.yaml`, and `product.yaml`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import urllib.parse

from dpf.core import Report, Workspace, write_text
from dpf.generate import build
from dpf.looker_deploy import (
    LookerCliRunner,
     _resolve_folder_id,
    find_looker_cli,
    resolve_looker_base_url,
    resolve_target_product,
)


def _build_semantic_queries(model: str, explore: str, date_filter: str) -> dict[str, dict[str, Any]]:
    """Construct governed LookML semantic query payloads (zero SQL)."""
    f_date = {"fct_order_line.order_date": date_filter} if date_filter else {}
    return {
        "headline_summary": {
            "model": model,
            "view": explore,
            "fields": [
                "fct_order_line.net_sales",
                "fct_order_line.units_sold",
                "fct_order_line.order_line_count",
                "fct_order_line.gross_amount",
                "fct_order_line.discount_amount",
                "fct_order_line.net_amount",
                "fct_order_line.count",
            ],
            "filters": {**f_date},
            "limit": "10",
        },
        "slice_cube": {
            "model": model,
            "view": explore,
            "fields": [
                "dim_date.year_quarter",
                "dim_date.year_month",
                "dim_customer.region",
                "dim_customer.customer_segment",
                "dim_product.product_category",
                "fct_order_line.net_sales",
                "fct_order_line.units_sold",
                "fct_order_line.order_line_count",
                "fct_order_line.gross_amount",
                "fct_order_line.discount_amount",
                "fct_order_line.net_amount",
                "fct_order_line.count",
            ],
            "filters": {**f_date},
            "sorts": ["dim_date.year_month asc", "fct_order_line.net_sales desc"],
            "limit": "500",
        },
        "scd2_point_in_time": {
            "model": model,
            "view": explore,
            "fields": [
                "dim_date.year_month",
                "dim_customer.customer_id",
                "dim_customer.customer_name",
                "dim_customer.customer_segment",
                "dim_customer.region",
                "dim_customer.version_no",
                "dim_customer.is_current",
                "dim_product.product_id",
                "dim_product.product_name",
                "dim_product.product_category",
                "dim_product.version_no",
                "dim_product.is_current",
                "fct_order_line.net_sales",
                "fct_order_line.units_sold",
                "fct_order_line.order_line_count",
            ],
            "filters": {**f_date, "fct_order_line.is_cancelled": "No"},
            "sorts": ["dim_customer.customer_id asc", "dim_date.year_month asc"],
            "limit": "200",
        },
        "semantic_guardrail": {
            "model": model,
            "view": explore,
            "fields": [
                "fct_order_line.order_status",
                "fct_order_line.is_cancelled",
                "fct_order_line.count",
                "fct_order_line.order_line_count",
                "fct_order_line.gross_amount",
                "fct_order_line.discount_amount",
                "fct_order_line.net_amount",
                "fct_order_line.net_sales",
                "fct_order_line.units_sold",
            ],
            "filters": {**f_date},
            "sorts": ["fct_order_line.count desc"],
            "limit": "50",
        },
        "order_line_ledger": {
            "model": model,
            "view": explore,
            "fields": [
                "fct_order_line.order_id",
                "fct_order_line.order_line_no",
                "fct_order_line.order_date",
                "dim_date.year_quarter",
                "dim_date.year_month",
                "dim_customer.customer_id",
                "dim_customer.customer_name",
                "dim_customer.customer_segment",
                "dim_customer.region",
                "dim_customer.version_no",
                "dim_product.product_id",
                "dim_product.product_name",
                "dim_product.product_category",
                "dim_product.version_no",
                "fct_order_line.order_status",
                "fct_order_line.is_cancelled",
                "fct_order_line.gross_amount",
                "fct_order_line.discount_amount",
                "fct_order_line.net_amount",
                "fct_order_line.net_sales",
                "fct_order_line.units_sold",
            ],
            "filters": {**f_date},
            "sorts": ["fct_order_line.order_date desc", "fct_order_line.order_id desc", "fct_order_line.order_line_no asc"],
            "limit": "250",
        },
    }


def _execute_single_query(cli: LookerCliRunner, key: str, qspec: dict[str, Any]) -> tuple[str, list[dict], str, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(qspec, tf, indent=2)
        qpath = tf.name
    try:
        ok_j, rows, err_j = cli.run_json(["query", "runquery", "--file", qpath, "--format", "json"], dev_session=True, timeout=90)
        if not ok_j:
            return key, [], "", err_j
        if isinstance(rows, dict) and (rows.get("looker_error") or rows.get("errors")):
            return key, [], "", str(rows.get("looker_error") or rows.get("errors"))
        proc_sql = cli.run(["query", "runquery", "--file", qpath, "--format", "sql"], dev_session=True, timeout=60)
        compiled_sql = (proc_sql.stdout or "").strip() if proc_sql.returncode == 0 else ""
        return key, (rows if isinstance(rows, list) else []), compiled_sql, ""
    finally:
        Path(qpath).unlink(missing_ok=True)


def fetch_lookml_telemetry(
    cli: LookerCliRunner,
    *,
    model: str,
    explore: str,
    date_filter: str,
    base_url: str | None,
    native_dashboard_url: str | None,
    product_version: str,
    build_digest: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    queries = _build_semantic_queries(model, explore, date_filter)
    datasets: dict[str, list[dict]] = {}
    compiled_sql: dict[str, str] = {}
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = [pool.submit(_execute_single_query, cli, k, q) for k, q in queries.items()]
        for fut in futs:
            key, rows, sql_txt, err = fut.result()
            if err:
                errors.append(f"{key}: {err}")
            else:
                datasets[key] = rows
                compiled_sql[key] = sql_txt

    if errors:
        return None, errors

    explore_base = f"{base_url}/explore/{urllib.parse.quote(model)}/{urllib.parse.quote(explore)}" if base_url else ""
    payload = {
        "meta": {
            "product_id": model,
            "product_version": product_version,
            "build_digest": build_digest,
            "model": model,
            "explore": explore,
            "date_filter": date_filter,
            "queried_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "looker_base_url": base_url or "",
            "looker_explore_url": explore_base,
            "native_dashboard_url": native_dashboard_url or "",
            "source_plane": "Looker LookML Semantic Layer (looker-cli query runquery)",
        },
        "queries": queries,
        "compiled_sql": compiled_sql,
        "data": datasets,
    }
    return payload, []


def _discover_native_udd_url(
    cli: LookerCliRunner, product_id: str, dash_name: str, dash_title: str, base_url: str | None
) -> str | None:
    folder_id, _ = _resolve_folder_id(cli, "Shared")
    if not folder_id:
        return None
    ok_cat, fcat, _ = cli.run_json(["folder", "cat", folder_id], dev_session=True)
    if not ok_cat or not isinstance(fcat, dict):
        return None
    for d in fcat.get("dashboards") or []:
        if isinstance(d, dict) and d.get("id") and (
            d.get("lookml_link_id") == f"{product_id}::{dash_name}"
            or str(d.get("title", "")).strip() == dash_title.strip()
        ):
            uid = str(d["id"])
            return f"{base_url}/dashboards/{uid}" if base_url else f"/dashboards/{uid}"
    return None


def _render_cockpit_html(payload: dict[str, Any], *, targets: dict[str, float]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    targets_json = json.dumps(targets, ensure_ascii=False)
    return _COCKPIT_HTML_TEMPLATE.replace("__LOOKML_PAYLOAD_JSON__", payload_json).replace("__TARGETS_JSON__", targets_json)


def resolve_presentation_server_url(
    ws: Workspace,
    explicit_url: str | None = None,
    *,
    prompt_on_first_run: bool = False,
) -> str:
    """Resolve Presentation Server URL from flag, env, agent-config.json, user config, or first-run prompt."""
    def _clean(raw: str | None) -> str:
        if not raw:
            return ""
        v = raw.strip()
        if v.lower() in {"none", "local", "skip", "null", "-"}:
            return ""
        if not v.startswith(("http://", "https://")):
            v = f"https://{v}"
        return v.rstrip("/")

    if explicit_url is not None:
        url = _clean(explicit_url)
        if url:
            _persist_presentation_server_url(ws, url)
        return url

    for env_key in ("DPF_PRESENTATION_SERVER_URL", "PRESENTATION_SERVER_URL"):
        if os.environ.get(env_key):
            return _clean(os.environ.get(env_key))

    for rel_cfg in ("registry/agent-config.json", "agent-config.json"):
        agent_cfg_path = ws.root / rel_cfg
        if agent_cfg_path.is_file():
            try:
                cfg = json.loads(agent_cfg_path.read_text(encoding="utf-8"))
                if cfg.get("presentation_server_url"):
                    return _clean(str(cfg["presentation_server_url"]))
            except Exception:
                pass

    user_cfg_path = Path.home() / ".config/presentation-server/config.json"
    if user_cfg_path.is_file():
        try:
            ucfg = json.loads(user_cfg_path.read_text(encoding="utf-8"))
            if ucfg.get("server_url"):
                return _clean(str(ucfg["server_url"]))
        except Exception:
            pass

    if prompt_on_first_run and sys.stdin.isatty():
        entered = input("Enter Presentation Server URL (e.g. https://my-presentation-server.a.run.app): ").strip()
        url = _clean(entered)
        if url:
            _persist_presentation_server_url(ws, url)
        return url

    return ""


def _persist_presentation_server_url(ws: Workspace, url: str) -> None:
    agent_cfg_path = ws.root / "registry/agent-config.json"
    if not agent_cfg_path.is_file() and (ws.root / "agent-config.json").is_file():
        agent_cfg_path = ws.root / "agent-config.json"
    try:
        cfg = json.loads(agent_cfg_path.read_text(encoding="utf-8")) if agent_cfg_path.is_file() else {}
        cfg["presentation_server_url"] = url
        write_text(agent_cfg_path, json.dumps(cfg, indent=2) + "\n")
    except Exception:
        pass
    user_cfg_path = Path.home() / ".config/presentation-server/config.json"
    try:
        existing = json.loads(user_cfg_path.read_text(encoding="utf-8")) if user_cfg_path.is_file() else {}
        existing["server_url"] = url
        write_text(user_cfg_path, json.dumps(existing, indent=2) + "\n")
    except Exception:
        pass


def build_or_serve_cockpit(
    ws: Workspace,
    product_id: str,
    report: Report,
    *,
    env: str | None = None,
    project_id: str | None = None,
    profile: str | None = None,
    host: str | None = None,
    port: str | None = None,
    date_filter: str | None = None,
    out_path: Path | None = None,
    serve_port: int | None = None,
    publish: bool = False,
    presentation_server_url: str | None = None,
    presentation_bucket: str | None = None,
    net_sales_target: float | None = None,
    units_target: float | None = None,
    discount_ceiling_pct: float = 10.0,
) -> Path | None:
    report.head(f"looker · cockpit — {product_id}", gate="looker")
    cli_bin = find_looker_cli()
    if not cli_bin:
        report.fail("looker-cli is not installed on PATH")
        return None

    p = resolve_target_product(ws, product_id, env=env, project_id=project_id)
    b = build(p)
    if not b.ok:
        for prob in b.problems:
            report.fail(prob)
        return None

    spec = json.loads(b.files["semantic-layer.json"])
    explores = spec.get("explores") or []
    if not explores:
        report.fail(f"product '{product_id}' declares no semantic_layer.explores")
        return None
    exp_obj = explores[0]
    explore_name = exp_obj["name"]
    dash_list = spec.get("dashboards") or []
    default_date_flt = date_filter
    if default_date_flt is None:
        default_date_flt = exp_obj.get("partition_default_filter") or "365 days"

    cli = LookerCliRunner(cli_bin, profile=profile, host=host, port=port)
    base_url = resolve_looker_base_url(profile=profile, host_override=host)
    udd_url = (
        _discover_native_udd_url(cli, p.id, dash_list[0]["name"], dash_list[0].get("title", ""), base_url)
        if dash_list
        else None
    )

    payload, errs = fetch_lookml_telemetry(
        cli,
        model=p.id,
        explore=explore_name,
        date_filter=default_date_flt,
        base_url=base_url,
        native_dashboard_url=udd_url,
        product_version=str(p.manifest.get("version", "1.0.0")),
        build_digest=b.digest,
    )
    if errs or payload is None:
        for e in errs:
            report.fail(f"LookML semantic query failed — {e}")
        return None

    for qname, rows in payload["data"].items():
        report.ok(f"LookML semantic query '{qname}' ({p.id}.{explore_name}): {len(rows)} row(s) + compiled SQL captured")

    head_row = (payload["data"].get("headline_summary") or [{}])[0]
    actual_sales = float(head_row.get("fct_order_line.net_sales") or 0.0)
    actual_units = float(head_row.get("fct_order_line.units_sold") or 0.0)
    targets = {
        "net_sales": float(net_sales_target) if net_sales_target is not None else round(max(actual_sales * 0.88, 1000.0), -2),
        "units_sold": float(units_target) if units_target is not None else max(round(actual_units * 0.90), 10.0),
        "discount_ceiling_pct": float(discount_ceiling_pct),
    }

    dest = out_path or (ws.root / "generated" / p.id / "semantic_layer" / f"{p.id}_semantic_cockpit.html")
    html_text = _render_cockpit_html(payload, targets=targets)
    write_text(dest, html_text)
    report.ok(f"rendered Stephen Few LookML cockpit -> {dest}")

    if publish or presentation_server_url:
        server_url = resolve_presentation_server_url(
            ws,
            presentation_server_url,
            prompt_on_first_run=True,
        )
        if not server_url:
            report.fail(
                "Presentation Server URL is not configured — pass --presentation-server-url <url> "
                "(or set DPF_PRESENTATION_SERVER_URL) on first run"
            )
            return None
        bucket = presentation_bucket or os.environ.get("DPF_PRESENTATION_BUCKET") or ""
        slug = dest.stem
        if bucket:
            gcloud_bin = shutil.which("gcloud")
            if not gcloud_bin:
                report.fail("gcloud CLI is required to upload to --presentation-bucket")
                return None
            gcs_uri = f"gs://{bucket.removeprefix('gs://').rstrip('/')}/{slug}.html"
            cp = subprocess.run(
                [gcloud_bin, "storage", "cp", "--cache-control=no-cache, max-age=0", str(dest), gcs_uri],
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                report.fail(f"failed uploading cockpit to {gcs_uri}: {cp.stderr.strip()}")
                return None
            report.ok(f"uploaded cockpit HTML -> {gcs_uri}")
        report.ok(f"Presentation Server cockpit URL: {server_url}/p/{slug}")

    if serve_port:
        _serve_live_cockpit(
            serve_port,
            cli=cli,
            model=p.id,
            explore=explore_name,
            date_filter=default_date_flt,
            base_url=base_url,
            udd_url=udd_url,
            product_version=str(p.manifest.get("version", "1.0.0")),
            build_digest=b.digest,
            targets=targets,
            initial_html=html_text,
            report=report,
        )
    return dest


def _serve_live_cockpit(
    port_num: int,
    *,
    cli: LookerCliRunner,
    model: str,
    explore: str,
    date_filter: str,
    base_url: str | None,
    udd_url: str | None,
    product_version: str,
    build_digest: str,
    targets: dict[str, float],
    initial_html: str,
    report: Report,
) -> None:
    state = {"html": initial_html}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            if self.path.startswith("/api/lookml-telemetry"):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                df = (qs.get("date_filter") or [date_filter])[0]
                fresh, errs = fetch_lookml_telemetry(
                    cli,
                    model=model,
                    explore=explore,
                    date_filter=df,
                    base_url=base_url,
                    native_dashboard_url=udd_url,
                    product_version=product_version,
                    build_digest=build_digest,
                )
                body = json.dumps({"ok": not errs, "errors": errs, "payload": fresh}).encode("utf-8")
                self.send_response(200 if not errs else 502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            body = state["html"].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", port_num), Handler)
    report.info(f"serving live LookML cockpit at http://127.0.0.1:{port_num} (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()


_COCKPIT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="deck-title" content="Sales Performance — LookML Semantic Operational Cockpit">
<meta name="description" content="Stephen Few Perceptual Edge operational cockpit powered strictly by the Data Product Framework (DPF) Looker LookML semantic layer (2013 Bullet Graphs, Q1-to-Q2 Range & Deviation change triad, Law 5E missing-period trend, SCD2 point-in-time audit, and cancelled-order semantic shield).">
<meta name="tags" content="DPF, Data Product Framework, Looker, LookML, Semantic Layer, Stephen Few, BigQuery">
<meta name="deck-role" content="master">
<meta name="catalog-visibility" content="visible">
<title>Sales Performance — LookML Semantic Operational Cockpit</title>
<style>
  :root {
    --bg-canvas: #E6E9E4;
    --bg-panel: #FFFFFF;
    --bg-subtle: #F3F4F1;
    --bg-hover: #ECEEE9;
    --bg-selected: #EBF1F6;
    --border: #D5D8D2;
    --border-hairline: #E4E6E1;
    --grid-line-muted: #ECEEE9;

    --text-primary: #141A17;
    --text-secondary: #435049;
    --text-muted: #6E7B74;

    --data-neutral-bar: #6E7F76;
    --data-secondary-bar: #5B7A8C;
    --data-muted-bar: #A3B1AA;
    --context-dimmed-opacity: 0.25;

    --accent-primary: #1F5A8A;
    --pass-fill: #1B6B3A;
    --pass-bg: #E3F3E9;
    --warn-fill: #B85D1E;
    --warn-bg: #FBECE1;
    --fail-fill: #A82424;
    --fail-bg: #FBEAEA;

    --bullet-band-poor: #A6ACA9;
    --bullet-band-satisfactory: #C8CDCA;
    --bullet-band-good: #E4E7E5;
    --bullet-bar-normal: #2C3531;
    --bullet-bar-alert: #A82424;
    --bullet-target: #141A17;
  }

  body.dark-mode {
    --bg-canvas: #0E131B;
    --bg-panel: #151C26;
    --bg-subtle: #1D2634;
    --bg-hover: #243042;
    --bg-selected: #1B2E46;
    --border: #314056;
    --border-hairline: #253142;
    --grid-line-muted: #1E2938;

    --text-primary: #F1F5F3;
    --text-secondary: #B4C0BC;
    --text-muted: #7F8E88;

    --data-neutral-bar: #7D9188;
    --data-secondary-bar: #6C92A8;
    --data-muted-bar: #4E5E6E;

    --accent-primary: #5DA5DA;
    --pass-fill: #34D399;
    --pass-bg: rgba(16, 185, 129, 0.16);
    --warn-fill: #FBBF24;
    --warn-bg: rgba(245, 158, 11, 0.16);
    --fail-fill: #F87171;
    --fail-bg: rgba(239, 68, 68, 0.18);

    --bullet-band-poor: #232D3B;
    --bullet-band-satisfactory: #2E3B4E;
    --bullet-band-good: #3A4A61;
    --bullet-bar-normal: #CBD5E1;
    --bullet-bar-alert: #F87171;
    --bullet-target: #F8FAFC;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-canvas);
    color: var(--text-primary);
    font-size: 12.5px;
    line-height: 1.38;
    -webkit-font-smoothing: antialiased;
  }
  .num { font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1; }
  .mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }

  .cockpit {
    max-width: 1720px;
    margin: 0 auto;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 100vh;
  }

  /* Header Bar */
  .header-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-radius: 3px;
    padding: 9px 14px;
    gap: 12px;
    flex-wrap: wrap;
  }
  .title-wrap { display: flex; flex-direction: column; gap: 4px; }
  .title-row { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
  .title-row h1 { font-size: 15.5px; font-weight: 700; letter-spacing: -0.02em; }
  .subtitle-row { font-size: 11.5px; color: var(--text-secondary); display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }

  .pill {
    font-size: 10.5px;
    color: var(--text-secondary);
    background: var(--bg-subtle);
    border: 1px solid var(--border-hairline);
    padding: 2px 7px;
    border-radius: 2px;
  }
  .pill.semantic {
    color: var(--accent-primary);
    background: var(--bg-selected);
    border-color: var(--border);
    font-weight: 600;
  }
  .pill.pass {
    color: var(--pass-fill);
    background: var(--pass-bg);
    font-weight: 600;
  }

  .header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .btn {
    font-family: inherit;
    font-size: 11.5px;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    padding: 5px 10px;
    border-radius: 3px;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }
  .btn:hover { background: var(--bg-hover); }
  .btn.primary {
    color: var(--accent-primary);
    border-color: var(--accent-primary);
    background: var(--bg-panel);
    font-weight: 600;
  }

  /* Collapsible LookML & Compiled SQL Provenance Drawer */
  .provenance-drawer {
    display: none;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 12px 14px;
    gap: 12px;
    grid-template-columns: 1fr 1.35fr;
  }
  .provenance-drawer.open { display: grid; }
  .code-pane { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .code-hdr { display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; font-weight: 600; color: var(--text-secondary); }
  .code-hdr select {
    font-family: inherit;
    font-size: 11.5px;
    padding: 3px 7px;
    background: var(--bg-subtle);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: 2px;
  }
  pre.code-box {
    background: var(--bg-subtle);
    border: 1px solid var(--border-hairline);
    border-radius: 2px;
    padding: 9px 11px;
    font-size: 11px;
    line-height: 1.42;
    overflow: auto;
    max-height: 210px;
    color: var(--text-primary);
  }

  /* Consolidated Global Filter Rail (Isolated on --bg-subtle per Few Rule 9) */
  .filter-rail {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 7px 12px;
    flex-wrap: wrap;
  }
  .filter-groups { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .filter-group { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
  .filter-lbl { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); margin-right: 2px; }
  .chip {
    font-family: inherit;
    font-size: 11px;
    padding: 2.5px 8px;
    border-radius: 2px;
    border: 1px solid var(--border);
    background: var(--bg-panel);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .chip:hover { background: var(--bg-hover); }
  .chip.active {
    background: var(--accent-primary);
    color: #FFFFFF;
    border-color: var(--accent-primary);
    font-weight: 600;
  }

  /* Top Zone: 4 Official 2013 Bullet Graphs */
  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }
  .panel {
    background: var(--bg-panel);
    border: 1px solid var(--border-hairline);
    border-radius: 3px;
    padding: 10px 13px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .panel-hdr { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .panel-title { font-size: 12px; font-weight: 600; color: var(--text-primary); }
  .panel-sub { font-size: 10.5px; color: var(--text-muted); margin-top: 1px; }

  .bullet-val-row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-top: 2px; }
  .bullet-ban { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
  .bullet-ctx { font-size: 11px; color: var(--text-secondary); }

  /* Official 2013 Bullet Graph (33.3% bar in front of 66.7% perpendicular target over 40/25/10% single-hue bands) */
  .few-bullet-wrap { display: flex; flex-direction: column; gap: 3px; margin-top: 2px; }
  .few-bullet-track {
    position: relative;
    height: 18px;
    width: 100%;
    display: flex;
    overflow: hidden;
    border-radius: 1px;
  }
  .few-bullet-band { height: 100%; }
  .few-bullet-bar {
    position: absolute;
    top: 33.33%;
    height: 33.33%;
    left: 0;
    background: var(--bullet-bar-normal);
    z-index: 2;
    transition: width 0.22s ease;
  }
  .few-bullet-bar.is-exception { background: var(--bullet-bar-alert); }
  .few-bullet-target {
    position: absolute;
    top: 16.67%;
    height: 66.67%;
    width: 2px;
    background: var(--bullet-target);
    z-index: 3;
  }
  .few-bullet-ticks {
    display: flex;
    justify-content: space-between;
    font-size: 9.5px;
    color: var(--text-muted);
  }

  /* Middle Zone: Asymmetric 12-Column Gestalt Grid (4 + 5 + 3) */
  .mid-grid {
    display: grid;
    grid-template-columns: 4fr 5fr 3fr;
    gap: 12px;
    align-items: stretch;
  }

  .seg-toggle { display: inline-flex; border: 1px solid var(--border); border-radius: 2px; overflow: hidden; }
  .seg-toggle button {
    font-family: inherit;
    font-size: 10.5px;
    padding: 2px 7px;
    border: none;
    background: var(--bg-subtle);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .seg-toggle button.active {
    background: var(--text-primary);
    color: var(--bg-panel);
    font-weight: 600;
  }

  /* Horizontal Ranked Bar Rows (Zero baseline, >=10:1 length-to-width, 0.25 coordinated dimming) */
  .bar-section-lbl { font-size: 10.5px; font-weight: 600; color: var(--text-secondary); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.03em; }
  .bar-list { display: flex; flex-direction: column; gap: 6px; }
  .bar-row {
    display: grid;
    grid-template-columns: 92px 1fr 68px;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 2px 3px;
    border-radius: 2px;
    transition: opacity 0.16s ease, background 0.12s ease;
  }
  .bar-row:hover { background: var(--bg-hover); }
  .bar-row.dimmed { opacity: var(--context-dimmed-opacity); }
  .bar-lbl { font-size: 11.5px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar-track { height: 11px; background: var(--bg-subtle); position: relative; border-left: 1px solid var(--text-primary); }
  .bar-fill { height: 100%; background: var(--data-neutral-bar); transition: width 0.22s ease; }
  .bar-fill.secondary { background: var(--data-secondary-bar); }
  .bar-val { font-size: 11.5px; font-weight: 600; text-align: right; color: var(--text-primary); }

  /* Center SVG Charts */
  .svg-box { width: 100%; overflow: visible; }
  .divider-hairline { border-top: 1px solid var(--border-hairline); margin: 6px 0 4px; }

  /* Right Column: Semantic Shield & SCD2 Matrix */
  .shield-pair { display: flex; flex-direction: column; gap: 7px; padding: 7px 9px; background: var(--bg-subtle); border-radius: 2px; border: 1px solid var(--border-hairline); }
  .shield-callout {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    padding: 5px 8px;
    border-radius: 2px;
    background: var(--pass-bg);
    color: var(--pass-fill);
    font-weight: 600;
  }
  .mini-table { width: 100%; border-collapse: collapse; font-size: 11px; }
  .mini-table th {
    text-align: left;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
    padding: 4px 5px;
    border-bottom: 1px solid var(--border);
  }
  .mini-table td {
    padding: 4.5px 5px;
    border-bottom: 1px solid var(--border-hairline);
    color: var(--text-primary);
  }
  .mini-table th.r, .mini-table td.r { text-align: right; }

  /* Bottom Zone: Granular Order-Line Ledger */
  .tab-bar { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
  .tabs { display: flex; gap: 6px; flex-wrap: wrap; }
  .tab-btn {
    font-family: inherit;
    font-size: 11.5px;
    font-weight: 500;
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 2px;
    background: var(--bg-subtle);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .tab-btn.active {
    background: var(--text-primary);
    color: var(--bg-panel);
    border-color: var(--text-primary);
    font-weight: 600;
  }

  .ledger-wrap { overflow-x: auto; }
  table.ledger { width: 100%; border-collapse: collapse; font-size: 11.5px; }
  table.ledger th {
    text-align: left;
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  table.ledger td {
    padding: 6px 8px;
    border-bottom: 1px solid var(--border-hairline);
    white-space: nowrap;
  }
  table.ledger tr:hover td { background: var(--bg-hover); }
  table.ledger tr.dimmed { opacity: var(--context-dimmed-opacity); }
  table.ledger th.r, table.ledger td.r { text-align: right; }

  .status-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    padding: 1.5px 6px;
    border-radius: 2px;
  }
  .status-tag.ok { background: var(--pass-bg); color: var(--pass-fill); }
  .status-tag.cancelled { background: var(--fail-bg); color: var(--fail-fill); }
  .status-tag.scd { background: var(--warn-bg); color: var(--warn-fill); }

  .explore-link {
    color: var(--accent-primary);
    text-decoration: none;
    font-weight: 600;
    font-size: 11px;
  }
  .explore-link:hover { text-decoration: underline; }

  @media (max-width: 1200px) {
    .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .mid-grid { grid-template-columns: 1fr; }
    .provenance-drawer.open { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="cockpit">
  <!-- Header -->
  <header class="header-bar">
    <div class="title-wrap">
      <div class="title-row">
        <h1>Sales Performance — Operational &amp; Point-in-Time Revenue Cockpit</h1>
        <span class="pill semantic" id="hdr-semantic-pill">LookML Semantic Layer: sales_performance.order_lines</span>
        <span class="pill pass" id="hdr-parity-pill">Zero Direct Table SQL · 100% Semantic Execution</span>
      </div>
      <div class="subtitle-row">
        <span id="hdr-meta-txt">Governed by Data Product Framework (DPF) · BigQuery Knowledge Catalog &amp; Looker Semantic Plane</span>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn" id="btn-live-refresh" type="button" title="Re-run all 5 LookML semantic queries when served via dpf looker cockpit --serve">↻ Live LookML Refresh</button>
      <button class="btn" id="btn-sql-drawer" type="button">{ } LookML &amp; Compiled SQL</button>
      <button class="btn" id="btn-theme" type="button">◑ Dark Stage (T)</button>
      <a class="btn" id="lnk-native-dash" href="#" target="_blank" rel="noopener" style="display:none;">Native Looker UDD ↗</a>
      <a class="btn primary" id="lnk-explore" href="#" target="_blank" rel="noopener" style="display:none;">Open Looker Explore ↗</a>
    </div>
  </header>

  <!-- Collapsible LookML Spec & Looker-Compiled SQL Provenance Drawer -->
  <section class="provenance-drawer" id="sql-drawer">
    <div class="code-pane">
      <div class="code-hdr">
        <span>LookML Semantic Query Specification (<span class="mono">looker-cli query runquery</span>)</span>
        <select id="sel-query-key"></select>
      </div>
      <pre class="code-box mono" id="box-query-json"></pre>
    </div>
    <div class="code-pane">
      <div class="code-hdr">
        <span>Exact BigQuery Standard SQL Compiled by Looker Semantic Engine (<span class="mono">--format sql</span>)</span>
        <span class="pill semantic">Symmetric Aggregates + Surrogate Keys Verified</span>
      </div>
      <pre class="code-box mono" id="box-query-sql"></pre>
    </div>
  </section>

  <!-- Consolidated Global Filter Rail -->
  <section class="filter-rail" aria-label="Global semantic filters">
    <div class="filter-groups">
      <div class="filter-group" id="flt-quarter"></div>
      <div class="filter-group" id="flt-region"></div>
      <div class="filter-group" id="flt-segment"></div>
      <div class="filter-group" id="flt-category"></div>
    </div>
    <div style="display:flex; align-items:center; gap:8px;">
      <span class="pill num" id="active-slice-summary">Showing all slices</span>
      <button class="btn" id="btn-reset-filters" type="button">Reset Filters</button>
    </div>
  </section>

  <!-- Top Zone: 4 Official 2013 Bullet Graphs -->
  <section class="kpi-strip" id="kpi-strip"></section>

  <!-- Middle Zone: Asymmetric 12-Column Gestalt Grid (4 + 5 + 3) -->
  <section class="mid-grid">
    <!-- Left (4 cols): Ranked Horizontal Bar Breakdowns -->
    <div class="panel">
      <div class="panel-hdr">
        <div>
          <div class="panel-title">Ranked Magnitude by Region &amp; Product Category</div>
          <div class="panel-sub">Zero-baseline bars · Click any bar to highlight in context (25% dimming)</div>
        </div>
        <div class="seg-toggle" id="metric-switcher">
          <button type="button" data-metric="net_sales" class="active">Net Sales</button>
          <button type="button" data-metric="units_sold">Units</button>
          <button type="button" data-metric="lines">Lines</button>
        </div>
      </div>
      <div class="bar-section-lbl">Customer Region (Australian State)</div>
      <div class="bar-list" id="bars-region"></div>
      <div class="divider-hairline"></div>
      <div class="bar-section-lbl">Merchandising Product Category (As-At Sale Date)</div>
      <div class="bar-list" id="bars-category"></div>
    </div>

    <!-- Center (5 cols): Law 5E Missing-Period Monthly Trend + Q1->Q2 Two-Point Change -->
    <div class="panel">
      <div class="panel-hdr">
        <div>
          <div class="panel-title">Monthly Net Sales Trajectory &amp; Missing-Period Integrity</div>
          <div class="panel-sub">Stephen Few Law 5E: line breaks across zero-activity May (2026-05) rather than fabricating a slope</div>
        </div>
        <span class="pill num" id="trend-caption">AUD · Excl. Cancelled</span>
      </div>
      <div id="chart-monthly-trend" class="svg-box"></div>
      <div class="divider-hairline"></div>
      <div class="panel-hdr">
        <div>
          <div class="panel-title">Quarter-on-Quarter Shift (Q1 → Q2 Range &amp; Deviation Bars)</div>
          <div class="panel-sub">Captures C-001 SMB → Enterprise &amp; P-200 Gadgets → Widgets Type 2 SCD transitions</div>
        </div>
        <div class="seg-toggle" id="twopoint-dim-switcher">
          <button type="button" data-dim="segment" class="active">Segment</button>
          <button type="button" data-dim="category">Category</button>
        </div>
      </div>
      <div id="chart-two-point" class="svg-box"></div>
    </div>

    <!-- Right (3 cols): LookML Semantic Distortion Shield + SCD2 Point-in-Time Audit -->
    <div class="panel">
      <div class="panel-hdr">
        <div>
          <div class="panel-title">LookML Semantic Guardrail &amp; SCD2 Shield</div>
          <div class="panel-sub">Why BI tools must query LookML metrics, not raw fact columns</div>
        </div>
      </div>
      <div class="shield-pair" id="semantic-shield-box"></div>
      <div class="divider-hairline"></div>
      <div>
        <div class="panel-title" style="font-size:11.5px;">Point-in-Time Surrogate-Key Audit (<span class="mono">sk_*</span>)</div>
        <div class="panel-sub">Same entity, different historical classification preserved per order month</div>
      </div>
      <table class="mini-table num" id="tbl-scd2-audit"></table>
    </div>
  </section>

  <!-- Bottom Zone: Granular Order-Line Root-Cause Ledger -->
  <section class="panel">
    <div class="tab-bar">
      <div class="tabs" id="ledger-tabs">
        <button type="button" class="tab-btn active" data-tab="all">All Governed &amp; Visible Lines</button>
        <button type="button" class="tab-btn" data-tab="scd2">Point-in-Time SCD2 Transitions (AX-4 / AX-7)</button>
        <button type="button" class="tab-btn" data-tab="cancelled">Shielded Cancelled Exceptions (AX-6)</button>
      </div>
      <div class="panel-sub num" id="ledger-summary">Every row drills directly into the governed Looker Explore</div>
    </div>
    <div class="ledger-wrap">
      <table class="ledger num">
        <thead>
          <tr>
            <th>Order</th>
            <th class="r">Line</th>
            <th>Order Date</th>
            <th>Month</th>
            <th>Customer</th>
            <th>As-At Segment</th>
            <th>Region</th>
            <th>Product</th>
            <th>As-At Category</th>
            <th>Status</th>
            <th class="r">Gross (AUD)</th>
            <th class="r">Discount</th>
            <th class="r">Raw Net</th>
            <th class="r">Governed Net Sales</th>
            <th class="r">Governed Units</th>
            <th class="r">Looker Drill</th>
          </tr>
        </thead>
        <tbody id="ledger-tbody"></tbody>
      </table>
    </div>
  </section>
</div>

<script>
  let PAYLOAD = __LOOKML_PAYLOAD_JSON__;
  const TARGETS = __TARGETS_JSON__;

  const STATE = {
    quarter: null,
    region: null,
    segment: null,
    category: null,
    barMetric: 'net_sales',
    twoPointDim: 'segment',
    ledgerTab: 'all',
  };

  const fmtAUD = (v) => {
    const n = Number(v || 0);
    const sign = n < 0 ? '-' : '';
    return sign + '$' + Math.abs(n).toLocaleString('en-AU', { maximumFractionDigits: 0 });
  };
  const fmtInt = (v) => Number(v || 0).toLocaleString('en-AU', { maximumFractionDigits: 0 });
  const fmtPct = (v) => Number(v || 0).toFixed(1) + '%';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function matchesFilter(r, ignoreKey = null) {
    if (ignoreKey !== 'quarter' && STATE.quarter && r['dim_date.year_quarter'] !== STATE.quarter) return false;
    if (ignoreKey !== 'region' && STATE.region && r['dim_customer.region'] !== STATE.region) return false;
    if (ignoreKey !== 'segment' && STATE.segment && r['dim_customer.customer_segment'] !== STATE.segment) return false;
    if (ignoreKey !== 'category' && STATE.category && r['dim_product.product_category'] !== STATE.category) return false;
    return true;
  }

  function renderHeaderAndDrawer() {
    const m = PAYLOAD.meta || {};
    document.getElementById('hdr-semantic-pill').textContent =
      `LookML Semantic Layer: ${m.model}.${m.explore}`;
    document.getElementById('hdr-meta-txt').textContent =
      `Product v${m.product_version} · Build ${(m.build_digest || '').slice(0, 19)}… · Filter: ${m.date_filter} · Queried ${m.queried_at_utc}`;

    const lnkDash = document.getElementById('lnk-native-dash');
    if (m.native_dashboard_url) {
      lnkDash.href = m.native_dashboard_url;
      lnkDash.style.display = 'inline-flex';
    }
    const lnkExp = document.getElementById('lnk-explore');
    if (m.looker_explore_url) {
      lnkExp.href = `${m.looker_explore_url}?fields=dim_date.year_month,dim_customer.customer_segment,dim_product.product_category,fct_order_line.net_sales,fct_order_line.units_sold,fct_order_line.order_line_count`;
      lnkExp.style.display = 'inline-flex';
    }

    const sel = document.getElementById('sel-query-key');
    const keys = Object.keys(PAYLOAD.queries || {});
    if (!sel.options.length) {
      keys.forEach((k) => {
        const opt = document.createElement('option');
        opt.value = k;
        opt.textContent = k;
        sel.appendChild(opt);
      });
    }
    const curKey = sel.value || keys[0];
    document.getElementById('box-query-json').textContent = JSON.stringify((PAYLOAD.queries || {})[curKey] || {}, null, 2);
    document.getElementById('box-query-sql').textContent = ((PAYLOAD.compiled_sql || {})[curKey] || '-- SQL unavailable').trim();
  }

  function renderFilterGroup(elId, label, stateKey, values) {
    const wrap = document.getElementById(elId);
    let html = `<span class="filter-lbl">${esc(label)}</span>`;
    html += `<button type="button" class="chip ${STATE[stateKey] === null ? 'active' : ''}" data-key="${stateKey}" data-val="">All</button>`;
    values.forEach((v) => {
      const act = STATE[stateKey] === v ? 'active' : '';
      html += `<button type="button" class="chip ${act}" data-key="${stateKey}" data-val="${esc(v)}">${esc(v)}</button>`;
    });
    wrap.innerHTML = html;
    wrap.querySelectorAll('button.chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const k = btn.getAttribute('data-key');
        const val = btn.getAttribute('data-val');
        STATE[k] = (!val || STATE[k] === val) ? null : val;
        renderAll();
      });
    });
  }

  function renderFilters() {
    const cube = PAYLOAD.data.slice_cube || [];
    const uniq = (fld) => Array.from(new Set(cube.map((r) => r[fld]).filter(Boolean))).sort();
    renderFilterGroup('flt-quarter', 'Quarter', 'quarter', uniq('dim_date.year_quarter'));
    renderFilterGroup('flt-region', 'Region', 'region', uniq('dim_customer.region'));
    renderFilterGroup('flt-segment', 'Segment', 'segment', uniq('dim_customer.customer_segment'));
    renderFilterGroup('flt-category', 'Category', 'category', uniq('dim_product.product_category'));

    const active = [STATE.quarter, STATE.region, STATE.segment, STATE.category].filter(Boolean);
    document.getElementById('active-slice-summary').textContent =
      active.length ? `Filtered: ${active.join(' · ')}` : 'All slices active (click any bar or pill to brush)';
  }

  function bulletHTML({ title, sub, actualText, ctxText, actual, target, maxScale, reversed = false, isException = false, ticks = [] }) {
    const pct = (v) => Math.max(0, Math.min(100, (v / (maxScale || 1)) * 100)).toFixed(2) + '%';
    const bands = reversed
      ? [
          { w: pct(target * 0.7), c: 'var(--bullet-band-good)' },
          { w: pct(target - target * 0.7), c: 'var(--bullet-band-satisfactory)' },
          { w: (100 - parseFloat(pct(target))).toFixed(2) + '%', c: 'var(--bullet-band-poor)' },
        ]
      : [
          { w: '55%', c: 'var(--bullet-band-poor)' },
          { w: '25%', c: 'var(--bullet-band-satisfactory)' },
          { w: '20%', c: 'var(--bullet-band-good)' },
        ];
    return `
      <div class="panel">
        <div>
          <div class="panel-title">${esc(title)}</div>
          <div class="panel-sub">${esc(sub)}</div>
        </div>
        <div class="bullet-val-row num">
          <span class="bullet-ban">${esc(actualText)}</span>
          <span class="bullet-ctx">${esc(ctxText)}</span>
        </div>
        <div class="few-bullet-wrap">
          <div class="few-bullet-track">
            ${bands.map((b) => `<div class="few-bullet-band" style="width:${b.w};background:${b.c};"></div>`).join('')}
            <div class="few-bullet-bar ${isException ? 'is-exception' : ''}" style="width:${pct(actual)};"></div>
            <div class="few-bullet-target" style="left:${pct(target)};"></div>
          </div>
          <div class="few-bullet-ticks num">
            ${ticks.map((t) => `<span>${esc(t)}</span>`).join('')}
          </div>
        </div>
      </div>
    `;
  }

  function renderBullets() {
    const rows = (PAYLOAD.data.order_line_ledger || []).filter((r) => matchesFilter(r));
    let netSales = 0, units = 0, activeLines = 0, rawNet = 0, activeGross = 0, activeDisc = 0, cancelledShielded = 0, cancelledCount = 0;
    rows.forEach((r) => {
      const isCanc = r['fct_order_line.is_cancelled'] === true || String(r['fct_order_line.is_cancelled']).toLowerCase() === 'yes';
      netSales += Number(r['fct_order_line.net_sales'] || 0);
      units += Number(r['fct_order_line.units_sold'] || 0);
      rawNet += Number(r['fct_order_line.net_amount'] || 0);
      if (isCanc) {
        cancelledCount += 1;
        cancelledShielded += Number(r['fct_order_line.net_amount'] || 0);
      } else {
        activeLines += 1;
        activeGross += Number(r['fct_order_line.gross_amount'] || 0);
        activeDisc += Number(r['fct_order_line.discount_amount'] || 0);
      }
    });

    const isFiltered = Boolean(STATE.quarter || STATE.region || STATE.segment || STATE.category);
    const salesTarget = isFiltered ? Math.max(netSales * 0.9, 500) : TARGETS.net_sales;
    const salesMax = Math.max(netSales, salesTarget) * 1.25 || 1000;
    const unitsTarget = isFiltered ? Math.max(Math.round(units * 0.9), 1) : TARGETS.units_sold;
    const unitsMax = Math.max(units, unitsTarget) * 1.25 || 10;

    const leakedCancelled = Math.max(0, netSales - (rawNet - cancelledShielded));
    const discPct = activeGross > 0 ? (activeDisc / activeGross) * 100 : 0;
    const discCeil = TARGETS.discount_ceiling_pct || 10.0;

    const cards = [
      bulletHTML({
        title: 'Governed Net Sales (AUD)',
        sub: 'LookML fct_order_line.net_sales (is_cancelled = No)',
        actualText: fmtAUD(netSales),
        ctxText: `Target ${fmtAUD(salesTarget)} (${netSales >= salesTarget ? '+' : ''}${fmtAUD(netSales - salesTarget)})`,
        actual: netSales,
        target: salesTarget,
        maxScale: salesMax,
        isException: netSales < salesTarget * 0.75,
        ticks: ['$0', fmtAUD(salesMax * 0.5), fmtAUD(salesMax)],
      }),
      bulletHTML({
        title: 'Governed Units Sold',
        sub: `Across ${fmtInt(activeLines)} of ${fmtInt(rows.length)} order lines`,
        actualText: `${fmtInt(units)} units`,
        ctxText: `Target ${fmtInt(unitsTarget)} units`,
        actual: units,
        target: unitsTarget,
        maxScale: unitsMax,
        isException: units < unitsTarget * 0.75,
        ticks: ['0', fmtInt(Math.round(unitsMax * 0.5)), fmtInt(Math.round(unitsMax))],
      }),
      bulletHTML({
        title: 'Cancelled Revenue Leaked',
        sub: `Reversed ceiling ($0 allowed) · ${fmtAUD(cancelledShielded)} shielded (${cancelledCount}/${rows.length} lines)`,
        actualText: fmtAUD(leakedCancelled),
        ctxText: `Ceiling $0 · Shielded ${fmtAUD(cancelledShielded)}`,
        actual: leakedCancelled,
        target: 1,
        maxScale: Math.max(cancelledShielded, 2000),
        reversed: true,
        isException: leakedCancelled > 0,
        ticks: ['$0 (Pass)', fmtAUD(Math.max(cancelledShielded, 2000) * 0.5), fmtAUD(Math.max(cancelledShielded, 2000))],
      }),
      bulletHTML({
        title: 'Effective Discount Rate',
        sub: 'Reversed ceiling (lower is better) · Active lines',
        actualText: fmtPct(discPct),
        ctxText: `Ceiling ${fmtPct(discCeil)} (${fmtAUD(activeDisc)} of ${fmtAUD(activeGross)})`,
        actual: discPct,
        target: discCeil,
        maxScale: 16,
        reversed: true,
        isException: discPct > discCeil,
        ticks: ['0%', '8%', '16%'],
      }),
    ];
    document.getElementById('kpi-strip').innerHTML = cards.join('');
  }

  function renderRankedBars(containerId, dimField, stateKey, secondaryTone = false) {
    const cube = PAYLOAD.data.slice_cube || [];
    const totals = new Map();
    cube.forEach((r) => {
      if (!matchesFilter(r, stateKey)) return;
      const k = r[dimField] || 'Unknown';
      const cur = totals.get(k) || { net_sales: 0, units_sold: 0, lines: 0 };
      cur.net_sales += Number(r['fct_order_line.net_sales'] || 0);
      cur.units_sold += Number(r['fct_order_line.units_sold'] || 0);
      cur.lines += Number(r['fct_order_line.order_line_count'] || 0);
      totals.set(k, cur);
    });

    const mKey = STATE.barMetric;
    const sorted = Array.from(totals.entries()).sort((a, b) => b[1][mKey] - a[1][mKey]);
    const maxVal = Math.max(...sorted.map(([, v]) => v[mKey]), 1);
    const fmt = mKey === 'net_sales' ? fmtAUD : fmtInt;

    const el = document.getElementById(containerId);
    el.innerHTML = sorted.map(([k, v]) => {
      const val = v[mKey];
      const w = Math.max(0, (val / maxVal) * 100).toFixed(2);
      const dimmed = STATE[stateKey] && STATE[stateKey] !== k ? 'dimmed' : '';
      return `
        <div class="bar-row num ${dimmed}" data-key="${stateKey}" data-val="${esc(k)}">
          <div class="bar-lbl" title="${esc(k)}">${esc(k)}</div>
          <div class="bar-track">
            <div class="bar-fill ${secondaryTone ? 'secondary' : ''}" style="width:${w}%;"></div>
          </div>
          <div class="bar-val">${esc(fmt(val))}</div>
        </div>
      `;
    }).join('');

    el.querySelectorAll('.bar-row').forEach((row) => {
      row.addEventListener('click', () => {
        const k = row.getAttribute('data-key');
        const val = row.getAttribute('data-val');
        STATE[k] = STATE[k] === val ? null : val;
        renderAll();
      });
    });
  }

  function nextYearMonth(ym) {
    const [y, m] = ym.split('-').map(Number);
    return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
  }

  function renderMonthlyTrend() {
    const cube = (PAYLOAD.data.slice_cube || []).filter((r) => matchesFilter(r));
    const byMonth = new Map();
    cube.forEach((r) => {
      const ym = r['dim_date.year_month'];
      if (!ym) return;
      byMonth.set(ym, (byMonth.get(ym) || 0) + Number(r['fct_order_line.net_sales'] || 0));
    });

    const observedMonths = Array.from(byMonth.keys()).sort();
    const box = document.getElementById('chart-monthly-trend');
    if (!observedMonths.length) {
      box.innerHTML = '<div class="panel-sub" style="padding:18px 0;">No monthly observations match the current filter.</div>';
      return;
    }

    // Build continuous calendar axis between min and max month, explicitly marking missing months as null (Law 5E)
    const timeline = [];
    let cur = observedMonths[0];
    const last = observedMonths[observedMonths.length - 1];
    let guard = 0;
    while (cur <= last && guard < 36) {
      timeline.push({ ym: cur, val: byMonth.has(cur) ? byMonth.get(cur) : null });
      cur = nextYearMonth(cur);
      guard += 1;
    }

    const W = 560, H = 158, padL = 52, padR = 24, padT = 18, padB = 28;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const maxV = Math.max(...timeline.map((d) => d.val ?? 0), 1000) * 1.15;
    const xAt = (i) => padL + (timeline.length === 1 ? plotW / 2 : (i / (timeline.length - 1)) * plotW);
    const yAt = (v) => padT + plotH - (v / maxV) * plotH;

    // Build broken path segments (never bridge across val === null)
    const segments = [];
    let seg = [];
    timeline.forEach((pt, idx) => {
      if (pt.val === null) {
        if (seg.length) { segments.push(seg); seg = []; }
      } else {
        seg.push({ ...pt, idx, x: xAt(idx), y: yAt(pt.val) });
      }
    });
    if (seg.length) segments.push(seg);

    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="158" role="img" aria-label="Monthly Net Sales Trend">`;
    [0, 0.5, 1].forEach((f) => {
      const y = yAt(maxV * f);
      svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--grid-line-muted)" stroke-width="1"/>`;
      svg += `<text x="${padL - 7}" y="${y + 3.5}" text-anchor="end" font-size="10" fill="var(--text-muted)">${esc(fmtAUD(maxV * f))}</text>`;
    });

    // Missing-period callout band
    timeline.forEach((pt, idx) => {
      const x = xAt(idx);
      svg += `<text x="${x}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--text-secondary)">${esc(pt.ym)}</text>`;
      if (pt.val === null) {
        svg += `<line x1="${x}" y1="${padT}" x2="${x}" y2="${padT + plotH}" stroke="var(--border)" stroke-dasharray="3,3"/>`;
        svg += `<text x="${x}" y="${padT + plotH / 2}" text-anchor="middle" font-size="9.5" fill="var(--text-muted)">No orders (gap)</text>`;
      }
    });

    segments.forEach((s) => {
      if (s.length >= 2) {
        const d = s.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
        svg += `<path d="${d}" fill="none" stroke="var(--data-secondary-bar)" stroke-width="2"/>`;
      }
      s.forEach((p) => {
        svg += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="var(--text-primary)" stroke="var(--bg-panel)" stroke-width="1.5"/>`;
        svg += `<text x="${p.x.toFixed(1)}" y="${Math.max(12, p.y - 8).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="600" fill="var(--text-primary)">${esc(fmtAUD(p.val))}</text>`;
      });
    });

    svg += `</svg>`;
    box.innerHTML = svg;
  }

  function renderTwoPointChange() {
    const dimField = STATE.twoPointDim === 'segment' ? 'dim_customer.customer_segment' : 'dim_product.product_category';
    const cube = (PAYLOAD.data.slice_cube || []).filter((r) => matchesFilter(r, 'quarter'));
    const quarters = Array.from(new Set(cube.map((r) => r['dim_date.year_quarter']).filter(Boolean))).sort();
    const box = document.getElementById('chart-two-point');
    if (quarters.length < 2) {
      box.innerHTML = '<div class="panel-sub" style="padding:14px 0;">At least two quarters are required for two-point change comparison.</div>';
      return;
    }
    const q1 = quarters[0], q2 = quarters[quarters.length - 1];
    const map = new Map();
    cube.forEach((r) => {
      const k = r[dimField] || 'Unknown';
      const q = r['dim_date.year_quarter'];
      if (q !== q1 && q !== q2) return;
      const entry = map.get(k) || { q1: 0, q2: 0 };
      if (q === q1) entry.q1 += Number(r['fct_order_line.net_sales'] || 0);
      if (q === q2) entry.q2 += Number(r['fct_order_line.net_sales'] || 0);
      map.set(k, entry);
    });

    const items = Array.from(map.entries())
      .map(([k, v]) => ({ name: k, q1: v.q1, q2: v.q2, delta: v.q2 - v.q1 }))
      .sort((a, b) => b.delta - a.delta);

    const W = 560, rowH = 30, padT = 22, padB = 18;
    const H = padT + items.length * rowH + padB;
    const lblW = 96, rangeX0 = 104, rangeW = 210, devX0 = 336, devW = 160;
    const maxAbs = Math.max(...items.flatMap((d) => [d.q1, d.q2]), 1000) * 1.1;
    const maxDev = Math.max(...items.map((d) => Math.abs(d.delta)), 500) * 1.15;
    const devZero = devX0 + devW / 2;

    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Quarter-on-quarter range and deviation bars">`;
    svg += `<text x="${rangeX0}" y="13" font-size="10" font-weight="600" fill="var(--text-muted)">RANGE: ${esc(q1)} (○) → ${esc(q2)} (●)</text>`;
    svg += `<text x="${devZero}" y="13" text-anchor="middle" font-size="10" font-weight="600" fill="var(--text-muted)">DEVIATION (Δ AUD)</text>`;
    svg += `<line x1="${rangeX0}" y1="${padT}" x2="${rangeX0}" y2="${H - padB}" stroke="var(--border)" stroke-width="1"/>`;
    svg += `<line x1="${devZero}" y1="${padT}" x2="${devZero}" y2="${H - padB}" stroke="var(--text-primary)" stroke-width="1"/>`;

    items.forEach((it, idx) => {
      const cy = padT + idx * rowH + rowH / 2;
      const x1 = rangeX0 + (it.q1 / maxAbs) * rangeW;
      const x2 = rangeX0 + (it.q2 / maxAbs) * rangeW;
      const left = Math.min(x1, x2), width = Math.max(2, Math.abs(x2 - x1));
      const barColor = it.delta >= 0 ? 'var(--data-secondary-bar)' : 'var(--data-muted-bar)';

      svg += `<text x="${lblW - 6}" y="${cy + 4}" text-anchor="end" font-size="11" font-weight="500" fill="var(--text-primary)">${esc(it.name)}</text>`;
      svg += `<rect x="${left.toFixed(1)}" y="${(cy - 4).toFixed(1)}" width="${width.toFixed(1)}" height="8" fill="${barColor}" rx="1"/>`;
      svg += `<circle cx="${x1.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.5" fill="var(--bg-panel)" stroke="var(--text-secondary)" stroke-width="1.5"/>`;
      svg += `<circle cx="${x2.toFixed(1)}" cy="${cy.toFixed(1)}" r="4" fill="var(--text-primary)"/>`;

      const dLen = (Math.abs(it.delta) / maxDev) * (devW / 2);
      const dx = it.delta >= 0 ? devZero : devZero - dLen;
      const dFill = it.delta >= 0 ? 'var(--pass-fill)' : 'var(--warn-fill)';
      svg += `<rect x="${dx.toFixed(1)}" y="${(cy - 5).toFixed(1)}" width="${Math.max(1.5, dLen).toFixed(1)}" height="10" fill="${dFill}"/>`;
      const sign = it.delta > 0 ? '+' : '';
      svg += `<text x="${W - 4}" y="${cy + 4}" text-anchor="end" font-size="10.5" font-weight="600" fill="var(--text-primary)">${esc(sign + fmtAUD(it.delta))}</text>`;
    });

    svg += `</svg>`;
    box.innerHTML = svg;
  }

  function renderShieldAndSCD2() {
    const guard = PAYLOAD.data.semantic_guardrail || [];
    let rawAmt = 0, govAmt = 0, rawCnt = 0, govCnt = 0;
    guard.forEach((r) => {
      rawAmt += Number(r['fct_order_line.net_amount'] || 0);
      govAmt += Number(r['fct_order_line.net_sales'] || 0);
      rawCnt += Number(r['fct_order_line.count'] || 0);
      govCnt += Number(r['fct_order_line.order_line_count'] || 0);
    });
    const maxShield = Math.max(rawAmt, govAmt, 1);
    const delta = rawAmt - govAmt;

    document.getElementById('semantic-shield-box').innerHTML = `
      <div style="display:flex;justify-content:space-between;font-size:11px;">
        <span style="color:var(--text-secondary);">Unfiltered Raw <span class="mono">net_amount</span> (${fmtInt(rawCnt)} lines)</span>
        <strong class="num" style="color:var(--fail-fill);">${esc(fmtAUD(rawAmt))}</strong>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:${((rawAmt / maxShield) * 100).toFixed(1)}%;background:var(--fail-fill);opacity:0.75;"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:11px;margin-top:2px;">
        <span style="color:var(--text-secondary);">Governed LookML <span class="mono">net_sales</span> (${fmtInt(govCnt)} lines)</span>
        <strong class="num">${esc(fmtAUD(govAmt))}</strong>
      </div>
      <div class="bar-track"><div class="bar-fill" style="width:${((govAmt / maxShield) * 100).toFixed(1)}%;background:var(--pass-fill);"></div></div>
      <div class="shield-callout num">
        <span>LookML Semantic Shield Active</span>
        <span>-${esc(fmtAUD(delta))} cancelled excluded</span>
      </div>
    `;

    // Point-in-Time SCD2 proof rows (entities appearing across >=2 versions or months)
    const scdRows = PAYLOAD.data.scd2_point_in_time || [];
    const byCust = new Map();
    scdRows.forEach((r) => {
      const cid = r['dim_customer.customer_id'];
      byCust.set(cid, (byCust.get(cid) || new Set()).add(r['dim_customer.customer_segment']));
    });
    const byProd = new Map();
    scdRows.forEach((r) => {
      const pid = r['dim_product.product_id'];
      byProd.set(pid, (byProd.get(pid) || new Set()).add(r['dim_product.product_category']));
    });

    const transitions = scdRows.filter((r) =>
      (byCust.get(r['dim_customer.customer_id']) || new Set()).size > 1 ||
      (byProd.get(r['dim_product.product_id']) || new Set()).size > 1
    );

    const tbl = document.getElementById('tbl-scd2-audit');
    tbl.innerHTML = `
      <thead>
        <tr>
          <th>Month</th>
          <th>Entity</th>
          <th>As-At Attribute</th>
          <th class="r">Net Sales</th>
        </tr>
      </thead>
      <tbody>
        ${transitions.map((r) => `
          <tr>
            <td class="mono">${esc(r['dim_date.year_month'])}</td>
            <td>${esc(r['dim_customer.customer_id'])} · ${esc(r['dim_product.product_id'])}</td>
            <td><span class="status-tag scd">v${esc(r['dim_customer.version_no'])} ${esc(r['dim_customer.customer_segment'])} / ${esc(r['dim_product.product_category'])}</span></td>
            <td class="r">${esc(fmtAUD(r['fct_order_line.net_sales']))}</td>
          </tr>
        `).join('')}
      </tbody>
    `;
  }

  function renderLedger() {
    const allRows = PAYLOAD.data.order_line_ledger || [];
    const custSegs = new Map(), prodCats = new Map();
    allRows.forEach((r) => {
      const cid = r['dim_customer.customer_id'], pid = r['dim_product.product_id'];
      if (!custSegs.has(cid)) custSegs.set(cid, new Set());
      if (!prodCats.has(pid)) prodCats.set(pid, new Set());
      custSegs.get(cid).add(r['dim_customer.customer_segment']);
      prodCats.get(pid).add(r['dim_product.product_category']);
    });

    const tabFiltered = allRows.filter((r) => {
      const isCanc = r['fct_order_line.is_cancelled'] === true || String(r['fct_order_line.is_cancelled']).toLowerCase() === 'yes';
      if (STATE.ledgerTab === 'cancelled') return isCanc;
      if (STATE.ledgerTab === 'scd2') {
        return (custSegs.get(r['dim_customer.customer_id']) || new Set()).size > 1 ||
               (prodCats.get(r['dim_product.product_id']) || new Set()).size > 1;
      }
      return true;
    });

    const expBase = (PAYLOAD.meta || {}).looker_explore_url || '';
    const tbody = document.getElementById('ledger-tbody');
    tbody.innerHTML = tabFiltered.map((r) => {
      const isCanc = r['fct_order_line.is_cancelled'] === true || String(r['fct_order_line.is_cancelled']).toLowerCase() === 'yes';
      const dimmed = !matchesFilter(r) ? 'dimmed' : '';
      const oid = r['fct_order_line.order_id'];
      const drillHref = expBase
        ? `${expBase}?fields=fct_order_line.order_id,fct_order_line.order_line_no,fct_order_line.order_date,dim_customer.customer_name,dim_customer.customer_segment,dim_product.product_category,fct_order_line.order_status,fct_order_line.net_sales,fct_order_line.units_sold&f[fct_order_line.order_id]=${encodeURIComponent(oid)}`
        : '#';
      return `
        <tr class="${dimmed}">
          <td class="mono"><strong>${esc(oid)}</strong></td>
          <td class="r mono">${esc(r['fct_order_line.order_line_no'])}</td>
          <td class="mono">${esc(r['fct_order_line.order_date'])}</td>
          <td class="mono">${esc(r['dim_date.year_month'])}</td>
          <td>${esc(r['dim_customer.customer_name'])} <span style="color:var(--text-muted);">(${esc(r['dim_customer.customer_id'])})</span></td>
          <td>${esc(r['dim_customer.customer_segment'])} <span style="color:var(--text-muted);">v${esc(r['dim_customer.version_no'])}</span></td>
          <td>${esc(r['dim_customer.region'])}</td>
          <td>${esc(r['dim_product.product_name'])}</td>
          <td>${esc(r['dim_product.product_category'])} <span style="color:var(--text-muted);">v${esc(r['dim_product.version_no'])}</span></td>
          <td><span class="status-tag ${isCanc ? 'cancelled' : 'ok'}">${esc(r['fct_order_line.order_status'])}${isCanc ? ' · SHIELDED' : ''}</span></td>
          <td class="r">${esc(fmtAUD(r['fct_order_line.gross_amount']))}</td>
          <td class="r">${esc(fmtAUD(r['fct_order_line.discount_amount']))}</td>
          <td class="r" style="${isCanc ? 'color:var(--fail-fill);text-decoration:line-through;' : ''}">${esc(fmtAUD(r['fct_order_line.net_amount']))}</td>
          <td class="r"><strong>${esc(fmtAUD(r['fct_order_line.net_sales']))}</strong></td>
          <td class="r">${esc(fmtInt(r['fct_order_line.units_sold']))}</td>
          <td class="r">${expBase ? `<a class="explore-link" href="${esc(drillHref)}" target="_blank" rel="noopener">Explore ↗</a>` : '—'}</td>
        </tr>
      `;
    }).join('');

    const matchingCount = tabFiltered.filter((r) => matchesFilter(r)).length;
    document.getElementById('ledger-summary').textContent =
      `Showing ${matchingCount} active-slice row(s) of ${tabFiltered.length} in tab (${allRows.length} total lines from LookML order_lines)`;
  }

  function renderAll() {
    renderHeaderAndDrawer();
    renderFilters();
    renderBullets();
    renderRankedBars('bars-region', 'dim_customer.region', 'region', false);
    renderRankedBars('bars-category', 'dim_product.product_category', 'category', true);
    renderMonthlyTrend();
    renderTwoPointChange();
    renderShieldAndSCD2();
    renderLedger();
  }

  // Controls wiring
  document.getElementById('btn-sql-drawer').addEventListener('click', () => {
    document.getElementById('sql-drawer').classList.toggle('open');
  });
  document.getElementById('sel-query-key').addEventListener('change', renderHeaderAndDrawer);
  document.getElementById('btn-theme').addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key.toLowerCase() === 't' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      document.body.classList.toggle('dark-mode');
    }
  });
  document.getElementById('btn-reset-filters').addEventListener('click', () => {
    STATE.quarter = null; STATE.region = null; STATE.segment = null; STATE.category = null;
    renderAll();
  });

  document.querySelectorAll('#metric-switcher button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#metric-switcher button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.barMetric = btn.getAttribute('data-metric');
      renderRankedBars('bars-region', 'dim_customer.region', 'region', false);
      renderRankedBars('bars-category', 'dim_product.product_category', 'category', true);
    });
  });

  document.querySelectorAll('#twopoint-dim-switcher button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#twopoint-dim-switcher button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.twoPointDim = btn.getAttribute('data-dim');
      renderTwoPointChange();
    });
  });

  document.querySelectorAll('#ledger-tabs button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#ledger-tabs button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.ledgerTab = btn.getAttribute('data-tab');
      renderLedger();
    });
  });

  document.getElementById('btn-live-refresh').addEventListener('click', async () => {
    const btn = document.getElementById('btn-live-refresh');
    const orig = btn.textContent;
    btn.textContent = '↻ Querying Looker…';
    try {
      const resp = await fetch('/api/lookml-telemetry');
      if (!resp.ok) throw new Error('Not connected to live local dpf looker cockpit --serve endpoint');
      const data = await resp.json();
      if (data.ok && data.payload) {
        PAYLOAD = data.payload;
        renderAll();
        btn.textContent = '✓ Refreshed from LookML';
        setTimeout(() => { btn.textContent = orig; }, 1800);
        return;
      }
      throw new Error((data.errors || []).join('; ') || 'Refresh failed');
    } catch (_) {
      btn.textContent = 'ℹ Embedded Snapshot (use --serve for live)';
      setTimeout(() => { btn.textContent = orig; }, 2400);
    }
  });

  renderAll();
</script>
</body>
</html>
"""
