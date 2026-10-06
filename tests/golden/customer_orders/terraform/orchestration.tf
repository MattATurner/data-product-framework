# dpf: implements=generate-artefacts
resource "google_dataform_repository_release_config" "product" {
  provider      = google-beta
  project       = var.project_id
  region        = var.region
  repository    = var.dataform_repository
  name          = "customer-orders"
  git_commitish = var.dataform_git_commitish
  cron_schedule = var.dataform_release_schedule == "" ? null : var.dataform_release_schedule
  time_zone     = "Australia/Perth"
  code_compilation_config {
    default_database = var.project_id
    default_schema   = "stg_orders"
    default_location = var.region
    assertion_schema = "dpf_assertions"
    vars = {
      raw_dataset        = "raw_example_files"
      staging_dataset    = "stg_orders"
      gold_dataset       = "gold_orders"
      assertions_dataset = "dpf_assertions"
      control_dataset    = "dpf_control"
      business_timezone  = "Australia/Perth"
    }
  }
}

# dpf: element=schedule:daily satisfies=R-6
resource "google_dataform_repository_workflow_config" "daily" {
  provider       = google-beta
  project        = var.project_id
  region         = var.region
  repository     = var.dataform_repository
  name           = "customer-orders-daily"
  release_config = google_dataform_repository_release_config.product.id
  cron_schedule  = "0 6 * * *"
  time_zone      = "Australia/Perth"
  invocation_config {
    included_tags                            = ["daily"]
    transitive_dependencies_included         = false
    fully_refresh_incremental_tables_enabled = false
    service_account                          = var.dataform_service_account == "" ? null : var.dataform_service_account
  }
}
