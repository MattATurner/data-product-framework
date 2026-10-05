# dpf: implements=generate-artefacts
output "datasets" {
  description = "Dataset ids by deployment key."
  value = {
    raw        = google_bigquery_dataset.raw.dataset_id
    staging    = google_bigquery_dataset.staging.dataset_id
    silver     = google_bigquery_dataset.silver.dataset_id
    gold       = google_bigquery_dataset.gold.dataset_id
    share      = google_bigquery_dataset.share.dataset_id
    assertions = google_bigquery_dataset.assertions.dataset_id
    control    = google_bigquery_dataset.control.dataset_id
  }
}

output "policy_tags" {
  description = "Policy tag resource names: pass to dbt with --vars, or read by the Dataform release configuration."
  value = {
    policy_tag_pii_contact = google_data_catalog_policy_tag.pii_contact.name
  }
}

output "listings" {
  description = "BigQuery sharing listing resource names."
  value = {
    sales_performance_monthly_extract = google_bigquery_analytics_hub_listing.sales_performance_monthly_extract.name
  }
}
