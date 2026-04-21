output "pool_name" {
  value       = google_iam_workload_identity_pool.github_actions.name
  description = "Full resource name of the WIF pool. 各ツール deployer SA の principalSet 指定に使う"
}

output "provider_name" {
  value       = google_iam_workload_identity_pool_provider.github.name
  description = "Full resource name of the WIF provider. GitHub Actions `google-github-actions/auth@v2` の workload_identity_provider 入力に設定する (GitHub secret `WIF_PROVIDER`)"
}

output "planner_sa_email" {
  value       = google_service_account.planner.email
  description = "Terraform planner SA email. PR の terraform plan ワークフローで WIF 経由 impersonate する (GitHub secret `WIF_SERVICE_ACCOUNT_PLANNER`)"
}
