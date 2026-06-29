# terraform/apis.tf
# Enable the Google APIs this stack needs. serviceusage + cloudresourcemanager
# must already be enabled (see terraform/README.md bootstrap) for these to apply.

locals {
  gcp_services = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.gcp_services)

  project = var.gcp_project_id
  service = each.value

  # Keep APIs enabled if the stack is destroyed; avoids breaking other resources.
  disable_on_destroy = false
}
