variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Optional local AWS CLI profile. Leave empty when using environment credentials or GitHub OIDC."
  type        = string
  default     = ""
}

variable "project_name" {
  description = "Tag value used to group resources."
  type        = string
  default     = "serverless-url-shortener"
}

variable "environment" {
  description = "Tag value such as dev or prod. Changing it does not rename existing resources."
  type        = string
  default     = "dev"
}

variable "table_name" {
  description = "DynamoDB table name. The default preserves the original deployed name."
  type        = string
  default     = "URLShortner"
}

variable "shortener_function_name" {
  description = "Lambda function that creates short links. Changing this creates a new function."
  type        = string
  default     = "urlshortener-shortener"
}

variable "redirect_function_name" {
  description = "Lambda function that resolves short links. Changing this creates a new function."
  type        = string
  default     = "urlshortener-redirect"
}

variable "api_name" {
  description = "API Gateway HTTP API name. Changing this creates a new API and a new invoke URL."
  type        = string
  default     = "urlshortener-http-api"
}

variable "public_base_url" {
  description = "Absolute base URL placed in short_url responses. Empty derives the URL from the API Gateway event."
  type        = string
  default     = ""
}

variable "log_level" {
  description = "Application log level: DEBUG, INFO, WARNING, or ERROR."
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "CloudWatch log retention. Short retention is the main log-cost control."
  type        = number
  default     = 14
}

variable "allowed_origins" {
  description = "Browser origins allowed to call POST /shorten. This does not restrict non-browser clients."
  type        = list(string)
  default     = ["*"]
}

variable "shorten_throttle_rate" {
  description = "Steady requests per second for POST /shorten, shared by every client."
  type        = number
  default     = 5
}

variable "shorten_throttle_burst" {
  description = "Burst size for POST /shorten."
  type        = number
  default     = 10
}

variable "redirect_throttle_rate" {
  description = "Steady requests per second for GET /r/{code}, shared by every client."
  type        = number
  default     = 20
}

variable "redirect_throttle_burst" {
  description = "Burst size for GET /r/{code}."
  type        = number
  default     = 40
}

variable "default_throttle_rate" {
  description = "Steady requests per second for any route without its own limit."
  type        = number
  default     = 10
}

variable "default_throttle_burst" {
  description = "Burst size for routes without their own limit."
  type        = number
  default     = 20
}

variable "point_in_time_recovery" {
  description = "Enable DynamoDB point-in-time recovery. This has an ongoing storage cost."
  type        = bool
  default     = true
}

variable "protect_table" {
  description = "Block deletion of the DynamoDB table at the AWS API."
  type        = bool
  default     = false
}

variable "enable_alarms" {
  description = "Create CloudWatch alarms for Lambda errors. Alarms have a small monthly cost."
  type        = bool
  default     = false
}

variable "alarm_sns_topic_arn" {
  description = "Optional SNS topic for alarm notifications. Leave empty to alarm without notifying."
  type        = string
  default     = ""
}
