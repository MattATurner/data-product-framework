# dpf: implements=generate-artefacts

variable "project_id" {
  description = "Project hosting the product's datasets."
  type        = string
  default     = "data-product-framework"
}

variable "region" {
  description = "BigQuery location and region for every regional resource."
  type        = string
  default     = "us-central1"
}

variable "consumer_group" {
  description = "Google group email: Sales leadership, Sales Operations and Finance."
  type        = string
}

variable "analyst_group" {
  description = "Google group email: General analysts; customer contact details are masked."
  type        = string
}

variable "contact_reader_group" {
  description = "Google group email allowed to read the unmasked values of tagged columns."
  type        = string
}

variable "partner_subscriber" {
  description = "IAM member granted subscriber on the listing, e.g. group:analytics@partner.example. Empty: no subscriber yet."
  type        = string
  default     = ""
}

variable "dataform_repository" {
  description = "Existing Dataform repository (name) whose default branch holds the generated dataform/ tree."
  type        = string
}

variable "dataform_git_commitish" {
  description = "Branch, tag or commit the release configuration compiles."
  type        = string
  default     = "main"
}

variable "dataform_release_schedule" {
  description = "Cron for automatic release compilation. Empty: no automatic release, so each deploy compiles and releases (required for a Dataform-hosted repository with strict act-as checks)."
  type        = string
  default     = "0 * * * *"
}

variable "dataform_service_account" {
  description = "Service account workflow invocations run as (needed under strict act-as checks). Empty: the repository's default service account."
  type        = string
  default     = ""
}

variable "alert_channel" {
  description = "Cloud Monitoring notification channel (projects/<p>/notificationChannels/<id>). Empty: alert policies are created without a channel."
  type        = string
  default     = ""
}

variable "monitor_service_account" {
  description = "Service account the scheduled checks run as. Empty: the caller's credentials."
  type        = string
  default     = ""
}

variable "extractor_log_resource_type" {
  description = "Monitored resource type the extractor's logs arrive under (generic_node for an agent beside the database, cloud_run_job, ...)."
  type        = string
  default     = "generic_node"
}
