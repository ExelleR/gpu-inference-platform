resource "google_project" "this" {
  name            = var.project_name
  project_id      = var.project_id
  billing_account = var.billing_account
  deletion_policy = var.deletion_policy

  labels = {
    purpose    = "gpu-inference-platform"
    managed-by = "terraform"
  }
}

resource "google_project_service" "apis" {
  for_each = toset(var.apis)

  project            = google_project.this.project_id
  service            = each.value
  disable_on_destroy = false
}

# Freshly enabled APIs take a moment to become usable in a new project.
resource "time_sleep" "api_propagation" {
  depends_on      = [google_project_service.apis]
  create_duration = "60s"
}
