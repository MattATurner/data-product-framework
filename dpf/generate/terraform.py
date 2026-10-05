"""Terraform renderer: everything the product needs around its models.

Datasets and dataset access (one ACL mechanism only: `google_bigquery_dataset_access`, so
authorised datasets are never clobbered), policy tags with data masking, BigQuery sharing
exchanges and listings, Dataform release and workflow configurations, freshness and volume checks as
scheduled queries, log-based metrics and alert policies, Knowledge Catalog data quality
scans, and the control tables the extractor writes. The module declares no providers; the
caller configures `google` and `google-beta`.
"""

from __future__ import annotations

import json
import re

from dpf.core import Product
from dpf.graph import ProductGraph
from dpf.generate.plan import Action
from dpf.generate.render import (dts_schedule, duration_minutes, is_timestamp, kebab_id, marker, project_vars,
                                 snake_id, timezone)

ROOT = "terraform"
ROLE_MAP = {"roles/bigquery.dataViewer": "READER", "roles/bigquery.dataEditor": "WRITER",
            "roles/bigquery.dataOwner": "OWNER"}
MASKING = {"always_null": "ALWAYS_NULL", "sha256": "SHA256", "default_masking_value": "DEFAULT_MASKING_VALUE"}
DAYS = {"SUN": 1, "MON": 2, "TUE": 3, "WED": 4, "THU": 5, "FRI": 6, "SAT": 7}
DATASET_PURPOSE = {
    "raw": "append-only raw landing, one table per source entity",
    "staging": "typed, deduplicated staging views with reject relations",
    "silver": "integration layer",
    "gold": "consumption layer read by the output ports",
    "share": "sharing dataset published as a BigQuery sharing listing",
    "assertions": "check results written by the pipeline's assertions",
    "control": "watermarks, landing manifests and the schema registry",
}
CONTROL_TABLES = {
    "extract_watermark": ("One row per committed batch; MAX(watermark_high) is the entity's watermark.", [
        ("source_system", "STRING", "NULLABLE"), ("entity", "STRING", "NULLABLE"),
        ("watermark_high", "TIMESTAMP", "NULLABLE"), ("batch_id", "STRING", "NULLABLE"),
        ("row_count", "INT64", "NULLABLE"), ("updated_at", "TIMESTAMP", "NULLABLE")], []),
    "landing_manifest": ("One landing-manifest.v1 per landed batch; a batch without a manifest is not consumable.", [
        ("batch_id", "STRING", "REQUIRED"), ("source_system", "STRING", "REQUIRED"), ("entity", "STRING", "REQUIRED"),
        ("ingest_ts", "TIMESTAMP", "REQUIRED"), ("row_count", "INT64", "REQUIRED"),
        ("watermark_low", "TIMESTAMP", "NULLABLE"), ("watermark_high", "TIMESTAMP", "NULLABLE"),
        ("schema_fingerprint", "STRING", "NULLABLE"), ("drift", "STRING", "NULLABLE"), ("status", "STRING", "REQUIRED"),
        ("manifest", "JSON", "NULLABLE"), ("recorded_at", "TIMESTAMP", "REQUIRED")], ["source_system", "entity"]),
    "schema_registry": ("Accepted schema per source entity; the latest recorded_at wins.", [
        ("source_system", "STRING", "REQUIRED"), ("entity", "STRING", "REQUIRED"), ("fingerprint", "STRING", "REQUIRED"),
        ("schema_json", "JSON", "NULLABLE"), ("recorded_at", "TIMESTAMP", "REQUIRED"), ("batch_id", "STRING", "NULLABLE")],
        ["source_system", "entity"]),
}


def q(s) -> str:
    """HCL quoted string with no interpolation."""
    s = json.dumps(str(s), ensure_ascii=False)
    return s.replace("${", "$${").replace("%{", "%%{")


def hcl_list(values: list[str]) -> str:
    return "[" + ", ".join(q(v) for v in values) + "]"


def reqs_of(*elements: dict) -> list[str]:
    out: list[str] = []
    for e in elements:
        out += list((e or {}).get("brd_requirement_id") or [])
    return sorted(set(out), key=lambda x: int(x.split("-")[1]))


