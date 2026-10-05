# dpf: element=policy:PT-1 satisfies=R-12 implements=generate-artefacts
resource "google_dataform_repository_release_config" "product" {
  provider      = google-beta
  project       = var.project_id
  region        = var.region
  repository    = var.dataform_repository
  name          = "sales-performance"
  git_commitish = var.dataform_git_commitish
  cron_schedule = "0 * * * *"
  time_zone     = "Australia/Perth"
  code_compilation_config {
    default_database = var.project_id
    default_schema   = "stg_sales"
    default_location = var.region
    assertion_schema = "dpf_assertions"
    vars = {
      raw_dataset            = "raw_ora_local"
      staging_dataset        = "stg_sales"
      silver_dataset         = "slv_sales"
      gold_dataset           = "gold_sales"
      share_dataset          = "share_sales_partner"
      assertions_dataset     = "dpf_assertions"
      control_dataset        = "dpf_control"
      business_timezone      = "Australia/Perth"
      policy_tag_pii_contact = google_data_catalog_policy_tag.pii_contact.name
    }
  }
}

# dpf: element=schedule:hourly satisfies=R-10
resource "google_dataform_repository_workflow_config" "hourly" {
  provider       = google-beta
  project        = var.project_id
  region         = var.region
  repository     = var.dataform_repository
  name           = "sales-performance-hourly"
  release_config = google_dataform_repository_release_config.product.id
  cron_schedule  = "10 * * * *"
  time_zone      = "Australia/Perth"
  invocation_config {
    included_tags                            = ["hourly"]
    transitive_dependencies_included         = false
    fully_refresh_incremental_tables_enabled = false
    service_account                          = var.dataform_service_account == "" ? null : var.dataform_service_account
  }
}

# dpf: element=schedule:monthly satisfies=R-13
resource "google_dataform_repository_workflow_config" "monthly" {
  provider       = google-beta
  project        = var.project_id
  region         = var.region
  repository     = var.dataform_repository
  name           = "sales-performance-monthly"
  release_config = google_dataform_repository_release_config.product.id
  cron_schedule  = "0 7 2 * *"
  time_zone      = "Australia/Perth"
  invocation_config {
    included_tags                            = ["monthly"]
    transitive_dependencies_included         = false
    fully_refresh_incremental_tables_enabled = false
    service_account                          = var.dataform_service_account == "" ? null : var.dataform_service_account
  }
}
