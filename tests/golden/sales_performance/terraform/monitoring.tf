# dpf: element=observability:OB-1 satisfies=R-10
resource "google_bigquery_data_transfer_config" "freshness_ob_1" {
  project              = var.project_id
  display_name         = "dpf sales_performance OB-1 freshness of sales_performance_monthly"
  location             = var.region
  data_source_id       = "scheduled_query"
  schedule             = "every 15 minutes"
  service_account_name = var.monitor_service_account == "" ? null : var.monitor_service_account
  email_preferences {
    enable_failure_email = true
  }
  params = {
    query = <<-SQL
      -- OB-1: sales_performance_monthly must be no older than 90 minutes (PT1H30M), MON TUE WED THU FRI 08:00-18:00 Australia/Perth.
      -- A breach (or a missing table) fails the query, which fails the transfer run and raises the alert.
      SELECT
        IF(age_minutes IS NULL OR age_minutes > 90,
           ERROR(FORMAT('dpf_freshness_breach OB-1 sales_performance.sales_performance_monthly age_minutes=%s max_minutes=90',
                        IFNULL(CAST(age_minutes AS STRING), 'missing'))),
           'fresh') AS status
      FROM (
        SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP_MILLIS(MAX(last_modified_time)), MINUTE) AS age_minutes
        FROM `${var.project_id}.gold_sales.__TABLES__`
        WHERE table_id = 'sales_performance_monthly'
      )
      WHERE EXTRACT(DAYOFWEEK FROM CURRENT_DATETIME('Australia/Perth')) IN (2, 3, 4, 5, 6)
        AND CURRENT_TIME('Australia/Perth') BETWEEN TIME '08:00:00' AND TIME '18:00:00'
    SQL
  }
}

# dpf: element=observability:OB-2 satisfies=R-13
resource "google_bigquery_data_transfer_config" "freshness_ob_2" {
  project              = var.project_id
  display_name         = "dpf sales_performance OB-2 freshness of sales_performance_partner_extract"
  location             = var.region
  data_source_id       = "scheduled_query"
  schedule             = "every 24 hours"
  service_account_name = var.monitor_service_account == "" ? null : var.monitor_service_account
  email_preferences {
    enable_failure_email = true
  }
  params = {
    query = <<-SQL
      -- OB-2: sales_performance_partner_extract must be no older than 46080 minutes (P32D), at all times.
      -- A breach (or a missing table) fails the query, which fails the transfer run and raises the alert.
      SELECT
        IF(age_minutes IS NULL OR age_minutes > 46080,
           ERROR(FORMAT('dpf_freshness_breach OB-2 sales_performance.sales_performance_partner_extract age_minutes=%s max_minutes=46080',
                        IFNULL(CAST(age_minutes AS STRING), 'missing'))),
           'fresh') AS status
      FROM (
        SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP_MILLIS(MAX(last_modified_time)), MINUTE) AS age_minutes
        FROM `${var.project_id}.share_sales_partner.__TABLES__`
        WHERE table_id = 'sales_performance_partner_extract'
      )
    SQL
  }
}

# dpf: element=observability:OB-3 implements=monitor-data-product
resource "google_bigquery_data_transfer_config" "volume_ob_3" {
  project              = var.project_id
  display_name         = "dpf sales_performance OB-3 volume of fct_order_line"
  location             = var.region
  data_source_id       = "scheduled_query"
  schedule             = "every 24 hours"
  service_account_name = var.monitor_service_account == "" ? null : var.monitor_service_account
  email_preferences {
    enable_failure_email = true
  }
  params = {
    query = <<-SQL
      -- OB-3: fct_order_line should hold 40000 rows (+/-60%) per P1D window of order_date.
      SELECT IF(n BETWEEN 16000 AND 64000, 'ok',
                ERROR(FORMAT('dpf_volume_breach OB-3 sales_performance.fct_order_line rows=%d expected=40000 tolerance_pct=60', n))) AS status
      FROM (
        SELECT COUNT(*) AS n
        FROM `${var.project_id}.slv_sales.fct_order_line`
        WHERE order_date >= DATE_SUB(CURRENT_DATE('Australia/Perth'), INTERVAL 1 DAY)
          AND order_date < CURRENT_DATE('Australia/Perth')
      )
    SQL
  }
}

# dpf: implements=monitor-data-product
locals {
  monitor_check_filter = join(" OR ", [for c in [google_bigquery_data_transfer_config.freshness_ob_1, google_bigquery_data_transfer_config.freshness_ob_2, google_bigquery_data_transfer_config.volume_ob_3] : format("resource.labels.config_id=\"%s\"", reverse(split("/", c.name))[0])])
}

