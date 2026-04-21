output "id" {
  value       = google_artifact_registry_repository.repo.id
  description = "Full resource ID of the repository"
}

output "name" {
  value       = google_artifact_registry_repository.repo.name
  description = "Repository name"
}

output "repository_id" {
  value       = google_artifact_registry_repository.repo.repository_id
  description = "Repository ID (short name)"
}
