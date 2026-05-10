import boto3
import json
import os
from datetime import datetime, timedelta

# Clients
ec2 = boto3.client('ec2', region_name='us-east-1')
s3 = boto3.client('s3', region_name='us-east-1')
ce = boto3.client('ce', region_name='us-east-1')
ses = boto3.client('ses', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

ACCOUNT_ID = os.environ['ACCOUNT_ID']
SENDER_EMAIL = os.environ['SENDER_EMAIL']
RECIPIENT_EMAIL = os.environ['RECIPIENT_EMAIL']

def get_unattached_eips():
    findings = []
    response = ec2.describe_addresses()
    for addr in response['Addresses']:
        if 'InstanceId' not in addr and 'NetworkInterfaceId' not in addr:
            findings.append({
                'resource': 'Elastic IP',
                'id': addr.get('PublicIp', 'Unknown'),
                'detail': 'Unattached EIP — charges apply when not associated',
                'severity': 'HIGH'
            })
    return findings

def get_stopped_instances():
    findings = []
    response = ec2.describe_instances(
        Filters=[{'Name': 'instance-state-name', 'Values': ['stopped']}]
    )
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            name = 'Unnamed'
            if 'Tags' in instance:
                for tag in instance['Tags']:
                    if tag['Key'] == 'Name':
                        name = tag['Value']
            findings.append({
                'resource': 'EC2 Instance',
                'id': f"{instance['InstanceId']} ({name})",
                'detail': f"Stopped instance — EBS volumes still incurring costs. Type: {instance['InstanceType']}",
                'severity': 'MEDIUM'
            })
    return findings

def get_unused_s3_buckets():
    findings = []
    try:
        buckets = s3.list_buckets()['Buckets']
        for bucket in buckets:
            bucket_name = bucket['Name']
            try:
                response = s3.list_objects_v2(
                    Bucket=bucket_name,
                    MaxKeys=1
                )
                if response.get('KeyCount', 0) == 0:
                    findings.append({
                        'resource': 'S3 Bucket',
                        'id': bucket_name,
                        'detail': 'Empty S3 bucket — consider removing if unused',
                        'severity': 'LOW'
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"Error scanning S3: {e}")
    return findings

def get_cost_breakdown():
    end = datetime.utcnow().strftime('%Y-%m-%d')
    start = datetime.utcnow().replace(day=1).strftime('%Y-%m-%d')

    response = ce.get_cost_and_usage(
        TimePeriod={'Start': start, 'End': end},
        Granularity='MONTHLY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
    )

    services = []
    total = 0.0

    for result in response['ResultsByTime']:
        for group in result['Groups']:
            amount = float(group['Metrics']['UnblendedCost']['Amount'])
            if amount > 0.001:
                services.append({
                    'service': group['Keys'][0],
                    'cost': amount
                })
                total += amount

    services.sort(key=lambda x: x['cost'], reverse=True)
    return services, total

def publish_cloudwatch_metrics(total_cost, findings_count):
    cloudwatch.put_metric_data(
        Namespace='CostOptimizer',
        MetricData=[
            {
                'MetricName': 'MonthToDateCost',
                'Value': total_cost,
                'Unit': 'None',
                'Dimensions': [{'Name': 'Account', 'Value': ACCOUNT_ID}]
            },
            {
                'MetricName': 'IdleResourceCount',
                'Value': findings_count,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'Account', 'Value': ACCOUNT_ID}]
            }
        ]
    )

def get_severity_color(severity):
    colors = {
        'HIGH': '#dc2626',
        'MEDIUM': '#d97706',
        'LOW': '#2563eb'
    }
    return colors.get(severity, '#6b7280')

