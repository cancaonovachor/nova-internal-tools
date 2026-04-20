terraform {
  required_version = ">= 1.5"

  backend "gcs" {
    bucket = "starlit-road-203901-tfstate"
    prefix = "notion-discord-bot"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
