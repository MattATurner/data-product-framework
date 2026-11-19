terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30, < 7.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.30, < 7.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "region" {
  type = string
}

variable "default_dataform_repository" {
  type = string
}

variable "state_bucket_name" {
  type = string
}

# 1. Google-managed service agents needed before any DPF product Terraform module applies.
resource "google_project_service_identity" "dataplex_agent" {
  provider = google-beta
  project  = var.project_id
  service  = "dataplex.googleapis.com"
}

resource "google_project_service_identity" "dataform_agent" {
  provider = google-beta
  project  = var.project_id
  service  = "dataform.googleapis.com"
}

resource "google_project_service_identity" "bq_dts_agent" {
  provider = google-beta
  project  = var.project_id
  service  = "bigquerydatatransfer.googleapis.com"
}

resource "google_project_iam_member" "dataplex_agent_roles" {
  for_each = toset([
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:service-${var.project_number}@gcp-sa-dataplex.iam.gserviceaccount.com"

  depends_on = [google_project_service_identity.dataplex_agent]
}

# 2. Custom Dataform execution service account (satisfies strict act-as checks and policy-tag reads).
resource "google_service_account" "dataform_runner" {
  project      = var.project_id
  account_id   = "dataform-runner"
  display_name = "DPF Dataform Pipeline Runner"
  description  = "Executes generated Dataform/dbt transformations and attaches BigQuery policy tags."
}

resource "google_project_iam_member" "dataform_runner_roles" {
  for_each = toset([
    "roles/bigquery.dataOwner",
    "roles/bigquery.jobUser",
    "roles/datacatalog.viewer",
    "roles/datacatalog.categoryFineGrainedReader",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.dataform_runner.email}"
}

resource "google_service_account_iam_member" "dataform_agent_token_creator" {
  service_account_id = google_service_account.dataform_runner.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${var.project_number}@gcp-sa-dataform.iam.gserviceaccount.com"

  depends_on = [google_project_service_identity.dataform_agent]
}

resource "google_service_account_iam_member" "dataform_agent_user" {
  service_account_id = google_service_account.dataform_runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${var.project_number}@gcp-sa-dataform.iam.gserviceaccount.com"

  depends_on = [google_project_service_identity.dataform_agent]
}

# 3. Custom DPF Monitor service account (executes business-hours freshness and volume checks).
resource "google_service_account" "dpf_monitor" {
  project      = var.project_id
  account_id   = "dpf-monitor"
  display_name = "DPF Observability Monitor"
  description  = "Runs scheduled BigQuery freshness and volume SLO queries."
}

resource "google_project_iam_member" "dpf_monitor_roles" {
  for_each = toset([
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.dpf_monitor.email}"
}

resource "google_service_account_iam_member" "dts_agent_token_creator" {
  service_account_id = google_service_account.dpf_monitor.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${var.project_number}@gcp-sa-bigquerydatatransfer.iam.gserviceaccount.com"

  depends_on = [google_project_service_identity.bq_dts_agent]
}

# 4. Workspace state & output bucket (mirrors l400-agentic-data-analytics state backup pattern).
resource "google_storage_bucket" "dpf_state" {
  project                     = var.project_id
  name                        = var.state_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }
}

# 5. Default Dataform repository wired to dataform-runner service account.
resource "google_dataform_repository" "default" {
  provider        = google-beta
  project         = var.project_id
  region          = var.region
  name            = var.default_dataform_repository
  display_name    = var.default_dataform_repository
  service_account = google_service_account.dataform_runner.email

  depends_on = [
    google_service_account_iam_member.dataform_agent_token_creator,
    google_service_account_iam_member.dataform_agent_user,
  ]
}

output "dataform_service_account" {
  value = google_service_account.dataform_runner.email
}

output "monitor_service_account" {
  value = google_service_account.dpf_monitor.email
}

output "dataform_repository" {
  value = google_dataform_repository.default.name
}

output "state_bucket" {
  value = google_storage_bucket.dpf_state.name
}
