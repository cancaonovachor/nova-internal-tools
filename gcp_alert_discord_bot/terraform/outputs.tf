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
