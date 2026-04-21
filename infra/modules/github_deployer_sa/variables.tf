variable "project" {
  type        = string
  description = "GCP project ID"
}

variable "sa_id" {
  type        = string
  description = "Service account ID (without @... suffix). 英数ハイフン, 30 字以内"
}

variable "display_name" {
  type        = string
  description = "Service account display name"
}

variable "wif_pool_name" {
  type        = string
  description = "Full resource name of the WIF pool (output.pool_name from infra/github_wif/)"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository in owner/name format"
}
