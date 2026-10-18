locals {
  tags = {
    Project = var.project_name
    Env     = var.environment
  }

  lambda_runtime = "python3.11"
  lambda_timeout = 5
  lambda_memory  = 256
}

# One package for both functions. boto3 is provided by the Lambda runtime,
# so the archive is only this repository's Python source.
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../backend"
  output_path = "${path.module}/build/lambda.zip"
  excludes = [
    "devserver.py",
    "__pycache__",
    "**/__pycache__/**",
  ]
}

resource "aws_dynamodb_table" "url" {
  name                        = var.table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "short_code"
  deletion_protection_enabled = var.protect_table

  attribute {
    name = "short_code"
    type = "S"
  }

  # Reads check expires_at themselves. TTL deletion is asynchronous and is
  # not the authorization decision for an expired link.
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  tags = local.tags
}

resource "aws_cloudwatch_log_group" "shortener" {
  name              = "/aws/lambda/${var.shortener_function_name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "redirect" {
  name              = "/aws/lambda/${var.redirect_function_name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

resource "aws_iam_role" "shortener_role" {
  name = "urlshortener-shortener-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role" "redirect_role" {
  name = "urlshortener-redirect-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "shortener_basic" {
  name = "urlshortener-shortener-logs"
  role = aws_iam_role.shortener_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "WriteFunctionLogs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = [
        aws_cloudwatch_log_group.shortener.arn,
        "${aws_cloudwatch_log_group.shortener.arn}:*",
      ]
    }]
  })
}

resource "aws_iam_role_policy" "shortener_dynamoDB" {
  name = "urlshortener-shortener-dynamodb"
  role = aws_iam_role.shortener_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "CreateMappings"
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem"]
      Resource = aws_dynamodb_table.url.arn
    }]
  })
}

resource "aws_iam_role_policy" "redirect_basic" {
  name = "urlshortener-redirect-logs"
  role = aws_iam_role.redirect_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "WriteFunctionLogs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = [
        aws_cloudwatch_log_group.redirect.arn,
        "${aws_cloudwatch_log_group.redirect.arn}:*",
      ]
    }]
  })
}

resource "aws_iam_role_policy" "redirect_dynamodb" {
  name = "urlshortener-redirect-dynamodb"
  role = aws_iam_role.redirect_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadAndCount"
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
      ]
      Resource = aws_dynamodb_table.url.arn
    }]
  })
}

resource "aws_lambda_function" "shortener" {
  function_name    = var.shortener_function_name
  role             = aws_iam_role.shortener_role.arn
  runtime          = local.lambda_runtime
  handler          = "handlers.shorten.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = local.lambda_timeout
  memory_size      = local.lambda_memory
  architectures    = ["arm64"]

  environment {
    variables = {
      TABLE_NAME      = var.table_name
      PUBLIC_BASE_URL = var.public_base_url
      LOG_LEVEL       = var.log_level
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.shortener,
    aws_iam_role_policy.shortener_basic,
  ]

  tags = local.tags
}

resource "aws_lambda_function" "redirect" {
  function_name    = var.redirect_function_name
  role             = aws_iam_role.redirect_role.arn
  runtime          = local.lambda_runtime
  handler          = "handlers.redirect.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = local.lambda_timeout
  memory_size      = local.lambda_memory
  architectures    = ["arm64"]

  environment {
    variables = {
      TABLE_NAME      = var.table_name
      PUBLIC_BASE_URL = var.public_base_url
      LOG_LEVEL       = var.log_level
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.redirect,
    aws_iam_role_policy.redirect_basic,
  ]

  tags = local.tags
}

resource "aws_apigatewayv2_api" "http_api" {
  name          = var.api_name
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["content-type", "accept"]
    allow_methods     = ["GET", "POST", "OPTIONS"]
    allow_origins     = var.allowed_origins
    max_age           = 600
  }

  tags = local.tags
}

resource "aws_apigatewayv2_integration" "shorten_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.shortener.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 5000
}

resource "aws_apigatewayv2_integration" "redirect_integration" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.redirect.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 5000
}

resource "aws_apigatewayv2_route" "shorten_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /shorten"
  target    = "integrations/${aws_apigatewayv2_integration.shorten_integration.id}"
}

resource "aws_apigatewayv2_route" "redirect_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /r/{code}"
  target    = "integrations/${aws_apigatewayv2_integration.redirect_integration.id}"
}

resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true

  # These limits are shared by all callers. They cap cost; they are not per-IP fairness.
  default_route_settings {
    throttling_burst_limit = var.default_throttle_burst
    throttling_rate_limit  = var.default_throttle_rate
  }

  route_settings {
    route_key              = "POST /shorten"
    throttling_burst_limit = var.shorten_throttle_burst
    throttling_rate_limit  = var.shorten_throttle_rate
  }

  route_settings {
    route_key              = "GET /r/{code}"
    throttling_burst_limit = var.redirect_throttle_burst
    throttling_rate_limit  = var.redirect_throttle_rate
  }

  tags = local.tags
}

resource "aws_lambda_permission" "allow_api_invoke_shortener" {
  statement_id  = "AllowAPIGatewayInvokeShortener"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.shortener.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/POST/shorten"
}

resource "aws_lambda_permission" "allow_api_invoke_redirect" {
  statement_id  = "AllowAPIGatewayInvokeRedirect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.redirect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/GET/r/*"
}

resource "aws_cloudwatch_metric_alarm" "shortener_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.shortener_function_name}-errors"
  alarm_description   = "Shortener Lambda reported errors."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]
  ok_actions          = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]

  dimensions = {
    FunctionName = aws_lambda_function.shortener.function_name
  }

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "redirect_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.redirect_function_name}-errors"
  alarm_description   = "Redirect Lambda reported errors."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]
  ok_actions          = var.alarm_sns_topic_arn == "" ? [] : [var.alarm_sns_topic_arn]

  dimensions = {
    FunctionName = aws_lambda_function.redirect.function_name
  }

  tags = local.tags
}
