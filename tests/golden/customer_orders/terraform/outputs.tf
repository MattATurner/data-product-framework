# dpf: implements=generate-artefacts
output "datasets" {
  description = "Dataset ids by deployment key."
  value = {
    raw        = google_bigquery_dataset.raw.dataset_id
    staging    = google_bigquery_dataset.staging.dataset_id
    gold       = google_bigquery_dataset.gold.dataset_id
    assertions = google_bigquery_dataset.assertions.dataset_id
    control    = google_bigquery_dataset.control.dataset_id
  }
}
