# dpf: element=port:customer_orders dataset=gold satisfies=R-1,R-8
resource "google_bigquery_dataset_access" "gold_sales_ops_group" {
  project        = var.project_id
  dataset_id     = google_bigquery_dataset.gold.dataset_id
  role           = "READER"
  group_by_email = var.sales_ops_group
}

# dpf: element=port:customer_orders dataset=gold satisfies=R-1,R-8
resource "google_bigquery_dataset_access" "gold_data_analytics_group" {
  project        = var.project_id
  dataset_id     = google_bigquery_dataset.gold.dataset_id
  role           = "READER"
  group_by_email = var.data_analytics_group
}
