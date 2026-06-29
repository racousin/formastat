# formaStat — Terraform

Provisions the baseline GCP infrastructure for **formaStat** (project ID `formastat`):

- Enables required APIs (Run, Artifact Registry, Cloud Build, IAM, Storage)
- Artifact Registry Docker repository (`formastat-docker`)
- Application GCS bucket
- A least-privilege Cloud Run runtime service account (`formastat-run`)
- A Cloud Run service (the app), optionally public

State is stored **locally** (`terraform.tfstate` in this directory — gitignored).

---

## ⚠️ Account note

The `formastat` project is owned by **`admin@scai-sorbonne.fr`** and lives in the
`scai-sorbonne.fr` organization, which **enforces Domain Restricted Sharing**
(`constraints/iam.allowedPolicyMemberDomains`). Only `scai-sorbonne.fr`
principals can be added to IAM — so `raphaelcousin90@gmail.com` **cannot** be
granted access, and SA impersonation from a gmail account is blocked too.
Terraform must authenticate with an in-domain identity (Option A) or an
in-project service account (Option C).

---

## Console / CLI bootstrap (one time)

You can do each step in the Cloud Console or with `gcloud`. CLI shown for brevity.

### 1. Confirm the project + billing

In the Console, switch to the account that owns **formaStat**
(top-right avatar → choose the right account), then select the **formaStat**
project from the project picker.

- **Billing must be linked** (Cloud Run + Artifact Registry require it):
  Console → *Billing* → confirm `formastat` is linked to an active billing account.
  CLI: `gcloud billing projects describe formastat`

### 2. Authentication for Terraform — choose ONE

**Option A — ADC as admin@scai-sorbonne.fr (recommended, no key files):**
`admin@scai-sorbonne.fr` is already Owner and is in the allowed domain, so
nothing needs granting. Point Terraform's credentials at that account:
```bash
# A browser opens — pick admin@scai-sorbonne.fr:
gcloud auth application-default login
gcloud auth application-default set-quota-project formastat
# Leave credentials_file empty in terraform.tfvars (the default).
```
This only changes the Application Default Credentials Terraform reads — your
everyday `gcloud` login (gmail / RL project) is untouched.

**Option B — grant raphaelcousin90@gmail.com: NOT POSSIBLE.**
Blocked by the org's Domain Restricted Sharing policy (gmail.com is not an
allowed domain). Use Option A or C instead.

**Option C — service-account key (works regardless of local gcloud login):**
Whoever owns formaStat runs:
```bash
gcloud iam service-accounts create terraform \
  --display-name="Terraform" --project=formastat
gcloud projects add-iam-policy-binding formastat \
  --member="serviceAccount:terraform@formastat.iam.gserviceaccount.com" \
  --role="roles/owner"
gcloud iam service-accounts keys create ~/formastat-terraform-key.json \
  --iam-account=terraform@formastat.iam.gserviceaccount.com
```
Then set `credentials_file = "/Users/raphaelcousin/formastat-terraform-key.json"`
in `terraform.tfvars`. (Note: some orgs block SA-key creation — then use A or B.)

### 3. Enable the bootstrap APIs

Terraform enables the app APIs itself, but the Service Usage + Resource Manager
APIs must already be on so it can do so:
```bash
gcloud services enable \
  serviceusage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=formastat
```

---

## Apply

```bash
cd /Users/raphaelcousin/formastat/terraform
cp terraform.tfvars.example terraform.tfvars   # optional: edit overrides
terraform init
terraform plan
terraform apply
```

The Cloud Run service starts on Google's `hello` sample image. Terraform ignores
image drift afterward, so real deploys won't be reverted.

## Deploy the real app (after the app exists)

```bash
gcloud auth configure-docker europe-west1-docker.pkg.dev
# Build for linux/amd64 (Cloud Run) if building on Apple Silicon:
docker build --platform linux/amd64 \
  -t europe-west1-docker.pkg.dev/formastat/formastat-docker/app:latest .
docker push europe-west1-docker.pkg.dev/formastat/formastat-docker/app:latest

gcloud run deploy formastat \
  --image=europe-west1-docker.pkg.dev/formastat/formastat-docker/app:latest \
  --region=europe-west1 --project=formastat
```

For Streamlit, make the container bind Cloud Run's port:
`streamlit run app.py --server.port=8080 --server.address=0.0.0.0`

## Outputs

`terraform output` gives the Cloud Run URL, Docker repo base URL, bucket name,
and the runtime SA email.
