locals {
  project_id = "starlit-road-203901"

  # GitHub repository (owner/name). ここを変えたら pool provider の
  # attribute_condition も追随させること。
  github_repo = "cancaonovachor/nova-internal-tools"

  # deploy を許可する branch。WIF トークン発行時に ref をここで絞る。
  allowed_branches = ["main"]
}

# -------------------- WIF pool --------------------
resource "google_iam_workload_identity_pool" "github_actions" {
  project                   = local.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "WIF pool for GitHub Actions deploys from ${local.github_repo}"
}

# -------------------- WIF provider (OIDC) --------------------
# GitHub Actions が発行する OIDC JWT を受けて Google token に交換する provider。
# attribute_condition で repo と branch を制限し、fork や feature branch からの
# 借用を弾く。
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
  }

  attribute_condition = <<-EOT
    assertion.repository == "${local.github_repo}" &&
    assertion.ref in [${join(", ", [for b in local.allowed_branches : "\"refs/heads/${b}\""])}]
  EOT

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}
