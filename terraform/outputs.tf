# terraform/outputs.tf

output "docker_repository_url" {
  description = "Base URL to tag/push images for this project"
  value       = "${google_artifact_registry_repository.docker_repository.location}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.docker_repository.repository_id}"
}

output "app_bucket" {
  description = "Application GCS bucket name"
  value       = google_storage_bucket.app_bucket.name
}

output "run_service_account" {
  description = "Cloud Run runtime service account email"
  value       = google_service_account.run_sa.email
}

output "cloud_run_url" {
  description = "Public URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.app.uri
}
