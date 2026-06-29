# terraform/iam.tf

# Runtime identity for the Cloud Run service (least privilege; not the
# default compute SA).
resource "google_service_account" "run_sa" {
  account_id   = "formastat-run"
  display_name = "formaStat Cloud Run runtime SA"
}

# Pull images from Artifact Registry.
resource "google_project_iam_member" "run_sa_artifact_reader" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.run_sa.email}"
}