# dpf: element=observability:schema_drift implements=monitor-data-product
resource "google_logging_metric" "schema_drift_breaking" {
  project     = var.project_id
  name        = "dpf_sales_performance_schema_drift_breaking"
  description = "sales_performance: breaking schema drift quarantined a batch. Runbook: examples/sales_performance/RUNBOOK.md#schema-drift"
  filter      = "jsonPayload.dpf_alert=\"schema_drift_breaking\" AND jsonPayload.source_system=(\"ora_local\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "schema_drift_breaking" {
  project      = var.project_id
  display_name = "dpf sales_performance: breaking schema drift quarantined a batch"
  combiner     = "OR"
  conditions {
    display_name = "breaking schema drift quarantined a batch"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.schema_drift_breaking.name}\" AND resource.type=\"${var.extractor_log_resource_type}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = var.alert_channel == "" ? [] : [var.alert_channel]
  documentation {
    mime_type = "text/markdown"
    content   = "sales_performance: breaking schema drift quarantined a batch. Runbook: examples/sales_performance/RUNBOOK.md#schema-drift"
  }
}

# dpf: element=source:ora_local satisfies=R-10
resource "google_logging_metric" "extract_failed" {
  project     = var.project_id
  name        = "dpf_sales_performance_extract_failed"
  description = "sales_performance: an extract failed and committed nothing. Runbook: examples/sales_performance/RUNBOOK.md#extract-failed"
  filter      = "jsonPayload.dpf_alert=\"extract_failed\" AND jsonPayload.source_system=(\"ora_local\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "extract_failed" {
  project      = var.project_id
  display_name = "dpf sales_performance: an extract failed and committed nothing"
  combiner     = "OR"
  conditions {
    display_name = "an extract failed and committed nothing"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.extract_failed.name}\" AND resource.type=\"${var.extractor_log_resource_type}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = var.alert_channel == "" ? [] : [var.alert_channel]
  documentation {
    mime_type = "text/markdown"
    content   = "sales_performance: an extract failed and committed nothing. Runbook: examples/sales_performance/RUNBOOK.md#extract-failed"
  }
}

# dpf: element=schedule:hourly,schedule:monthly implements=monitor-data-product
# verify: Dataform invocation completion log fields
resource "google_logging_metric" "pipeline_failed" {
  project     = var.project_id
  name        = "dpf_sales_performance_pipeline_failed"
  description = "sales_performance: a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored). Runbook: examples/sales_performance/RUNBOOK.md#pipeline-failed"
  filter      = "resource.type=\"dataform.googleapis.com/Repository\" AND resource.labels.repository_id=\"${var.dataform_repository}\" AND jsonPayload.terminalState=\"FAILED\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "pipeline_failed" {
  project      = var.project_id
  display_name = "dpf sales_performance: a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored)"
  combiner     = "OR"
  conditions {
    display_name = "a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored)"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.pipeline_failed.name}\" AND resource.type=\"dataform.googleapis.com/Repository\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = var.alert_channel == "" ? [] : [var.alert_channel]
  documentation {
    mime_type = "text/markdown"
    content   = "sales_performance: a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored). Runbook: examples/sales_performance/RUNBOOK.md#pipeline-failed"
  }
}

# dpf: element=observability:OB-1,observability:OB-2,observability:OB-3 satisfies=R-10,R-13
resource "google_logging_metric" "monitor_check_failed" {
  project     = var.project_id
  name        = "dpf_sales_performance_monitor_check_failed"
  description = "sales_performance: a freshness or volume check failed. Runbook: examples/sales_performance/RUNBOOK.md#freshness-or-volume-breach"
  filter      = "resource.type=\"bigquery_dts_config\" AND severity>=ERROR AND (${local.monitor_check_filter})"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "monitor_check_failed" {
  project      = var.project_id
  display_name = "dpf sales_performance: a freshness or volume check failed"
  combiner     = "OR"
  conditions {
    display_name = "a freshness or volume check failed"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.monitor_check_failed.name}\" AND resource.type=\"bigquery_dts_config\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = var.alert_channel == "" ? [] : [var.alert_channel]
  documentation {
    mime_type = "text/markdown"
    content   = "sales_performance: a freshness or volume check failed. Runbook: examples/sales_performance/RUNBOOK.md#freshness-or-volume-breach"
  }
}
