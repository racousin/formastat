# terraform/variables.tf

variable "gcp_project_id" {
  description = "The GCP project ID"
  type        = string
  default     = "formastat"
}

variable "gcp_region" {
  description = "The GCP region"
  type        = string
  default     = "europe-west1"
}

variable "gcp_zone" {
  description = "The GCP zone"
  type        = string
  default     = "europe-west1-b"
}

variable "credentials_file" {
  description = "Path to a service-account key JSON. Leave empty to use Application Default Credentials (recommended)."
  type        = string
  default     = ""
}

# ── Artifact Registry ──

variable "artifact_repo_id" {
  description = "Artifact Registry Docker repository ID"
  type        = string
  default     = "formastat-docker"
}

# ── Storage ──

variable "bucket_name" {
  description = "Globally-unique name of the application GCS bucket"
  type        = string
  default     = "formastat-app-bucket-eu"
}

variable "bucket_location" {
  description = "The location of the storage bucket"
  type        = string
  default     = "EU"
}

# ── Cloud Run ──

variable "service_name" {
  description = "Cloud Run service name (the app)"
  type        = string
  default     = "formastat"
}

variable "container_image" {
  description = "Container image for the Cloud Run service. Defaults to Google's hello sample until the real image is pushed; deploys are then driven by gcloud/CI and Terraform ignores image drift."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "container_port" {
  description = "Port the container listens on (the app must respect $PORT / bind 0.0.0.0). Streamlit: --server.port=8080 --server.address=0.0.0.0"
  type        = number
  default     = 8080
}

variable "allow_unauthenticated" {
  description = "Grant allUsers (anonymous public) invoke access. BLOCKED by the scai-sorbonne.fr Domain Restricted Sharing org policy — keep false unless an org-admin exception for allUsers exists on this project."
  type        = bool
  default     = false
}

variable "invoker_members" {
  description = "Principals granted run.invoker (authenticated access). In-domain values are permitted by the org policy, e.g. [\"domain:scai-sorbonne.fr\"] or [\"user:someone@scai-sorbonne.fr\"]."
  type        = list(string)
  default     = []
}
