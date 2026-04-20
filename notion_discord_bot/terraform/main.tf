locals {
  image_url = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}/${var.image_name}:${var.image_tag}"

  required_apis = toset([
    "run.googleapis.com",
    "cloudtasks.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
  ])
}

# -------------------- APIs --------------------
resource "google_project_service" "apis" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -------------------- Artifact Registry --------------------
resource "google_artifact_registry_repository" "repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "notion-discord-bot container images"

  depends_on = [google_project_service.apis]
}

# -------------------- Secret Manager --------------------
resource "google_secret_manager_secret" "verification_token" {
  project   = var.project_id
  secret_id = "notion-verification-token"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "verification_token_v1" {
  secret      = google_secret_manager_secret.verification_token.id
  secret_data = var.notion_verification_token
}

resource "google_secret_manager_secret" "api_key" {
  project   = var.project_id
  secret_id = "notion-api-key"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "api_key_v1" {
  secret      = google_secret_manager_secret.api_key.id
  secret_data = var.notion_api_key
}

resource "google_secret_manager_secret" "discord_webhook" {
  project   = var.project_id
  secret_id = "notion-bot-discord-webhook"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# 空文字のときは version を作らない（Cloud Run 側も env を条件で付ける）
resource "google_secret_manager_secret_version" "discord_webhook_v1" {
  count       = var.discord_webhook_url == "" ? 0 : 1
  secret      = google_secret_manager_secret.discord_webhook.id
  secret_data = var.discord_webhook_url
}

resource "google_secret_manager_secret" "discord_deletion_webhook" {
  project   = var.project_id
  secret_id = "notion-bot-discord-deletion-webhook"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "discord_deletion_webhook_v1" {
  count       = var.discord_deletion_webhook_url == "" ? 0 : 1
  secret      = google_secret_manager_secret.discord_deletion_webhook.id
  secret_data = var.discord_deletion_webhook_url
}

# -------------------- Service Accounts --------------------
resource "google_service_account" "ingress" {
  project      = var.project_id
  account_id   = "notion-bot-ingress"
  display_name = "notion-discord-bot ingress runtime"
}

resource "google_service_account" "worker" {
  project      = var.project_id
  account_id   = "notion-bot-worker"
  display_name = "notion-discord-bot worker runtime"
}

# ingress SA が OIDC トークン発行時に自分自身を impersonate できるようにする
resource "google_service_account_iam_member" "ingress_self_user" {
  service_account_id = google_service_account.ingress.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.ingress.email}"
}

# -------------------- Cloud Tasks Queue --------------------
resource "google_cloud_tasks_queue" "queue" {
  project  = var.project_id
  location = var.region
  name     = var.queue_name

  rate_limits {
    max_dispatches_per_second = 10
    max_concurrent_dispatches = 5
  }

  retry_config {
    max_attempts  = 5
    min_backoff   = "5s"
    max_backoff   = "300s"
    max_doublings = 4
  }

  depends_on = [google_project_service.apis]
}

# ingress がキューにタスクを投入する権限
resource "google_project_iam_member" "ingress_cloudtasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.ingress.email}"
}

# -------------------- Secret Access --------------------
resource "google_secret_manager_secret_iam_member" "ingress_verification_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.verification_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingress.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_api_key_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_discord_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.discord_webhook.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_discord_deletion_reader" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.discord_deletion_webhook.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

# -------------------- Cloud Run: worker --------------------
resource "google_cloud_run_v2_service" "worker" {
  project  = var.project_id
  location = var.region
  name     = "notion-discord-bot-worker"

  deletion_protection = false

  template {
    service_account = google_service_account.worker.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.cloud_run_worker_max_instances
    }

    max_instance_request_concurrency = 10
    timeout                          = "60s"

    containers {
      image = local.image_url
      args  = ["worker.main:app", "--host", "0.0.0.0", "--port", "8080"]

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name = "NOTION_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.api_key.secret_id
            version = "latest"
          }
        }
      }

      dynamic "env" {
        for_each = var.discord_webhook_url == "" ? [] : [1]
        content {
          name = "DISCORD_WEBHOOK_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.discord_webhook.secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = var.discord_deletion_webhook_url == "" ? [] : [1]
        content {
          name = "DISCORD_DELETION_WEBHOOK_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.discord_deletion_webhook.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.api_key_v1,
    google_secret_manager_secret_iam_member.worker_api_key_reader,
    google_secret_manager_secret_iam_member.worker_discord_reader,
    google_secret_manager_secret_iam_member.worker_discord_deletion_reader,
  ]
}

# ingress SA のみ worker を invoke できる
resource "google_cloud_run_v2_service_iam_member" "ingress_invokes_worker" {
  project  = google_cloud_run_v2_service.worker.project
  location = google_cloud_run_v2_service.worker.location
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.ingress.email}"
}

# -------------------- Cloud Run: ingress --------------------
resource "google_cloud_run_v2_service" "ingress" {
  project  = var.project_id
  location = var.region
  name     = "notion-discord-bot-ingress"

  deletion_protection = false

  template {
    service_account = google_service_account.ingress.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.cloud_run_ingress_max_instances
    }

    max_instance_request_concurrency = 80
    timeout                          = "10s"

    containers {
      image = local.image_url
      args  = ["ingress.main:app", "--host", "0.0.0.0", "--port", "8080"]

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name = "NOTION_VERIFICATION_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.verification_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "NOTION_ALLOWED_EVENTS"
        value = join(",", var.notion_allowed_events)
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "CLOUD_TASKS_LOCATION"
        value = var.region
      }

      env {
        name  = "CLOUD_TASKS_QUEUE"
        value = google_cloud_tasks_queue.queue.name
      }

      env {
        name  = "WORKER_URL"
        value = "${google_cloud_run_v2_service.worker.uri}/tasks/notion-event"
      }

      env {
        name  = "WORKER_INVOKER_SA"
        value = google_service_account.ingress.email
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.verification_token_v1,
    google_secret_manager_secret_iam_member.ingress_verification_reader,
    google_cloud_run_v2_service.worker,
    google_cloud_tasks_queue.queue,
  ]
}

# Notion からの webhook 受信用に ingress は公開
resource "google_cloud_run_v2_service_iam_member" "ingress_public" {
  project  = google_cloud_run_v2_service.ingress.project
  location = google_cloud_run_v2_service.ingress.location
  name     = google_cloud_run_v2_service.ingress.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
