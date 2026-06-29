# terraform/cloud_run.tf

# The formaStat application, served by Cloud Run.
resource "google_cloud_run_v2_service" "app" {
  name                = var.service_name
  location            = var.gcp_region
  deletion_protection = false

  template {
    service_account = google_service_account.run_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.container_image

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.app_bucket.name
      }
    }
  }

  # Real image rollouts are driven by `gcloud run deploy` / CI. Ignore image
  # drift so Terraform doesn't revert deployed versions back to the default.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.run_sa_artifact_reader,
  ]
}

# Anonymous public access (allUsers). Only applies if the org's Domain
# Restricted Sharing policy permits allUsers — it does NOT by default on
# scai-sorbonne.fr, so this stays disabled unless an exception is granted.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count = var.allow_unauthenticated ? 1 : 0

  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Authenticated invokers — in-domain principals allowed by the org policy
# (e.g. domain:scai-sorbonne.fr for any org member, or specific users).
resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)

  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = each.value
}
