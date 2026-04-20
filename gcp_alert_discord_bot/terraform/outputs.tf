output "topic_id" {
  value       = google_pubsub_topic.alerts.id
  description = "Budget / Monitoring に publish 先として指定する Pub/Sub topic"
}

output "topic_name" {
  value = google_pubsub_topic.alerts.name
}

output "service_url" {
  value = google_cloud_run_v2_service.service.uri
}

output "image_url" {
  value = local.image_url
}

output "artifact_registry_repo" {
  value = google_artifact_registry_repository.repo.id
}

output "notification_channel_id" {
  value       = try(google_monitoring_notification_channel.pubsub[0].id, null)
  description = "Alert policy に紐付ける notification channel の resource id"
}

output "cloud_run_alert_policy_id" {
  value       = try(google_monitoring_alert_policy.cloud_run_error[0].id, null)
  description = "Cloud Run services の ERROR log を検出する alert policy id"
}

output "cloud_run_job_alert_policy_id" {
  value       = try(google_monitoring_alert_policy.cloud_run_job_error[0].id, null)
  description = "Cloud Run Jobs の ERROR log を検出する alert policy id"
}

output "email_notification_channel_id" {
  value       = try(google_monitoring_notification_channel.email[0].id, null)
  description = "self-alert 用の email 通知チャネル id"
}

output "self_alert_policy_id" {
  value       = try(google_monitoring_alert_policy.self_error[0].id, null)
  description = "gcp-alert-discord-bot 自身の ERROR を検出する alert policy id"
}
