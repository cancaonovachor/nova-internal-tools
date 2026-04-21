# 各ツール用 GitHub Actions deployer SA + WIF 信頼付与。
# IAM role (artifactregistry.writer / run.developer / iam.serviceAccountUser) は
# tool 側でリソース単位で付与する (この module ではロール付与しない)。

resource "google_service_account" "deployer" {
  project      = var.project
  account_id   = var.sa_id
  display_name = var.display_name
}

# WIF 経由で GitHub Actions (指定 repo の main ブランチ workflow) が当該 SA を
# impersonate できるようにする。
# pool provider は PR イベントも許可する条件になっているので、deployer 側は
# `subject` (GitHub OIDC の google.subject) で `ref:refs/heads/main` に固定して
# PR ブランチからの借用を弾く。これが主防衛線。
# google.subject の値は GitHub OIDC の `sub` claim:
#   push to branch -> "repo:<owner>/<repo>:ref:refs/heads/<branch>"
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${var.wif_pool_name}/subject/repo:${var.github_repo}:ref:refs/heads/main"
}
