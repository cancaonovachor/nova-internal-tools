output "ingress_url" {
  value       = google_cloud_run_v2_service.ingress.uri
  description = "ingress Cloud Run サービスのベース URL"
}

output "ingress_webhook_url" {
  value       = "${google_cloud_run_v2_service.ingress.uri}/webhook/notion"
  description = "Notion subscription に登録する webhook URL"
}

output "worker_url" {
  value       = google_cloud_run_v2_service.worker.uri
  description = "worker Cloud Run サービスのベース URL"
}

output "image_url" {
  value       = local.image_url
  description = "ビルド/プッシュ先の Artifact Registry イメージ URL"
}

output "artifact_registry_repo" {
  value = module.artifact_registry.id
}

output "queue_name" {
  value = google_cloud_tasks_queue.queue.name
}

output "deployer_service_account_email" {
  value       = module.github_deployer.email
  description = "GitHub Actions deploy workflow に渡す SA email (GitHub secret WIF_SERVICE_ACCOUNT_NOTION)"
}
