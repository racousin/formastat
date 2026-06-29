# terraform/artifact_registry.tf

# Docker repository to host the formaStat application image.
resource "google_artifact_registry_repository" "docker_repository" {
  location      = var.gcp_region
  repository_id = var.artifact_repo_id
  description   = "formaStat Docker repository"
  format        = "DOCKER"

  labels = {
    environment = "prod"
  }

  depends_on = [google_project_service.apis]
}
