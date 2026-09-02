output "project_id" {
  value = google_project.this.project_id
}

output "project_number" {
  value = google_project.this.number
}

output "state_bucket" {
  value = google_storage_bucket.tfstate.name
}

output "region" {
  value = var.region
}
