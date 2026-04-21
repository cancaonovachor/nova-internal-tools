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
module "artifact_registry" {
  source = "../modules/artifact_registry"

  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo
  description   = "notion-discord-bot container images"

  depends_on = [google_project_service.apis]
}

# 旧構成 (terraform/ 配下のルートモジュール直書き) からの state 移行用。
# 既存 state の `google_artifact_registry_repository.repo` をモジュール配下に
# 再マップし、destroy+create を避ける。
moved {
  from = google_artifact_registry_repository.repo
  to   = module.artifact_registry.google_artifact_registry_repository.repo
}

# -------------------- Secret Manager --------------------
# secret リソースのみ Terraform で管理する。version (実際の値) は
# `gcloud secrets versions add <secret-id> --data-file=-` でアウトオブバンドに投入する。
# 旧構成ではここに `google_secret_manager_secret_version.*_v1` リソースがあり
# var から secret_data を流し込んでいたが、tfvars に秘匿値が残る構成を避けるため撤去。
# 移行時は `terraform state rm` で旧 version リソースを state から除去する (下記 README 参照)。
resource "google_secret_manager_secret" "verification_token" {
  project   = var.project_id
  secret_id = "notion-verification-token"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "api_key" {
  project   = var.project_id
  secret_id = "notion-api-key"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "discord_webhook" {
  project   = var.project_id
  secret_id = "notion-bot-discord-webhook"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "discord_deletion_webhook" {
  project   = var.project_id
  secret_id = "notion-bot-discord-deletion-webhook"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
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
        for_each = var.enable_discord_webhook ? [1] : []
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
        for_each = var.enable_discord_deletion_webhook ? [1] : []
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
    google_secret_manager_secret_iam_member.worker_api_key_reader,
    google_secret_manager_secret_iam_member.worker_discord_reader,
    google_secret_manager_secret_iam_member.worker_discord_deletion_reader,
  ]

  # image は GitHub Actions deploy workflow が更新する (`gcloud run services update --image=...:<sha>`)。
  # Terraform は初回作成時にのみ image を設定し、その後の差分は無視する。
  # client / client_version は gcloud / GCP が書き込むメタデータで、Terraform は管理しない。
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
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
    google_secret_manager_secret_iam_member.ingress_verification_reader,
    google_cloud_run_v2_service.worker,
    google_cloud_tasks_queue.queue,
  ]

  # image は GitHub Actions deploy workflow が更新する (`gcloud run services update --image=...:<sha>`)。
  # Terraform は初回作成時にのみ image を設定し、その後の差分は無視する。
  # client / client_version は gcloud / GCP が書き込むメタデータで、Terraform は管理しない。
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

# Notion からの webhook 受信用に ingress は公開
resource "google_cloud_run_v2_service_iam_member" "ingress_public" {
  project  = google_cloud_run_v2_service.ingress.project
  location = google_cloud_run_v2_service.ingress.location
  name     = google_cloud_run_v2_service.ingress.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# -------------------- GitHub Actions Deployer --------------------
# WIF 経由で GitHub Actions から image push + Cloud Run revision 更新を行う SA。
# pool / provider 自体は infra/github_wif/ で作成しておくこと (先に apply 必須)。
data "google_iam_workload_identity_pool" "github_actions" {
  workload_identity_pool_id = "github-actions"
  project                   = var.project_id
}

module "github_deployer" {
  source = "../modules/github_deployer_sa"

  project       = var.project_id
  sa_id         = "notion-bot-deployer"
  display_name  = "notion-discord-bot GitHub Actions deployer"
  wif_pool_name = data.google_iam_workload_identity_pool.github_actions.name
  github_repo   = "cancaonovachor/nova-internal-tools"
}

# deployer は当該ツールの AR repo に push できる
resource "google_artifact_registry_repository_iam_member" "deployer_ar_writer" {
  project    = var.project_id
  location   = var.region
  repository = module.artifact_registry.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${module.github_deployer.email}"
}

# deployer は当該サービスのみ update できる (ingress)
resource "google_cloud_run_v2_service_iam_member" "deployer_ingress_developer" {
  project  = google_cloud_run_v2_service.ingress.project
  location = google_cloud_run_v2_service.ingress.location
  name     = google_cloud_run_v2_service.ingress.name
  role     = "roles/run.developer"
  member   = "serviceAccount:${module.github_deployer.email}"
}

# deployer は当該サービスのみ update できる (worker)
resource "google_cloud_run_v2_service_iam_member" "deployer_worker_developer" {
  project  = google_cloud_run_v2_service.worker.project
  location = google_cloud_run_v2_service.worker.location
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.developer"
  member   = "serviceAccount:${module.github_deployer.email}"
}

# Cloud Run デプロイ時に runtime SA (ingress/worker) を設定するため、
# deployer に iam.serviceAccountUser を与える (他ツールの SA には出さない)。
resource "google_service_account_iam_member" "deployer_acts_as_ingress_runtime" {
  service_account_id = google_service_account.ingress.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${module.github_deployer.email}"
}

resource "google_service_account_iam_member" "deployer_acts_as_worker_runtime" {
  service_account_id = google_service_account.worker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${module.github_deployer.email}"
}
