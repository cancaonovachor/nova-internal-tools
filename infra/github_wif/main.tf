locals {
  project_id = "starlit-road-203901"

  # GitHub repository (owner/name). ここを変えたら pool provider の
  # attribute_condition も追随させること。
  github_repo = "cancaonovachor/nova-internal-tools"

  # deploy を許可する branch。WIF トークン発行時に ref をここで絞る。
  allowed_branches = ["main"]

  # Terraform state backend bucket (plan で state を読むのに planner SA に権限が要る)
  tfstate_bucket = "starlit-road-203901-tfstate"
}

# -------------------- WIF pool --------------------
resource "google_iam_workload_identity_pool" "github_actions" {
  project                   = local.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "WIF pool for GitHub Actions (deploy + PR terraform plan) from ${local.github_repo}"
}

# -------------------- WIF provider (OIDC) --------------------
# GitHub Actions が発行する OIDC JWT を受けて Google token に交換する provider。
# attribute_condition で repo を制限した上で、
#   - main への push (deploy)
#   - pull_request イベント (terraform plan コメント)
# の 2 系統を許可する。どちらに向かうかは各 SA の IAM binding 側で絞る:
#   - deployer SA: subject で `ref:refs/heads/main` に固定 (PR からは借りられない)
#   - planner SA : attribute.repository で広く許可 (read-only 権限のみ付与)
resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = local.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.actor"      = "assertion.actor"
    "attribute.event_name" = "assertion.event_name"
  }

  attribute_condition = <<-EOT
    assertion.repository == "${local.github_repo}" && (
      assertion.ref in [${join(", ", [for b in local.allowed_branches : "\"refs/heads/${b}\""])}] ||
      assertion.event_name == "pull_request"
    )
  EOT

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# -------------------- Planner SA (read-only, shared) --------------------
# PR で `terraform plan` を走らせるための共通 SA。
# write 権限は一切与えず、すべての infra stack が共用する。
# write が必要な deploy は各ツールごとの deployer SA (main ref 専用) を使う。
resource "google_service_account" "planner" {
  project      = local.project_id
  account_id   = "tf-planner"
  display_name = "GitHub Actions Terraform planner (read-only, PR)"
}

# PR ワークフロー (event_name=pull_request) + 同 repo なら impersonate できる。
# Pool provider 側で event_name / ref の条件が効くので、principalSet は repo 単位で十分。
resource "google_service_account_iam_member" "planner_wif_binding" {
  service_account_id = google_service_account.planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/${local.github_repo}"
}

# Terraform plan の refresh で広く read する。
# viewer はほとんどのリソースを読めるが、IAM policy の read には securityReviewer が要る。
resource "google_project_iam_member" "planner_viewer" {
  project = local.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.planner.email}"
}

resource "google_project_iam_member" "planner_iam_reviewer" {
  project = local.project_id
  role    = "roles/iam.securityReviewer"
  member  = "serviceAccount:${google_service_account.planner.email}"
}

# tfstate bucket を読む権限 (各 stack の state を init/plan で参照する)。
# bucket 自体は Terraform 管理外 (手動作成) なので、IAM member のみ管理する。
resource "google_storage_bucket_iam_member" "planner_state_reader" {
  bucket = local.tfstate_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.planner.email}"
}
