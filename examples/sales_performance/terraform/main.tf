terraform {
  required_version = ">= 1.5"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type    = string
  default = "data-product-framework"
}

variable "region" {
  type    = string
  default = "us-central1"
}

locals {
  datasets = {
    raw_ora_local  = "Immutable landing zone. Append-only, source-shaped."
    stg_sales      = "Typed, deduplicated staging. Methodology-neutral."
    slv_sales      = "Silver: Kimball dimensional models."
    gold_sales     = "Gold: published data product output ports."
    dpf_assertions = "Dataform assertion results."
    dpf_control    = "Extract watermarks and run control."
  }
}

resource "google_bigquery_dataset" "d" {
  for_each      = local.datasets
  dataset_id    = each.key
  location      = var.region
  description   = each.value
  friendly_name = each.key

  labels = {
    managed_by = "data-product-framework"
    product    = "sales-performance"
  }
}

# --- R-12: analysts must not see customer contact details -------------------
resource "google_data_catalog_taxonomy" "pii" {
  display_name           = "dpf-pii"
  region                 = var.region
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}

resource "google_data_catalog_policy_tag" "contact" {
  taxonomy     = google_data_catalog_taxonomy.pii.id
  display_name = "pii/contact"
  description  = "Customer contact details. Masked for the analyst role (BRD R-12)."
}

# Attach in the table schema; grant fine-grained reader only to roles that need it.
# Note: the IAM identifier keeps its legacy string.
#   roles/datacatalog.categoryFineGrainedReader

output "datasets" {
  value = [for d in google_bigquery_dataset.d : d.dataset_id]
}

output "contact_policy_tag" {
  value = google_data_catalog_policy_tag.contact.id
}
