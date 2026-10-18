output "table_name" {
  description = "DynamoDB table name."
  value       = aws_dynamodb_table.url.name
}

output "table_arn" {
  description = "DynamoDB table ARN."
  value       = aws_dynamodb_table.url.arn
}

output "http_api_url" {
  description = "API Gateway invoke URL for the $default stage."
  value       = aws_apigatewayv2_api.http_api.api_endpoint
}

output "shorten_endpoint" {
  description = "POST this URL to create a short link."
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/shorten"
}

output "redirect_base_url" {
  description = "Short links are served under this prefix."
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/r"
}
