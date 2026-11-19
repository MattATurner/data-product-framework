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
  description = "Globally unique GCP Project ID to create."
  type        = string
}

variable "project_name" {
  description = "Human-readable GCP Project display name."
  type        = string
}

variable "billing_account" {
  description = "Billing Account ID (XXXXXX-XXXXXX-XXXXXX)."
  type        = string
}

variable "org_id" {
  description = "Organization ID (set empty or '0' when using folder_id)."
  type        = string
  default     = ""
}

variable "folder_id" {
  description = "Optional Folder ID (folders/12345 or 12345); takes precedence over org_id when non-empty."
  type        = string
  default     = ""
}

resource "google_project" "project" {
  name            = var.project_name
  project_id      = var.project_id
  billing_account = var.billing_account
  org_id          = var.folder_id == "" && var.org_id != "" && var.org_id != "0" ? var.org_id : null
  folder_id       = var.folder_id != "" ? var.folder_id : null

  timeouts {
    create = "15m"
  }
}

output "project_id" {
  value = google_project.project.project_id
}

output "project_number" {
  value = google_project.project.number
}
