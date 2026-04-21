variable "project" {
  type        = string
  description = "GCP project ID"
}

variable "location" {
  type        = string
  description = "Artifact Registry location (region)"
}

variable "repository_id" {
  type        = string
  description = "Artifact Registry repository ID"
}

variable "description" {
  type        = string
  default     = ""
  description = "Repository description"
}
