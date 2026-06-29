# terraform/provider.tf

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.9"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
  zone    = var.gcp_zone

  # Auth: by default Terraform uses Application Default Credentials
  # (`gcloud auth application-default login`). To use a downloaded service
  # account key instead, set var.credentials_file to its path.
  credentials = var.credentials_file != "" ? file(var.credentials_file) : null
}
