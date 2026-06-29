# terraform/storage.tf

# Application data bucket.
resource "google_storage_bucket" "app_bucket" {
  name                        = var.bucket_name
  location                    = var.bucket_location
  uniform_bucket_level_access = true
  force_destroy               = false

  # Versioning off by default; flip to true if you need object history.
  versioning {
    enabled = false
  }

  # No blanket delete lifecycle by default (avoid surprise data loss).
  # Uncomment to expire objects under a prefix, e.g. temp uploads:
  # lifecycle_rule {
  #   condition {
  #     age            = 30
  #     matches_prefix = ["tmp/"]
  #   }
  #   action {
  #     type = "Delete"
  #   }
  # }

  depends_on = [google_project_service.apis]
}

# The Cloud Run runtime SA can read/write objects in the app bucket.
resource "google_storage_bucket_iam_member" "run_sa_object_admin" {
  bucket = google_storage_bucket.app_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.run_sa.email}"
}
