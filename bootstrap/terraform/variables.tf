variable "gcp_account_name" {
  description = "Email address of the active gcloud user running the bootstrap."
  type        = string
}

variable "project_id" {
  description = "Base GCP Project ID (a 4-char suffix is appended when creating a new project unless append_random_suffix = false)."
  type        = string
  default     = "dpf-workspace"
}

variable "project_name" {
  description = "Display name when creating a new GCP project (defaults to resolved project_id)."
  type        = string
  default     = ""
}

variable "project_number" {
  description = "Leave empty to create a new GCP project; set to the 12-digit project number when attaching to an existing customer project."
  type        = string
  default     = ""
}

variable "append_random_suffix" {
  description = "Append a 4-char random suffix when creating a new project so globally unique IDs never collide."
  type        = bool
  default     = true
}

variable "org_id" {
  description = "GCP Organization ID (set '0' when running as a non-org-admin on an existing project)."
  type        = string
  default     = "0"
}

variable "folder_id" {
  description = "Optional GCP Folder ID parent when creating a new project inside a subfolder instead of the root org."
  type        = string
  default     = ""
}

variable "billing_account" {
  description = "Billing Account ID (XXXXXX-XXXXXX-XXXXXX); required only when creating a new project."
  type        = string
  default     = ""
}

variable "region" {
  description = "Primary Google Cloud region for BigQuery, Dataform, and Knowledge Catalog."
  type        = string
  default     = "us-central1"
}

variable "business_timezone" {
  description = "IANA business calendar timezone written into registry/platform-defaults.yaml (e.g. Pacific/Auckland, Australia/Perth)."
  type        = string
  default     = "Australia/Perth"
}

variable "default_dataform_repository" {
  description = "Name of the initial Dataform repository created in the project."
  type        = string
  default     = "sales-performance"
}

variable "deployment_service_account_name" {
  description = "Optional existing service account email when running from CI instead of an interactive user."
  type        = string
  default     = ""
}

variable "relax_domain_org_policy" {
  description = "Relax iam.allowedPolicyMemberDomains on the project when testing cross-domain BigQuery sharing listings in a sandbox."
  type        = bool
  default     = false
}
