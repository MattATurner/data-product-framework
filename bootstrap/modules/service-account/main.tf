terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30"
    }
  }
}

variable "project_id" {
  type = string
}

variable "org_id" {
  type    = string
  default = "0"
}

variable "impersonation_account" {
  description = "IAM principal (user:... or serviceAccount:...) allowed to impersonate the deployer SA."
  type        = string
}

variable "gcp_account_name" {
  type = string
}

variable "grant_org_policy_admin" {
  type    = bool
  default = false
}

resource "google_project_iam_member" "caller_owner" {
  count   = var.org_id != "0" && var.org_id != "" ? 1 : 0
  project = var.project_id
  role    = "roles/owner"
  member  = var.impersonation_account
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "dpf-deployer"
  display_name = "DPF Terraform Bootstrap Deployer"
  description  = "Impersonated service account used by deploy.sh to provision DPF foundation resources without exported keys."

  depends_on = [google_project_iam_member.caller_owner]
}

resource "google_project_iam_member" "deployer_owner" {
  project = var.project_id
  role    = "roles/owner"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_organization_iam_member" "deployer_org_policy_admin" {
  count  = var.grant_org_policy_admin && var.org_id != "0" && var.org_id != "" ? 1 : 0
  org_id = var.org_id
  role   = "roles/orgpolicy.policyAdmin"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_impersonation" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.impersonation_account
}

output "deployment_service_account" {
  value = google_service_account.deployer.email
}
