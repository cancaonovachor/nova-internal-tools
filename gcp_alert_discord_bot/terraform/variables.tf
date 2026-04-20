# NOTE: このモジュールでは tfvars を使わない方針。
# - 固定値は main.tf の locals に置く
# - 機密値 (Discord webhook URL 等) は Terraform で secret resource のみ作成し、
#   `gcloud secrets versions add` でアウトオブバンドに投入する
# 将来変動しうる軽い設定のみここに variable として残す。

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "デプロイするイメージのタグ"
}

variable "cloud_run_max_instances" {
  type    = number
  default = 5
}

variable "create_monitoring_channel" {
  type        = bool
  default     = true
  description = "Cloud Monitoring の Pub/Sub 通知チャンネルを作成するか"
}

variable "cloud_run_alert_enabled" {
  type        = bool
  default     = true
  description = "Cloud Run services / Cloud Run Jobs の ERROR ログを検出する alert policy を作成するか (gcp-alert-discord-bot 自身は除外)"
}
