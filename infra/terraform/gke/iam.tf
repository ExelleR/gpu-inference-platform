resource "google_service_account" "nodes" {
  account_id   = "${var.cluster_name}-nodes"
  display_name = "GKE node service account"
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/artifactregistry.reader",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# Managed Prometheus query frontend: reads Cloud Monitoring through Workload Identity.
resource "google_service_account" "gmp_frontend" {
  count = var.observability_enabled ? 1 : 0

  account_id   = "gmp-frontend"
  display_name = "Managed Prometheus query frontend"
}

resource "google_project_iam_member" "gmp_frontend_viewer" {
  count = var.observability_enabled ? 1 : 0

  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gmp_frontend[0].email}"
}

resource "google_service_account_iam_member" "gmp_frontend_workload_identity" {
  count = var.observability_enabled ? 1 : 0

  service_account_id = google_service_account.gmp_frontend[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[observability/gmp-frontend]"
}