def build_html_email(findings, services, total_cost):
    today = datetime.utcnow().strftime('%B %d, %Y')

    findings_rows = ''
    if findings:
        for f in findings:
            color = get_severity_color(f['severity'])
            findings_rows += f"""
            <tr>
                <td style="padding:10px;border-bottom:1px solid #e5e7eb;">{f['resource']}</td>
                <td style="padding:10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;">{f['id']}</td>
                <td style="padding:10px;border-bottom:1px solid #e5e7eb;">{f['detail']}</td>
                <td style="padding:10px;border-bottom:1px solid #e5e7eb;">
                    <span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;">
                        {f['severity']}
                    </span>
                </td>
            </tr>"""
    else:
        findings_rows = '<tr><td colspan="4" style="padding:16px;text-align:center;color:#6b7280;">No idle resources found</td></tr>'

    cost_rows = ''
    for svc in services[:8]:
        cost_rows += f"""
        <tr>
            <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">{svc['service']}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600;">${svc['cost']:.4f}</td>
        </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f3f4f6;margin:0;padding:20px;">
        <div style="max-width:700px;margin:0 auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,0.1);">

            <div style="background:#0f172a;padding:32px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:24px;font-weight:700;">AWS Cost Intelligence Report</h1>
                <p style="color:#94a3b8;margin:8px 0 0;font-size:14px;">{today} — Account: {ACCOUNT_ID}</p>
            </div>

            <div style="padding:32px;background:#f8fafc;border-bottom:1px solid #e5e7eb;">
                <h2 style="margin:0 0 20px;font-size:16px;color:#374151;text-transform:uppercase;letter-spacing:0.05em;">Month-to-Date Spend</h2>
                <div style="text-align:center;">
                    <span style="font-size:48px;font-weight:800;color:#0f172a;">${total_cost:.2f}</span>
                    <p style="color:#6b7280;margin:4px 0 0;font-size:14px;">Total AWS spend this month</p>
                </div>
                <table style="width:100%;border-collapse:collapse;margin-top:24px;">
                    <thead>
                        <tr style="background:#e5e7eb;">
                            <th style="padding:8px 10px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase;">Service</th>
                            <th style="padding:8px 10px;text-align:right;font-size:12px;color:#6b7280;text-transform:uppercase;">Cost</th>
                        </tr>
                    </thead>
                    <tbody>{cost_rows}</tbody>
                    <tfoot>
                        <tr style="background:#f1f5f9;">
                            <td style="padding:10px;font-weight:700;">Total</td>
                            <td style="padding:10px;text-align:right;font-weight:700;">${total_cost:.4f}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            <div style="padding:32px;">
                <h2 style="margin:0 0 8px;font-size:16px;color:#374151;text-transform:uppercase;letter-spacing:0.05em;">
                    Idle Resource Findings
                    <span style="background:#fee2e2;color:#dc2626;padding:2px 8px;border-radius:20px;font-size:12px;margin-left:8px;">
                        {len(findings)} found
                    </span>
                </h2>
                <p style="color:#6b7280;font-size:14px;margin:0 0 20px;">Resources that may be incurring unnecessary costs</p>
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f1f5f9;">
                            <th style="padding:10px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase;">Resource</th>
                            <th style="padding:10px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase;">ID</th>
                            <th style="padding:10px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase;">Detail</th>
                            <th style="padding:10px;text-align:left;font-size:12px;color:#6b7280;text-transform:uppercase;">Severity</th>
                        </tr>
                    </thead>
                    <tbody>{findings_rows}</tbody>
                </table>
            </div>

            <div style="padding:24px 32px;background:#f8fafc;border-top:1px solid #e5e7eb;text-align:center;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    AWS Cost Optimizer — Automated daily report<br>
                    Running on AWS Lambda — Deployed via Terraform
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def lambda_handler(event, context):
    print("Starting cost optimization scan...")

    findings = []
    findings.extend(get_unattached_eips())
    findings.extend(get_stopped_instances())
    findings.extend(get_unused_s3_buckets())

    services, total_cost = get_cost_breakdown()

    publish_cloudwatch_metrics(total_cost, len(findings))

    html_body = build_html_email(findings, services, total_cost)

    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={'ToAddresses': [RECIPIENT_EMAIL]},
        Message={
            'Subject': {
                'Data': f"AWS Cost Report — ${total_cost:.2f} MTD — {len(findings)} idle resources found"
            },
            'Body': {
                'Html': {'Data': html_body}
            }
        }
    )

    print(f"Scan complete. Total cost: ${total_cost:.2f}. Findings: {len(findings)}")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'total_cost': total_cost,
            'findings_count': len(findings),
            'findings': findings
        })
    }