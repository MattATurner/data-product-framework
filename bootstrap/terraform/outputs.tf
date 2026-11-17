output "gcp_account_name" {
  value = var.gcp_account_name
}

output "project_id" {
  value = local.resolved_project_id
}

output "project_number" {
  value = local.create_new_project ? module.project[0].project_number : var.project_number
}

output "region" {
  value = var.region
}

output "business_timezone" {
  value = var.business_timezone
}

output "deployment_service_account" {
  value = module.service_account.deployment_service_account
}

output "dataform_service_account" {
  value = module.dpf_foundation.dataform_service_account
}

output "monitor_service_account" {
  value = module.dpf_foundation.monitor_service_account
}

output "dataform_repository" {
  value = module.dpf_foundation.dataform_repository
}

output "terraform_output_bucket" {
  value = module.dpf_foundation.state_bucket
}
