# NOTE: tfvars ファイルは作らない方針 (root CLAUDE.md 参照)。
# - 機密値 (Notion token / API key / Discord webhook URL) は Terraform で secret
#   resource のみ作成し、`gcloud secrets versions add` でアウトオブバンドに投入する
# - 固定値は locals か variable default に寄せる

variable "project_id" {
  type        = string
  default     = "starlit-road-203901"
  description = "GCP project ID"
}

variable "region" {
  type        = string
  default     = "asia-northeast1"
  description = "Cloud Run / Cloud Tasks / Artifact Registry のリージョン"
}

variable "artifact_repo" {
  type        = string
  default     = "notion-discord-bot"
  description = "Artifact Registry リポジトリ名"
}

variable "image_name" {
  type        = string
  default     = "notion-discord-bot"
  description = "Artifact Registry 内のイメージ名"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "デプロイするイメージのタグ"
}

variable "queue_name" {
  type    = string
  default = "notion-discord-bot-events"
}

# 以下 enable_* bool は "secret に version がセットされていて Cloud Run env を
# 実際に接続したい" 状態かどうかを切り替える。Cloud Run は起動時に secret の
# :latest を読むので、version が無い secret を env に繋ぐと起動失敗する。
# - notion_verification_token / notion_api_key は必須扱い (常に env を繋ぐ)
# - discord_webhook / discord_deletion_webhook は任意 (未使用時は env 未接続)
variable "enable_discord_webhook" {
  type        = bool
  default     = true
  description = "DISCORD_WEBHOOK_URL env を Cloud Run worker に接続するか。false の場合 worker は FileDiscordSender にフォールバック (stdout 出力のみ)"
}

variable "enable_discord_deletion_webhook" {
  type        = bool
  default     = false
  description = "page.deleted のみ別の Discord webhook に追送するか。true の場合、事前に `gcloud secrets versions add notion-bot-discord-deletion-webhook` で version を投入しておくこと"
}

variable "notion_allowed_events" {
  type = list(string)
  default = [
    "page.created",
    "page.content_updated",
    "page.properties_updated",
    "page.deleted",
    "comment.created",
  ]
  description = "ingress が worker に enqueue する Notion イベント種別"
}

variable "cloud_run_ingress_max_instances" {
  type    = number
  default = 10
}

variable "cloud_run_worker_max_instances" {
  type    = number
  default = 10
}
