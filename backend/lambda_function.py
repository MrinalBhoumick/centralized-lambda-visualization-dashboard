import boto3
import json
import logging
import os
import time
from datetime import datetime, timedelta
import asyncio
from openpyxl import Workbook
import tempfile
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_RETRIES = 5
RETRY_SLEEP = 1
MAX_CONCURRENT_TASKS = 10  # Limit the number of concurrent tasks
BATCH_SIZE = 500

def lambda_handler(event, context):
    # Run the asynchronous logic inside a blocking function
    return asyncio.run(handle_event(event, context))

async def handle_event(event, context):
    try:
        # Parse JSON body and extract required fields
        body = event.get("body")
        if body:
            if isinstance(body, str):
                body = json.loads(body)
        else:
            return build_response(400, {"error": "Missing request body."})

        region = body.get("region")
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        bucket_name = body.get("bucket_name")

        if not all([region, start_date, end_date, bucket_name]):
            return build_response(400, {"error": "Missing one or more required fields in request body."})

        lambda_client = boto3.client("lambda", region_name=region)
        cloudwatch = boto3.client("cloudwatch", region_name=region)
        s3 = boto3.client("s3", region_name=region)

        # Ensure the end_date is strictly after the start_date
        start_time = datetime.strptime(start_date, "%Y-%m-%d")
        end_time = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

        if start_time >= end_time:
            logger.error(f"Invalid date range: Start date {start_time} must be before End date {end_time}")
            return build_response(400, {"error": "Start date must be before end date."})

        # Fetch all Lambda functions
        paginator = lambda_client.get_paginator("list_functions")
        all_functions = [fn for page in paginator.paginate() for fn in page['Functions']]

        logger.info(f"Total functions fetched: {len(all_functions)}")

        # Process functions in smaller batches with a limit on concurrent tasks
        insights = await analyze_functions_in_batches(all_functions, lambda_client, cloudwatch, s3, start_time, end_time, bucket_name)

        if not insights:
            return {"statusCode": 500, "body": "No function metrics collected."}

        # Write to Excel
        workbook = Workbook()
        sheet = workbook.active
        headers = list(insights[0].keys())
        sheet.append(headers)
        for item in insights:
            sheet.append([item.get(h, '') for h in headers])

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            workbook.save(tmp.name)
            file_key = f"lambda-insights-report-{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
            await asyncio.to_thread(s3.upload_file, tmp.name, bucket_name, file_key)

        # Construct the HTTPS link
        file_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{file_key}"

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Lambda insights report generated.",
                "url": file_url
            })
        }

    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        return build_response(500, {"error": "Internal server error."})

async def analyze_functions_in_batches(all_functions, lambda_client, cloudwatch, s3, start_time, end_time, bucket_name):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    insights = []
    tasks = []
    
    # Process functions in smaller batches
    for i in range(0, len(all_functions), BATCH_SIZE):
        batch = all_functions[i:i + BATCH_SIZE]
        for fn in batch:
            tasks.append(analyze_function(fn, lambda_client, cloudwatch, s3, start_time, end_time, bucket_name, semaphore))
        
        results = await asyncio.gather(*tasks)
        insights.extend(filter(None, results))  # Add successful results to insights
        tasks.clear()  # Clear the tasks list to process the next batch

    return insights

async def analyze_function(fn, lambda_client, cloudwatch, s3, start_time, end_time, bucket_name, semaphore):
    async with semaphore:  # Limit concurrent execution
        name = fn['FunctionName']
        try:
            config = await asyncio.to_thread(lambda_client.get_function_configuration, FunctionName=name)
        except ClientError as e:
            logger.error(f"[{name}] Configuration fetch failed: {e}")
            return None

        memory = config.get("MemorySize", 0)
        runtime = config.get("Runtime", "unknown")
        arch = config.get("Architectures", ["x86_64"])[0]
        cold_start_risk = "High" if memory < 256 or runtime.startswith("java") or arch == "arm64" else "Low"

        metrics = {
            "Invocations": await get_metric(name, "Invocations", "Sum", cloudwatch, start_time, end_time),
            "Errors": await get_metric(name, "Errors", "Sum", cloudwatch, start_time, end_time),
            "Throttles": await get_metric(name, "Throttles", "Sum", cloudwatch, start_time, end_time),
            "Duration (sec)": round(await get_metric(name, "Duration", "Average", cloudwatch, start_time, end_time) / 1000, 2),
            "ConcurrentExecutions": await get_metric(name, "ConcurrentExecutions", "Sum", cloudwatch, start_time, end_time),
        }

        return {
            "Function Name": name,
            "Runtime": runtime,
            "Memory Size (MB)": memory,
            "Timeout (sec)": config.get("Timeout", 0),
            "Package Type": config.get("PackageType", "Zip"),
            "Provisioned Concurrency": config.get("ProvisionedConcurrencyConfig", {}).get(
                "AllocatedProvisionedConcurrentExecutions", 0),
            "Cold Start Risk": cold_start_risk,
            **metrics
        }

async def get_metric(fn_name, metric_name, stat, cloudwatch, start_time, end_time):
    for attempt in range(MAX_RETRIES):
        try:
            response = await asyncio.to_thread(cloudwatch.get_metric_statistics,
                                                Namespace="AWS/Lambda",
                                                MetricName=metric_name,
                                                Dimensions=[{"Name": "FunctionName", "Value": fn_name}],
                                                StartTime=start_time,
                                                EndTime=end_time,
                                                Period=3600,
                                                Statistics=[stat])
            datapoints = response.get("Datapoints", [])
            return datapoints[0][stat] if datapoints else 0
        except ClientError as e:
            if e.response['Error']['Code'] == 'Throttling':
                await asyncio.sleep(RETRY_SLEEP * (2 ** attempt))
            else:
                logger.error(f"[{fn_name}] Metric {metric_name} error: {e}")
                return 0
    logger.warning(f"[{fn_name}] Max retries exceeded for metric {metric_name}")
    return 0

def build_response(status_code, body):
    return {
        "statusCode": status_code,
        "body": json.dumps(body)
    }
