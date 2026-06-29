# formaStat — Makefile

# ── GCP config switching ──────────────────────────────────────────────
# Switch the active gcloud CLI configuration between projects.
# (Terraform auth is separate: it uses ADC = admin@scai-sorbonne.fr —
#  this only affects gcloud/docker commands.)

# Switch gcloud CLI to formaStat (admin@scai-sorbonne.fr)
gcp-formastat:
	@echo "Activating gcloud config: formastat (admin@scai-sorbonne.fr)..."
	@gcloud config configurations activate formastat

# Switch gcloud CLI back to the RL project (default config / gmail)
gcp-rl:
	@echo "Activating gcloud config: default (rlarena / gmail)..."
	@gcloud config configurations activate default

# Show all gcloud configurations and which is active
gcp-config:
	@gcloud config configurations list

# ── Terraform ─────────────────────────────────────────────────────────

tf-init:
	cd terraform && terraform init

tf-plan:
	cd terraform && terraform plan

tf-apply:
	cd terraform && terraform apply
