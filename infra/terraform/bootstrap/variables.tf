variable "project_id" {
  description = "Globally unique GCP project ID to create, e.g. gpu-inf-<yourname>-2026."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "6-30 chars, lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "project_name" {
  type    = string
  default = "gpu-inference-platform"
}

variable "billing_account" {
  description = "Billing account ID in the form XXXXXX-XXXXXX-XXXXXX."
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "state_bucket_location" {
  type    = string
  default = "US"
}

variable "deletion_policy" {
  description = "PREVENT keeps the project on terraform destroy; DELETE removes it."
  type        = string
  default     = "PREVENT"
  validation {
    condition     = contains(["PREVENT", "DELETE", "ABANDON"], var.deletion_policy)
    error_message = "Must be PREVENT, DELETE or ABANDON."
  }
}

variable "create_budget" {
  type    = bool
  default = true
}

variable "monthly_budget_usd" {
  type    = number
  default = 100
}

variable "alert_email" {
  description = "Email for budget alerts. Empty disables the notification channel."
  type        = string
  default     = ""
}

variable "apis" {
  type = list(string)
  default = [
    "compute.googleapis.com",
    "container.googleapis.com",
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
  ]
}
