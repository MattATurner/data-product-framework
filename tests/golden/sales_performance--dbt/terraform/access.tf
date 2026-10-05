# dpf: element=port:sales_performance_monthly,port:sales_order_line_detail dataset=gold satisfies=R-1,R-2,R-7
resource "google_bigquery_dataset_access" "gold_consumer_group" {
  project        = var.project_id
  dataset_id     = google_bigquery_dataset.gold.dataset_id
  role           = "READER"
  group_by_email = var.consumer_group
}

# dpf: element=port:sales_performance_monthly,port:sales_order_line_detail dataset=gold satisfies=R-1,R-2,R-7
resource "google_bigquery_dataset_access" "gold_analyst_group" {
  project        = var.project_id
  dataset_id     = google_bigquery_dataset.gold.dataset_id
  role           = "READER"
  group_by_email = var.analyst_group
}

# dpf: dataset=silver implements=generate-artefacts
resource "google_bigquery_dataset_access" "silver_analyst_group" {
  project        = var.project_id
  dataset_id     = google_bigquery_dataset.silver.dataset_id
  role           = "READER"
  group_by_email = var.analyst_group
}

# dpf: element=port:sales_order_line_detail satisfies=R-2
resource "google_bigquery_dataset_access" "silver_authorizes_gold_views" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.silver.dataset_id
  dataset {
    dataset {
      project_id = var.project_id
      dataset_id = google_bigquery_dataset.gold.dataset_id
    }
    target_types = ["VIEWS"]
  }
}
