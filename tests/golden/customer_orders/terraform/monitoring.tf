# dpf: element=observability:OB-1 satisfies=R-6
resource "google_bigquery_data_transfer_config" "freshness_ob_1" {
  project              = var.project_id
  display_name         = "dpf customer_orders OB-1 freshness of customer_orders"
  location             = var.region
  data_source_id       = "scheduled_query"
  schedule             = "every 1 hours"
  service_account_name = var.monitor_service_account == "" ? null : var.monitor_service_account
  email_preferences {
    enable_failure_email = true
  }
  params = {
    query = <<-SQL
      -- OB-1: customer_orders must be no older than 780 minutes (PT13H), MON TUE WED THU FRI SAT SUN 07:00-18:00 Australia/Perth.
      -- A breach (or a missing table) fails the query, which fails the transfer run and raises the alert.
      SELECT
        IF(age_minutes IS NULL OR age_minutes > 780,
           ERROR(FORMAT('dpf_freshness_breach OB-1 customer_orders.customer_orders age_minutes=%s max_minutes=780',
                        IFNULL(CAST(age_minutes AS STRING), 'missing'))),
           'fresh') AS status
      FROM (
        SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP_MILLIS(MAX(last_modified_time)), MINUTE) AS age_minutes
        FROM `${var.project_id}.gold_orders.__TABLES__`
        WHERE table_id = 'customer_orders'
      )
      WHERE EXTRACT(DAYOFWEEK FROM CURRENT_DATETIME('Australia/Perth')) IN (2, 3, 4, 5, 6, 7, 1)
        AND CURRENT_TIME('Australia/Perth') BETWEEN TIME '07:00:00' AND TIME '18:00:00'
    SQL
  }
}

# dpf: implements=monitor-data-product
locals {
  monitor_check_filter = join(" OR ", [for c in [google_bigquery_data_transfer_config.freshness_ob_1] : format("resource.labels.config_id=\"%s\"", reverse(split("/", c.name))[0])])
}

# dpf: element=observability:schema_drift implements=monitor-data-product
resource "google_logging_metric" "schema_drift_breaking" {
  project     = var.project_id
  name        = "dpf_customer_orders_schema_drift_breaking"
  description = "customer_orders: breaking schema drift quarantined a batch."
  filter      = "jsonPayload.dpf_alert=\"schema_drift_breaking\" AND jsonPayload.source_system=(\"example_files\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "schema_drift_breaking" {
  project      = var.project_id
  display_name = "dpf customer_orders: breaking schema drift quarantined a batch"
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
    content   = "customer_orders: breaking schema drift quarantined a batch."
  }
}

# dpf: element=source:example_files satisfies=R-6
resource "google_logging_metric" "extract_failed" {
  project     = var.project_id
  name        = "dpf_customer_orders_extract_failed"
  description = "customer_orders: an extract failed and committed nothing."
  filter      = "jsonPayload.dpf_alert=\"extract_failed\" AND jsonPayload.source_system=(\"example_files\")"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "extract_failed" {
  project      = var.project_id
  display_name = "dpf customer_orders: an extract failed and committed nothing"
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
    content   = "customer_orders: an extract failed and committed nothing."
  }
}

# dpf: element=schedule:daily implements=monitor-data-product
# verify: Dataform invocation completion log fields
resource "google_logging_metric" "pipeline_failed" {
  project     = var.project_id
  name        = "dpf_customer_orders_pipeline_failed"
  description = "customer_orders: a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored)."
  filter      = "resource.type=\"dataform.googleapis.com/Repository\" AND resource.labels.repository_id=\"${var.dataform_repository}\" AND jsonPayload.terminalState=\"FAILED\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "pipeline_failed" {
  project      = var.project_id
  display_name = "dpf customer_orders: a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored)"
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
    content   = "customer_orders: a scheduled Dataform invocation failed (a blocking check stopped publication, or an action errored)."
  }
}

# dpf: element=observability:OB-1 satisfies=R-6
resource "google_logging_metric" "monitor_check_failed" {
  project     = var.project_id
  name        = "dpf_customer_orders_monitor_check_failed"
  description = "customer_orders: a freshness or volume check failed."
  filter      = "resource.type=\"bigquery_dts_config\" AND severity>=ERROR AND (${local.monitor_check_filter})"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "monitor_check_failed" {
  project      = var.project_id
  display_name = "dpf customer_orders: a freshness or volume check failed"
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
    content   = "customer_orders: a freshness or volume check failed."
  }
}
