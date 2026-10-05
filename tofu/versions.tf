# Provider constraint shared by `make providers` (offline mirror) and the generated estate (ADR-0014).
# Change it here only; the estate generator copies this file into the estate.
terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
