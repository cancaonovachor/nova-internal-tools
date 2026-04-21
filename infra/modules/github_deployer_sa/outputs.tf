output "email" {
  value       = google_service_account.deployer.email
  description = "Deployer SA email. GitHub secret の WIF_SERVICE_ACCOUNT_* に設定"
}

output "name" {
  value       = google_service_account.deployer.name
  description = "Deployer SA full resource name (projects/.../serviceAccounts/<email>)"
}

output "unique_id" {
  value       = google_service_account.deployer.unique_id
  description = "Deployer SA unique ID"
}
