provider "google" {
  region = var.region
}

# The Cloud Billing Budgets API needs a quota project. Use the project this
# stage creates (billingbudgets API is enabled in main.tf before use).
provider "google" {
  alias                 = "budget"
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
}
