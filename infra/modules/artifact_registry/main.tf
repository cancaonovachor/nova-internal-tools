resource "google_artifact_registry_repository" "repo" {
  project       = var.project
  location      = var.location
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = var.description
}
