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

variable "allowed_domain_customer_ids" {
  description = "Optional Cloud Identity / Workspace customer IDs (e.g. C01234567) to allowlist instead of full sandbox relaxation."
  type        = list(string)
  default     = []
}

# Applied at project scope by the caller's existing Org Policy Admin privileges (never granting org-root admin to a project SA).
resource "google_org_policy_policy" "allowed_policy_member_domains" {
  name   = "projects/${var.project_id}/policies/iam.allowedPolicyMemberDomains"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      allow_all = length(var.allowed_domain_customer_ids) == 0 ? "TRUE" : null
      dynamic "values" {
        for_each = length(var.allowed_domain_customer_ids) > 0 ? [1] : []
        content {
          allowed_values = var.allowed_domain_customer_ids
        }
      }
    }
  }
}
