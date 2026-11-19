terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30, < 7.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "impersonation_account" {
  description = "IAM principal (user:... or serviceAccount:...) allowed to impersonate the deployer SA."
  type        = string
}

locals {
  # Scoped least-privilege roles required to provision Layer-0 and Layer-1 DPF resources
  # without granting permanent project roles/owner or organization-root Org Policy Admin.
  deployer_roles = toset([
    "roles/analyticshub.admin",
    "roles/bigquery.admin",
    "roles/bigquerydatapolicy.admin",
    "roles/cloudscheduler.admin",
    "roles/datacatalog.admin",
    "roles/dataform.admin",
    "roles/dataplex.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/logging.admin",
    "roles/monitoring.admin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/workflows.admin",
  ])
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "dpf-deployer"
  display_name = "DPF Terraform Bootstrap Deployer"
  description  = "Impersonated service account used by deploy.sh to provision DPF foundation resources without exported keys."
}

resource "google_project_iam_member" "deployer_roles" {
  for_each = local.deployer_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.impersonation_account
}

output "deployment_service_account" {
  value = google_service_account.deployer.email
}
