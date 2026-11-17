resource "random_string" "suffix" {
  length  = 4
  special = false
  upper   = false
}

locals {
  create_new_project = var.project_number == ""
  resolved_project_id = (
    local.create_new_project && var.append_random_suffix
    ? "${var.project_id}-${random_string.suffix.result}"
    : var.project_id
  )
  resolved_project_name = var.project_name != "" ? var.project_name : local.resolved_project_id
  impersonation_member = (
    var.deployment_service_account_name == ""
    ? "user:${var.gcp_account_name}"
    : "serviceAccount:${var.deployment_service_account_name}"
  )
  state_bucket_name = "${local.resolved_project_id}-dpf-state"
}

# Caller provider: creates the project (when new), enables initial APIs, and sets up deployer SA impersonation.
provider "google" {
  project = local.resolved_project_id
  region  = var.region
}

provider "google-beta" {
  project = local.resolved_project_id
  region  = var.region
}

# Keyless Service Account Impersonation providers for downstream foundation resources.
provider "google" {
  alias                       = "impersonated"
  impersonate_service_account = "dpf-deployer@${local.resolved_project_id}.iam.gserviceaccount.com"
  project                     = local.resolved_project_id
  region                      = var.region
  billing_project             = local.resolved_project_id
  user_project_override       = true
}

provider "google-beta" {
  alias                       = "impersonated"
  impersonate_service_account = "dpf-deployer@${local.resolved_project_id}.iam.gserviceaccount.com"
  project                     = local.resolved_project_id
  region                      = var.region
  billing_project             = local.resolved_project_id
  user_project_override       = true
}

module "project" {
  count           = local.create_new_project ? 1 : 0
  source          = "../modules/project"
  project_id      = local.resolved_project_id
  project_name    = local.resolved_project_name
  billing_account = var.billing_account
  org_id          = var.org_id
  folder_id       = var.folder_id
}

module "apis" {
  source     = "../modules/apis-batch-enable"
  project_id = local.resolved_project_id

  depends_on = [module.project]
}

module "service_account" {
  source                 = "../modules/service-account"
  project_id             = local.resolved_project_id
  org_id                 = var.org_id
  impersonation_account  = local.impersonation_member
  gcp_account_name       = var.gcp_account_name
  grant_org_policy_admin = var.relax_domain_org_policy

  depends_on = [module.project, module.apis]
}

resource "time_sleep" "iam_propagation" {
  create_duration = "90s"

  depends_on = [
    module.project,
    module.apis,
    module.service_account,
  ]
}

module "org_policies" {
  count      = var.relax_domain_org_policy && var.org_id != "0" && var.org_id != "" ? 1 : 0
  source     = "../modules/org-policies"
  project_id = local.resolved_project_id
  providers = {
    google = google.impersonated
  }

  depends_on = [time_sleep.iam_propagation]
}

module "dpf_foundation" {
  source                      = "../modules/dpf-foundation"
  project_id                  = local.resolved_project_id
  project_number              = local.create_new_project ? module.project[0].project_number : var.project_number
  region                      = var.region
  default_dataform_repository = var.default_dataform_repository
  state_bucket_name           = local.state_bucket_name
  providers = {
    google      = google.impersonated
    google-beta = google-beta.impersonated
  }

  depends_on = [
    time_sleep.iam_propagation,
    module.org_policies,
  ]
}
