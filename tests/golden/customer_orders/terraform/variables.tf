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

variable "sales_ops_group" {
  description = "Google group email: Sales Operations."
  type        = string
}

variable "data_analytics_group" {
  description = "Google group email: Data Analytics."
  type        = string
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

variable "dataform_service_account" {
  description = "Service account workflow invocations run as. Empty: the Dataform service agent."
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
