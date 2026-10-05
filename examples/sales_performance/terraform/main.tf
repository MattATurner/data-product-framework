# Root module for the sales_performance example.
#
# Every resource is generated: run `dpf generate sales_performance` first, which writes the
# module to generated/sales_performance/terraform/. This wrapper only configures providers
# and passes inputs, so a change to the product is a change to products/sales_performance/,
# never to Terraform written by hand.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

module "sales_performance" {
  source = "../../../generated/sales_performance/terraform"

  project_id                  = var.project_id
  region                      = var.region
  consumer_group              = var.consumer_group
  analyst_group               = var.analyst_group
  contact_reader_group        = var.contact_reader_group
  partner_subscriber          = var.partner_subscriber
  dataform_repository         = var.dataform_repository
  dataform_git_commitish      = var.dataform_git_commitish
  dataform_service_account    = var.dataform_service_account
  alert_channel               = var.alert_channel
  monitor_service_account     = var.monitor_service_account
  extractor_log_resource_type = var.extractor_log_resource_type
}