def trace(elements: list[str] | None = None, satisfies: list[str] | None = None, implements: str | None = None,
          **extra) -> str:
    fields = {}
    if elements:
        fields["element"] = elements
    fields.update(extra)
    if satisfies:
        fields["satisfies"] = satisfies
    if implements:
        fields["implements"] = implements
    return marker(fields, "#")


class Module:
    def __init__(self, p: Product, g: ProductGraph, actions: list[Action], engine: str):
        self.p, self.g, self.actions, self.engine = p, g, actions, engine
        self.man = p.manifest
        self.ds = (self.man.get("deployment") or {}).get("datasets") or {}
        self.tz = timezone(p)
        self.variables: dict[str, dict] = {}
        self.files: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ helpers
    def emit(self, file: str, header: str, block: str) -> None:
        self.files.setdefault(file, []).append(header + "\n" + block.strip("\n") + "\n")

    def var(self, name: str, description: str, default=None, has_default: bool = False) -> str:
        if name not in self.variables:
            self.variables[name] = {"description": description, "default": default, "has_default": has_default}
        return f"var.{name}"

    def dataset_of(self, model: str) -> str:
        node = self.g.get(model)
        if node is None:
            return "gold"
        if node.kind == "raw":
            return "raw"
        if node.layer == "staging":
            return "staging"
        return node.model.get("dataset") or node.layer

    def ports_in(self, dataset_key: str) -> list[dict]:
        return [pt for pt in self.man.get("output_ports", []) or [] if self.dataset_of(pt["model"]) == dataset_key]

    # ------------------------------------------------------------------ sections
    def versions(self) -> None:
        self.emit("versions.tf", trace(implements="generate-artefacts", product=self.p.id), """
terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.30"
    }
  }
}""")

    def base_variables(self) -> None:
        dep = self.man.get("deployment") or {}
        self.var("project_id", "Project hosting the product's datasets.", dep.get("gcp_project"), True)
        self.var("region", "BigQuery location and region for every regional resource.", dep.get("region"), True)

    def datasets(self) -> None:
        for key, name in self.ds.items():
            desc = f"{self.p.id}: {DATASET_PURPOSE.get(key, key)} (generated by dpf)."
            self.emit("datasets.tf", trace(implements="select-engine-and-storage", dataset=key), f"""
resource "google_bigquery_dataset" "{key}" {{
  project                    = var.project_id
  dataset_id                 = {q(name)}
  location                   = var.region
  description                = {q(desc)}
  delete_contents_on_destroy = false
  labels = {{
    dpf_product = {q(self.p.id)}
    dpf_layer   = {q(key)}
  }}
}}""")

    def access(self) -> None:
        gov = self.man.get("governance") or {}
        for a in gov.get("access", []) or []:
            pv = a["principal_var"]
            self.var(pv, f"Google group email: {a.get('description', pv)}.")
            for key in a.get("datasets", []) or []:
                if key not in self.ds:
                    continue
                ports = self.ports_in(key)
                hdr = trace([f"port:{pt['name']}" for pt in ports], reqs_of(*ports),
                            None if ports else "generate-artefacts", dataset=key)
                role = ROLE_MAP.get(a["role"], a["role"])
                self.emit("access.tf", hdr, f"""
resource "google_bigquery_dataset_access" "{key}_{snake_id(pv)}" {{
  project        = var.project_id
  dataset_id     = google_bigquery_dataset.{key}.dataset_id
  role           = {q(role)}
  group_by_email = var.{pv}
}}""")
        # Authorised datasets: consumer-facing views read other datasets without granting them.
        port_ds = {self.dataset_of(pt["model"]) for pt in self.man.get("output_ports", []) or []}
        pairs: dict[tuple[str, str], list[str]] = {}
        for a in self.actions:
            if a.kind != "view" or a.dataset not in port_ds:
                continue
            for i in self.g.upstream(a.model, transitive=False):
                src = self.dataset_of(i)
                if src != a.dataset and src in self.ds:
                    pairs.setdefault((src, a.dataset), []).append(a.model)
        for (src, viewer), models in sorted(pairs.items()):
            ports = [pt for pt in self.man.get("output_ports", []) or [] if pt["model"] in models]
            self.emit("access.tf", trace([f"port:{pt['name']}" for pt in ports], reqs_of(*ports),
                                         None if ports else "generate-artefacts"), f"""
resource "google_bigquery_dataset_access" "{src}_authorizes_{viewer}_views" {{
  project    = var.project_id
  dataset_id = google_bigquery_dataset.{src}.dataset_id
  dataset {{
    dataset {{
      project_id = var.project_id
      dataset_id = google_bigquery_dataset.{viewer}.dataset_id
    }}
    target_types = ["VIEWS"]
  }}
}}""")

    def policy_tags(self) -> None:
        tags = (self.man.get("governance") or {}).get("policy_tags", []) or []
        if not tags:
            return
        allp = [f"policy:{t['id']}" for t in tags]
        self.emit("governance.tf", trace(allp, reqs_of(*tags)), f"""
resource "google_data_catalog_taxonomy" "product" {{
  project                = var.project_id
  region                 = var.region
  display_name           = {q(self.p.id)}
  description            = {q(f"Column policy tags for {self.p.id} (generated by dpf).")}
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}}""")
        done: set[str] = set()
        for t in tags:
            tag = t["tag"]
            if tag not in done:
                done.add(tag)
                users = [x for x in tags if x["tag"] == tag]
                desc = "; ".join(f"{x['model']}: {', '.join(x['columns'])} ({x['id']})" for x in users)
                self.emit("governance.tf", trace([f"policy:{x['id']}" for x in users], reqs_of(*users)), f"""
resource "google_data_catalog_policy_tag" "{tag}" {{
  taxonomy     = google_data_catalog_taxonomy.product.id
  display_name = {q(tag)}
  description  = {q(desc)}
}}""")
                for reader in sorted({r for x in users for r in x.get("fine_grained_readers") or []}):
                    self.var(reader, "Google group email allowed to read the unmasked values of tagged columns.")
                    self.emit("governance.tf", trace([f"policy:{x['id']}" for x in users], reqs_of(*users)), f"""
resource "google_data_catalog_policy_tag_iam_member" "{tag}_reader_{snake_id(reader)}" {{
  policy_tag = google_data_catalog_policy_tag.{tag}.name
  role       = "roles/datacatalog.categoryFineGrainedReader"
  member     = "group:${{var.{reader}}}"
}}""")
            pid = snake_id(t["id"])
            self.emit("governance.tf", trace([f"policy:{t['id']}"], reqs_of(t)), f"""
resource "google_bigquery_datapolicy_data_policy" "{pid}" {{
  project          = var.project_id
  location         = var.region
  data_policy_id   = {q(snake_id(self.p.id, t["id"]))}
  policy_tag       = google_data_catalog_policy_tag.{tag}.name
  data_policy_type = "DATA_MASKING_POLICY"
  data_masking_policy {{
    predefined_expression = {q(MASKING[t["masking"]])}
  }}
}}""")
            for reader in t.get("masked_readers") or []:
                self.var(reader, "Google group email that sees masked values of tagged columns.")
                self.emit("governance.tf", trace([f"policy:{t['id']}"], reqs_of(t)), f"""
resource "google_bigquery_datapolicy_data_policy_iam_member" "{pid}_masked_{snake_id(reader)}" {{
  project        = var.project_id
  location       = var.region
  data_policy_id = google_bigquery_datapolicy_data_policy.{pid}.data_policy_id
  role           = "roles/bigquerydatapolicy.maskedReader"
  member         = "group:${{var.{reader}}}"
}}""")

    def sharing(self) -> None:
        exchanges: set[str] = set()
        for pt in self.man.get("output_ports", []) or []:
            sh = pt.get("sharing")
            if pt.get("access") != "sharing_listing" or not sh:
                continue
            ex, li = sh["exchange_id"], sh["listing_id"]
            ds_key = self.dataset_of(pt["model"])
            hdr = trace([f"port:{pt['name']}"], reqs_of(pt))
            if ex not in exchanges:
                exchanges.add(ex)
                self.emit("sharing.tf", hdr, f"""
resource "google_bigquery_analytics_hub_data_exchange" "{ex}" {{
  project          = var.project_id
  location         = var.region
  data_exchange_id = {q(ex)}
  display_name     = {q(ex)}
  description      = {q(f"{self.p.id}: external sharing exchange (generated by dpf).")}
}}""")
            node = self.g.get(pt["model"])
            grain = (node.model.get("grain_statement") if node else "") or ""
            self.emit("sharing.tf", hdr, f"""
resource "google_bigquery_analytics_hub_listing" "{li}" {{
  project          = var.project_id
  location         = var.region
  data_exchange_id = google_bigquery_analytics_hub_data_exchange.{ex}.data_exchange_id
  listing_id       = {q(li)}
  display_name     = {q(pt["name"])}
  description      = {q(f"{pt['name']}: {grain}.")}
  bigquery_dataset {{
    dataset = google_bigquery_dataset.{ds_key}.id
  }}
  restricted_export_config {{
    enabled               = true
    restrict_query_result = true
  }}
}}""")
            sv = sh.get("subscriber_var")
            if sv:
                self.var(sv, "IAM member granted subscriber on the listing, e.g. group:analytics@partner.example. "
                             "Empty: no subscriber yet.", "", True)
                self.emit("sharing.tf", hdr, f"""
resource "google_bigquery_analytics_hub_listing_iam_member" "{li}_subscriber" {{
  count            = var.{sv} == "" ? 0 : 1
  project          = var.project_id
  location         = var.region
  data_exchange_id = google_bigquery_analytics_hub_data_exchange.{ex}.data_exchange_id
  listing_id       = google_bigquery_analytics_hub_listing.{li}.listing_id
  role             = "roles/analyticshub.subscriber"
  member           = var.{sv}
}}""")

    def orchestration(self) -> None:
        if self.engine != "dataform":
            return
        orch = self.man.get("orchestration") or {}
        self.var("dataform_repository", "Existing Dataform repository (name) whose default branch holds the generated "
                                        "dataform/ tree.")
        self.var("dataform_git_commitish", "Branch, tag or commit the release configuration compiles.", "main", True)
        self.var("dataform_service_account", "Service account workflow invocations run as. Empty: the Dataform "
                                             "service agent.", "", True)
        tags = (self.man.get("governance") or {}).get("policy_tags", []) or []
        vars_ = dict(project_vars(self.p))
        width = max(len(k) for k in vars_)
        lines = []
        for k, v in vars_.items():
            if k.startswith("policy_tag_"):
                tag = k.removeprefix("policy_tag_")
                lines.append(f"      {k.ljust(width)} = google_data_catalog_policy_tag.{tag}.name")
            else:
                lines.append(f"      {k.ljust(width)} = {q(v)}")
        name = kebab_id(self.p.id)
        self.emit("orchestration.tf", trace([f"policy:{t['id']}" for t in tags], reqs_of(*tags),
                                            "generate-artefacts"), f"""
resource "google_dataform_repository_release_config" "product" {{
  provider      = google-beta
  project       = var.project_id
  region        = var.region
  repository    = var.dataform_repository
  name          = {q(name)}
  git_commitish = var.dataform_git_commitish
  cron_schedule = "0 * * * *"
  time_zone     = {q(self.tz)}
  code_compilation_config {{
    default_database = var.project_id
    default_schema   = {q(self.ds.get("staging"))}
    default_location = var.region
    assertion_schema = {q(self.ds.get("assertions", "dpf_assertions"))}
    vars = {{
{chr(10).join(lines)}
    }}
  }}
}}""")
        for s in orch.get("schedules", []) or []:
            self.emit("orchestration.tf", trace([f"schedule:{s['id']}"], reqs_of(s), None if reqs_of(s) else "generate-artefacts"), f"""
resource "google_dataform_repository_workflow_config" "{snake_id(s['id'])}" {{
  provider       = google-beta
  project        = var.project_id
  region         = var.region
  repository     = var.dataform_repository
  name           = {q(kebab_id(self.p.id, s["id"]))}
  release_config = google_dataform_repository_release_config.product.id
  cron_schedule  = {q(s["cron"])}
  time_zone      = {q(self.tz)}
  invocation_config {{
    included_tags                            = [{q(s["id"])}]
    transitive_dependencies_included         = false
    fully_refresh_incremental_tables_enabled = false
    service_account                          = var.dataform_service_account == "" ? null : var.dataform_service_account
  }}
}}""")

    # ------------------------------------------------------------------ monitoring
    def _table(self, model: str) -> str:
        return f"`${{var.project_id}}.{self.ds.get(self.dataset_of(model))}.{model}`"

    def freshness_sql(self, ob: dict) -> str:
        model, max_min = ob["model"], duration_minutes(ob["max_staleness"])
        cal = ob.get("calendar")
        lines = [f"-- {ob['id']}: {model} must be no older than {max_min} minutes ({ob['max_staleness']})"
                 + (f", {' '.join(cal['days'])} {cal['start']}-{cal['end']} {cal['timezone']}." if cal else ", at all times."),
                 "-- A breach (or a missing table) fails the query, which fails the transfer run and raises the alert.",
                 "SELECT",
                 f"  IF(age_minutes IS NULL OR age_minutes > {max_min},",
                 f"     ERROR(FORMAT('dpf_freshness_breach {ob['id']} {self.p.id}.{model} age_minutes=%s max_minutes={max_min}',",
                 "                  IFNULL(CAST(age_minutes AS STRING), 'missing'))),",
                 "     'fresh') AS status",
                 "FROM (",
                 "  SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP_MILLIS(MAX(last_modified_time)), MINUTE) AS age_minutes",
                 f"  FROM `${{var.project_id}}.{self.ds.get(self.dataset_of(model))}.__TABLES__`",
                 f"  WHERE table_id = '{model}'",
                 ")"]
        if cal:
            days = ", ".join(str(DAYS[d]) for d in cal["days"])
            tz = cal["timezone"]
            lines += [f"WHERE EXTRACT(DAYOFWEEK FROM CURRENT_DATETIME('{tz}')) IN ({days})",
                      f"  AND CURRENT_TIME('{tz}') BETWEEN TIME '{cal['start']}:00' AND TIME '{cal['end']}:00'"]
        return "\n".join(lines)

    def volume_sql(self, ob: dict) -> str:
        model, exp, tol = ob["model"], int(ob["expected_rows"]), float(ob["tolerance_pct"])
        lo, hi = int(exp * (1 - tol / 100)), int(exp * (1 + tol / 100))
        days = max(1, duration_minutes(ob["window"]) // 1440)
        col = ob.get("date_column")
        if col:
            expr = f"DATE({col}, '{self.tz}')" if is_timestamp(col) else col
            where = (f"WHERE {expr} >= DATE_SUB(CURRENT_DATE('{self.tz}'), INTERVAL {days} DAY)\n"
                     f"    AND {expr} < CURRENT_DATE('{self.tz}')")
        else:
            where = ""
        return "\n".join([
            f"-- {ob['id']}: {model} should hold {exp} rows (+/-{tol:g}%) per {ob['window']} window"
            + (f" of {col}." if col else "."),
            f"SELECT IF(n BETWEEN {lo} AND {hi}, 'ok',",
            f"          ERROR(FORMAT('dpf_volume_breach {ob['id']} {self.p.id}.{model} rows=%d expected={exp} "
            f"tolerance_pct={tol:g}', n))) AS status",
            "FROM (",
            "  SELECT COUNT(*) AS n",
            f"  FROM {self._table(model)}",
            f"  {where}".rstrip(),
            ")"])

    def monitoring(self) -> None:
        obs = self.man.get("observability") or {}
        alerting = obs.get("alerting") or {}
        chan = alerting.get("notification_channel_var") or "alert_channel"
        self.var(chan, "Cloud Monitoring notification channel (projects/<p>/notificationChannels/<id>). Empty: "
                       "alert policies are created without a channel.", "", True)
        self.var("monitor_service_account", "Service account the scheduled checks run as. Empty: the caller's "
                                            "credentials.", "", True)
        runbook = alerting.get("runbook")
        checks: list[str] = []

        def transfer(rid: str, ob: dict, display: str, schedule: str, sql: str, elements: list[str]) -> None:
            checks.append(rid)
            sat = reqs_of(ob)
            body = "\n".join("      " + line if line else "" for line in sql.splitlines())
            self.emit("monitoring.tf", trace(elements, sat, ob.get("implements") if not sat else None), f"""
resource "google_bigquery_data_transfer_config" "{rid}" {{
  project              = var.project_id
  display_name         = {q(display)}
  location             = var.region
  data_source_id       = "scheduled_query"
  schedule             = {q(schedule)}
  service_account_name = var.monitor_service_account == "" ? null : var.monitor_service_account
  email_preferences {{
    enable_failure_email = true
  }}
  params = {{
    query = <<-SQL
{body}
    SQL
  }}
}}""")

        for ob in obs.get("freshness", []) or []:
            transfer(f"freshness_{snake_id(ob['id'])}", ob, f"dpf {self.p.id} {ob['id']} freshness of {ob['model']}",
                     dts_schedule(ob.get("check_every") or "PT1H"), self.freshness_sql(ob), [f"observability:{ob['id']}"])
        for ob in obs.get("volume", []) or []:
            transfer(f"volume_{snake_id(ob['id'])}", ob, f"dpf {self.p.id} {ob['id']} volume of {ob['model']}",
                     "every 24 hours", self.volume_sql(ob), [f"observability:{ob['id']}"])

        sources = self.man.get("sources", []) or []
        src_filter = " OR ".join(f'\\"{s["system_id"]}\\"' for s in sources)
        metrics: list[tuple[str, str, str, str, str, str]] = []  # id, filter, resource type, title, anchor, header
        if sources:
            self.var("extractor_log_resource_type", "Monitored resource type the extractor's logs arrive under "
                                                    "(generic_node for an agent beside the database, cloud_run_job, ...).",
                     "generic_node", True)
            if obs.get("schema_drift"):
                metrics.append(("schema_drift_breaking",
                                f'jsonPayload.dpf_alert=\\"schema_drift_breaking\\" AND jsonPayload.source_system=({src_filter})',
                                "${var.extractor_log_resource_type}", "breaking schema drift quarantined a batch",
                                "schema-drift",
                                trace(["observability:schema_drift"], reqs_of(obs["schema_drift"]),
                                      obs["schema_drift"].get("implements"))))
            metrics.append(("extract_failed",
                            f'jsonPayload.dpf_alert=\\"extract_failed\\" AND jsonPayload.source_system=({src_filter})',
                            "${var.extractor_log_resource_type}", "an extract failed and committed nothing",
                            "extract-failed",
                            trace([f"source:{s['system_id']}" for s in sources], reqs_of(*sources))))
        if self.engine == "dataform":
            metrics.append(("pipeline_failed",
                            'resource.type=\\"dataform.googleapis.com/Repository\\" AND '
                            'resource.labels.repository_id=\\"${var.dataform_repository}\\" AND '
                            'jsonPayload.terminalState=\\"FAILED\\"',
                            "dataform.googleapis.com/Repository", "a scheduled Dataform invocation failed "
                            "(a blocking check stopped publication, or an action errored)", "pipeline-failed",
                            trace([f"schedule:{s['id']}" for s in (self.man.get("orchestration") or {}).get("schedules", [])],
                                  None, "monitor-data-product") + "\n# verify: Dataform invocation completion log fields"))
        if checks:
            cfgs = ", ".join(f"google_bigquery_data_transfer_config.{c}" for c in checks)
            self.emit("monitoring.tf", trace(implements="monitor-data-product"), f"""
locals {{
  monitor_check_filter = join(" OR ", [for c in [{cfgs}] : format("resource.labels.config_id=\\"%s\\"", reverse(split("/", c.name))[0])])
}}""")
            metrics.append(("monitor_check_failed",
                            'resource.type=\\"bigquery_dts_config\\" AND severity>=ERROR AND (${local.monitor_check_filter})',
                            "bigquery_dts_config", "a freshness or volume check failed", "freshness-or-volume-breach",
                            trace([f"observability:{o['id']}" for k in ("freshness", "volume") for o in obs.get(k, []) or []],
                                  reqs_of(*(obs.get("freshness") or [])), None)))

        for mid, flt, rtype, title, anchor, hdr in metrics:
            name = f"dpf_{self.p.id}_{mid}"
            doc = f"{self.p.id}: {title}."
            if runbook:
                doc += f" Runbook: {runbook}#{anchor}"
            self.emit("monitoring.tf", hdr, f"""
resource "google_logging_metric" "{mid}" {{
  project     = var.project_id
  name        = {q(name)}
  description = {q(doc)}
  filter      = "{flt}"
  metric_descriptor {{
    metric_kind = "DELTA"
    value_type  = "INT64"
  }}
}}

resource "google_monitoring_alert_policy" "{mid}" {{
  project      = var.project_id
  display_name = {q(f"dpf {self.p.id}: {title}")}
  combiner     = "OR"
  conditions {{
    display_name = {q(title)}
    condition_threshold {{
      filter          = "metric.type=\\"logging.googleapis.com/user/${{google_logging_metric.{mid}.name}}\\" AND resource.type=\\"{rtype}\\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {{
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }}
    }}
  }}
  notification_channels = var.{chan} == "" ? [] : [var.{chan}]
  documentation {{
    mime_type = "text/markdown"
    content   = {q(doc)}
  }}
}}""")

    def quality_scans(self) -> None:
        qs = (self.man.get("observability") or {}).get("quality_scans")
        if not qs:
            return
        rules_by_model: dict[str, list[dict]] = {}
        for r in (self.man.get("quality") or {}).get("rules", []) or []:
            if r.get("on_fail") != "quarantine":
                rules_by_model.setdefault(r["model"], []).append(r)
        for model in qs["models"]:
            node = self.g.get(model)
            if node is None:
                continue
            m = node.model
            grain = list(m.get("grain_columns") or [])
            rules: list[str] = []
            for c in grain:
                rules.append(self._rule(f"{c}-not-null", "COMPLETENESS", c, "non_null_expectation {}"))
            if len(grain) == 1:
                rules.append(self._rule("grain-unique", "UNIQUENESS", grain[0], "uniqueness_expectation {}"))
            else:
                cols = ", ".join(grain)
                rules.append(self._rule("grain-unique", "UNIQUENESS", None,
                                        f"sql_assertion {{\n        sql_statement = {q(f'SELECT {cols} FROM ${{data()}} GROUP BY {cols} HAVING COUNT(*) > 1')}\n      }}"))
            for ref in (m.get("attributes") or {}).get("dim_refs", []) or []:
                if ref.get("natural_key"):
                    rules.append(self._rule(f"{ref['natural_key']}-not-null", "COMPLETENESS", ref["natural_key"],
                                            "non_null_expectation {}"))
            for r in rules_by_model.get(model, []):
                rules.append(self._quality_rule(r))
            body = "\n".join(x for x in rules if x)
            ds = self.ds.get(self.dataset_of(model))
            self.emit("quality.tf", trace(["observability:quality_scans", f"model:{model}"],
                                          reqs_of(qs, *rules_by_model.get(model, [])), qs.get("implements")), f"""
resource "google_dataplex_datascan" "dq_{model}" {{
  project      = var.project_id
  location     = var.region
  data_scan_id = {q(kebab_id("dpf", self.p.id, model))}
  display_name = {q(f"dpf {self.p.id} {model}")}
  description  = {q(f"Knowledge Catalog data quality scan of {model}: grain, keys and quality rules (generated by dpf).")}
  data {{
    resource = "//bigquery.googleapis.com/projects/${{var.project_id}}/datasets/{ds}/tables/{model}"
  }}
  execution_spec {{
    trigger {{
      schedule {{
        cron = {q(f"CRON_TZ={self.tz} {qs['schedule']}")}
      }}
    }}
  }}
  data_quality_spec {{
    sampling_percent = 100
{body}
  }}
}}""")

    @staticmethod
    def _rule(name: str, dimension: str, column: str | None, expectation: str) -> str:
        col = f"\n      column    = {q(column)}" if column else ""
        thr = "\n      threshold = 1" if column else ""
        return (f"    rules {{\n      name      = {q(kebab_id(name))}\n      dimension = {q(dimension)}{col}{thr}\n"
                f"      {expectation}\n    }}")

    def _quality_rule(self, r: dict) -> str | None:
        t, col = r.get("type"), r.get("column")
        name = kebab_id(r["id"], t or "rule")
        if t == "not_null":
            return self._rule(name, "COMPLETENESS", col, "non_null_expectation {}")
        if t == "range":
            parts = []
            if r.get("min") is not None:
                parts.append(f"min_value = {q(r['min'])}")
            if r.get("max") is not None:
                parts.append(f"max_value = {q(r['max'])}")
            return self._rule(name, "VALIDITY", col, "range_expectation {\n        " + "\n        ".join(parts) + "\n      }")
        if t == "set_membership":
            return self._rule(name, "VALIDITY", col, f"set_expectation {{\n        values = {hcl_list(r.get('values') or [])}\n      }}")
        if t == "unique":
            cols = r.get("columns") or [col]
            if len(cols) == 1:
                return self._rule(name, "UNIQUENESS", cols[0], "uniqueness_expectation {}")
            c = ", ".join(cols)
            return self._rule(name, "UNIQUENESS", None, f"sql_assertion {{\n        sql_statement = "
                                                        f"{q(f'SELECT {c} FROM ${{data()}} GROUP BY {c} HAVING COUNT(*) > 1')}\n      }}")
        if t == "custom_sql" and r.get("expression"):
            return self._rule(name, "VALIDITY", None,
                              f"row_condition_expectation {{\n        sql_expression = {q(r['expression'])}\n      }}")
        return None

    def control(self) -> None:
        if "control" not in self.ds:
            return
        sources = self.man.get("sources", []) or []
        for table, (desc, cols, clustering) in CONTROL_TABLES.items():
            schema = ",\n".join(f"    {{ name = {q(n)}, type = {q(t)}, mode = {q(m)} }}" for n, t, m in cols)
            clus = f"\n  clustering          = {hcl_list(clustering)}" if clustering else ""
            self.emit("control.tf", trace([f"source:{s['system_id']}" for s in sources], reqs_of(*sources),
                                          "land-immutable-raw"), f"""
resource "google_bigquery_table" "{table}" {{
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.control.dataset_id
  table_id            = {q(table)}
  description         = {q(desc)}
  deletion_protection = true{clus}
  schema = jsonencode([
{schema}
  ])
}}""")

    @staticmethod
    def _map(entries: list[tuple[str, str]]) -> str:
        """Render HCL map entries with `=` aligned the way `terraform fmt` does."""
        width = max((len(k) for k, _ in entries), default=0)
        return "\n".join(f"    {k.ljust(width)} = {v}" for k, v in entries)

    def outputs(self) -> None:
        ds = self._map([(k, f"google_bigquery_dataset.{k}.dataset_id") for k in self.ds])
        out = [f"""
output "datasets" {{
  description = "Dataset ids by deployment key."
  value = {{
{ds}
  }}
}}"""]
        tags = sorted({t["tag"] for t in (self.man.get("governance") or {}).get("policy_tags", []) or []})
        if tags:
            tv = self._map([(f"policy_tag_{t}", f"google_data_catalog_policy_tag.{t}.name") for t in tags])
            out.append(f"""
output "policy_tags" {{
  description = "Policy tag resource names: pass to dbt with --vars, or read by the Dataform release configuration."
  value = {{
{tv}
  }}
}}""")
        listings = [pt["sharing"]["listing_id"] for pt in self.man.get("output_ports", []) or []
                    if pt.get("access") == "sharing_listing" and pt.get("sharing")]
        if listings:
            lv = self._map([(li, f"google_bigquery_analytics_hub_listing.{li}.name") for li in listings])
            out.append(f"""
output "listings" {{
  description = "BigQuery sharing listing resource names."
  value = {{
{lv}
  }}
}}""")
        self.emit("outputs.tf", trace(implements="generate-artefacts"), "\n".join(out))

    def variables_tf(self) -> str:
        blocks = [trace(implements="generate-artefacts")]
        for name, v in self.variables.items():
            lines = [f'variable "{name}" {{', f"  description = {q(v['description'])}", "  type        = string"]
            if v["has_default"]:
                lines.append(f"  default     = {q(v['default'] if v['default'] is not None else '')}")
            lines.append("}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n"

    def render(self) -> dict[str, str]:
        self.base_variables()
        self.versions()
        self.datasets()
        self.access()
        self.policy_tags()
        self.sharing()
        self.orchestration()
        self.monitoring()
        self.quality_scans()
        self.control()
        self.outputs()
        out = {f"{ROOT}/{name}": "\n".join(blocks) for name, blocks in self.files.items()}
        out[f"{ROOT}/variables.tf"] = self.variables_tf()
        return dict(sorted(out.items()))


def render(p: Product, g: ProductGraph, actions: list[Action], engine: str) -> dict[str, str]:
    return Module(p, g, actions, engine).render()


TF_RESOURCE = re.compile(r'^resource\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"', re.M)


def resources(text: str) -> list[tuple[str, str]]:
    return TF_RESOURCE.findall(text)
