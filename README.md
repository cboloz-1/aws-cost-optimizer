# AWS Cost Intelligence & Security Scanner

A serverless AWS cost optimization and security scanning tool. A Lambda function runs on a weekly schedule, scans your AWS account for idle resources and security misconfigurations, pulls a cost breakdown from Cost Explorer, and delivers a formatted HTML report to your inbox via SES.

## Email Report

The weekly report includes:
- Month-to-date spend broken down by AWS service
- Idle resource findings with severity ratings
- Security group misconfigurations
- IAM user activity analysis

## Architecture

```
EventBridge (cron — every Monday 8am UTC)
    ↓
Lambda Function (Python 3.11)
    ├── EC2 — unattached EIPs, stopped instances
    ├── EBS — unattached volumes, old snapshots
    ├── S3  — empty buckets
    ├── Security Groups — unrestricted access rules
    ├── IAM — inactive users
    └── Cost Explorer — month-to-date spend by service
    ↓
CloudWatch — publishes custom metrics
    ├── CostOptimizer/MonthToDateCost
    └── CostOptimizer/IdleResourceCount
    ↓
SES — sends HTML email report from costs@cboloz.com
```

## Stack

| Tool | Purpose |
|------|---------|
| AWS Lambda | Serverless function |
| AWS EventBridge | Schedules Lambda weekly |
| AWS Cost Explorer | Pulls month-to-date spend by service |
| AWS SES | Sends formatted HTML email report |
| AWS CloudWatch | Stores custom cost and findings metrics |
| Terraform | Provisions all infrastructure as code |

## Resources Scanned

| Resource | Finding | Severity |
|----------|---------|----------|
| Elastic IPs | Unattached —> charges apply | HIGH |
| EC2 Instances | Stopped —> EBS still billing | MEDIUM |
| EBS Volumes | Unattached —> still incurring charges | HIGH |
| EBS Snapshots | Older than 90 days, not tied to AMI | LOW |
| S3 Buckets | Empty buckets | LOW |
| Security Groups | Unrestricted ingress on non-80/443 ports | HIGH |
| IAM Users | No activity in 90+ days | MEDIUM |

## Infrastructure

```
aws-cost-optimizer/
├── terraform/
│   ├── main.tf        # Lambda, IAM role, EventBridge rule
│   └── providers.tf   # AWS provider + S3 backend
└── lambda/
    └── cost_optimizer.py  # Scanner and email logic
```

## Notes

- CloudWatch custom metrics enable Grafana dashboard integration
- Currently alert-only. No automatic remediation