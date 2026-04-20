locals {
  # 固定値はここに集約 (tfvars / variable は使わない)
  project_id     = "starlit-road-203901"
  project_number = "938216897098"
  region         = "asia-northeast1"
  artifact_repo  = "gcp-alert-discord-bot"
  image_name     = "gcp-alert-discord-bot"
  topic_name     = "gcp-alerts"

  image_url = "${local.region}-docker.pkg.dev/${local.project_id}/${local.artifact_repo}/${local.image_name}:${var.image_tag}"

  required_apis = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "iam.googleapis.com",
  ])
}

# -------------------- APIs --------------------
resource "google_project_service" "apis" {
  for_each = local.required_apis

  project            = local.project_id
  service            = each.value
  disable_on_destroy = false
}

# -------------------- Artifact Registry --------------------
resource "google_artifact_registry_repository" "repo" {
  project       = local.project_id
  location      = local.region
  repository_id = local.artifact_repo
  format        = "DOCKER"
  description   = "gcp-alert-discord-bot container images"

  depends_on = [google_project_service.apis]
}

# -------------------- Secret: Discord webhook --------------------
# secret リソースのみ Terraform で管理する。version (実際の webhook URL) は
# `gcloud secrets versions add gcp-alert-bot-discord-webhook --data-file=-` で
# アウトオブバンドに投入する。
resource "google_secret_manager_secret" "discord_webhook" {
  project   = local.project_id
  secret_id = "gcp-alert-bot-discord-webhook"
  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

# -------------------- Pub/Sub topic --------------------
resource "google_pubsub_topic" "alerts" {
  project = local.project_id
  name    = local.topic_name

  depends_on = [google_project_service.apis]
}

# NOTE: Budget / Monitoring notification channel の publish 権限は GCP 側が自動付与する。
# - Budget: 予算設定で topic を指定すると billing-budgets@system に publisher 権限が付く
# - Monitoring: notification channel 作成で gcp-sa-monitoring-notification に付く
# これらを Terraform で管理しようとすると、対象 SA がまだプロジェクトに現れていない
# 段階で 400 エラーになるため、Terraform 管理対象から外している。

# -------------------- Service Accounts --------------------
# Cloud Run 本体が使う SA
resource "google_service_account" "worker" {
  project      = local.project_id
  account_id   = "gcp-alert-bot-worker"
  display_name = "gcp-alert-discord-bot runtime"
}

# Pub/Sub push が Cloud Run を呼ぶときの OIDC 用 SA
resource "google_service_account" "invoker" {
  project      = local.project_id
  account_id   = "gcp-alert-bot-invoker"
  display_name = "gcp-alert-discord-bot Pub/Sub invoker"
}

# Secret 読み取り権限
resource "google_secret_manager_secret_iam_member" "worker_discord_reader" {
  project   = local.project_id
  secret_id = google_secret_manager_secret.discord_webhook.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

# -------------------- Cloud Run --------------------
resource "google_cloud_run_v2_service" "service" {
  project  = local.project_id
  location = local.region
  name     = "gcp-alert-discord-bot"

  deletion_protection = false

  template {
    service_account = google_service_account.worker.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.cloud_run_max_instances
    }

    max_instance_request_concurrency = 20
    timeout                          = "60s"

    containers {
      image = local.image_url
      args  = ["app.main:app", "--host", "0.0.0.0", "--port", "8080"]

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # DISCORD_WEBHOOK_URL は Secret Manager の :latest を参照。
      # Secret に version が無い初回デプロイだと Cloud Run が起動に失敗するため、
      # 初回は `gcloud secrets versions add` を先に実行すること。
      env {
        name = "DISCORD_WEBHOOK_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.discord_webhook.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.worker_discord_reader,
  ]
}

# invoker SA のみ Cloud Run を呼べる (Pub/Sub push の OIDC がこの SA)
resource "google_cloud_run_v2_service_iam_member" "invoker_binding" {
  project  = google_cloud_run_v2_service.service.project
  location = google_cloud_run_v2_service.service.location
  name     = google_cloud_run_v2_service.service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.invoker.email}"
}

# -------------------- Pub/Sub subscription (push) --------------------
# Pub/Sub が OIDC token を作れるよう、project の pubsub service agent に
# serviceAccountTokenCreator を与える必要がある。
# ref: https://cloud.google.com/pubsub/docs/push#authentication
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.invoker.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${local.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription" "push_to_run" {
  project = local.project_id
  name    = "${local.topic_name}-to-run"
  topic   = google_pubsub_topic.alerts.name

  ack_deadline_seconds = 30

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.service.uri}/pubsub/push"

    oidc_token {
      service_account_email = google_service_account.invoker.email
      audience              = google_cloud_run_v2_service.service.uri
    }
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = ""
  }

  depends_on = [
    google_cloud_run_v2_service_iam_member.invoker_binding,
    google_service_account_iam_member.pubsub_token_creator,
  ]
}

# -------------------- Cloud Monitoring: Pub/Sub 通知チャネル --------------------
resource "google_monitoring_notification_channel" "pubsub" {
  count        = var.create_monitoring_channel ? 1 : 0
  project      = local.project_id
  display_name = "gcp-alerts pubsub"
  type         = "pubsub"

  labels = {
    topic = google_pubsub_topic.alerts.id
  }
}
