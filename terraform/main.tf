locals {
  function_name = "aws-cost-optimizer"
}

# Lambda execution role
resource "aws_iam_role" "lambda_role" {
  name = "cost-optimizer-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Policy for Lambda
resource "aws_iam_role_policy" "lambda_policy" {
  name = "cost-optimizer-policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeAddresses",
          "ec2:DescribeInstances",
          "s3:ListAllMyBuckets",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:ListMultipartUploadParts",
          "ce:GetCostAndUsage",
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:PutLogEvents",
          "ses:SendEmail",
          "ses:SendRawEmail",
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots",
          "ec2:DescribeImages",
          "ec2:DescribeSecurityGroups",
          "iam:ListUsers",
          "iam:GetLoginProfile",
        ]
        Resource = "*"
      }
    ]
  })
}

# Zip the Lambda function
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda/cost_optimizer.py"
  output_path = "${path.module}/cost_optimizer.zip"
}

# Lambda function
resource "aws_lambda_function" "cost_optimizer" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = local.function_name
  role             = aws_iam_role.lambda_role.arn
  handler          = "cost_optimizer.lambda_handler"
  runtime          = "python3.11"
  timeout          = 60
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      ACCOUNT_ID    = "600743178233"
      SENDER_EMAIL  = "costs@cboloz.com"
      RECIPIENT_EMAIL = "cdboloz1@gmail.com"
    }
  }
}

# EventBridge rule — runs daily at 8am UTC
resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "cost-optimizer-weekly"
  description         = "Triggers cost optimizer Lambda weekly on Monday 8am"
  schedule_expression = "cron(0 8 ? * MON *)"
}

# Connect EventBridge to Lambda
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_trigger.name
  target_id = "CostOptimizerLambda"
  arn       = aws_lambda_function.cost_optimizer.arn
}

# Allow EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_optimizer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger.arn
}