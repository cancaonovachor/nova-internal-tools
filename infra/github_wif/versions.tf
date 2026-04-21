terraform {
  required_version = ">= 1.5"

  backend "gcs" {
    bucket = "starlit-road-203901-tfstate"
    prefix = "github-wif"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
  }
}

provider "google" {
  project = "starlit-road-203901"
  region  = "asia-northeast1"
}
