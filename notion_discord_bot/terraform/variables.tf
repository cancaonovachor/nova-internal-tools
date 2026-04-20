variable "project_id" {
  type        = string
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

variable "notion_verification_token" {
  type        = string
  sensitive   = true
  description = "Notion webhook subscription の verification token"
}

variable "notion_api_key" {
  type        = string
  sensitive   = true
  description = "Notion integration の Internal Integration Token"
}

variable "discord_webhook_url" {
  type        = string
  sensitive   = true
  default     = ""
  description = "空文字の場合 worker は FileDiscordSender を使う（stdout ログのみ）"
}

variable "discord_deletion_webhook_url" {
  type        = string
  sensitive   = true
  default     = ""
  description = "page.deleted のみ追加で送る Discord webhook URL。空文字で無効"
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
