"""
Phase 5: the only module in this project allowed to call sts:AssumeRole.

On every "allow" decision for an AWS-backed tool (s3_put_object,
send_email), this assumes the baseline role fresh, with an inline session
policy narrowed to that one call's specific resource -- not just "the
bucket", the exact key; not just "SES", the exact identity. On deny or
require_approval, nothing in this module is ever invoked at all -- see
proxy/main.py's AWS_BACKED_TOOLS branch, which only reaches this module
after the policy decision is already "allow".

Config is read lazily, inside put_object()/send_email(), NOT at module
import time. This module gets imported unconditionally by main.py
regardless of whether USE_REAL_AWS is set -- if the required env vars
were read at import time, every earlier phase's run script would crash
on proxy startup even with AWS features completely unused, since the
crash would happen before USE_REAL_AWS is ever checked.
"""
import json
import os
import time

import boto3

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _config():
    try:
        return {
            "baseline_role_arn": os.environ["BASELINE_ROLE_ARN"],
            "bucket_name": os.environ["BUCKET_NAME"],
            "ses_identity_arn": os.environ["SES_IDENTITY_ARN"],
            "ses_sender": os.environ["SES_SENDER"],
        }
    except KeyError as e:
        raise RuntimeError(
            f"Phase 5 AWS config missing: {e}. Set BASELINE_ROLE_ARN, "
            "BUCKET_NAME, SES_IDENTITY_ARN, and SES_SENDER before using "
            "AWS-backed tools."
        ) from e


def _assume_scoped(session_policy, session_name, baseline_role_arn):
    sts = boto3.client("sts", region_name=AWS_REGION)
    resp = sts.assume_role(
        RoleArn=baseline_role_arn,
        RoleSessionName=session_name,
        Policy=json.dumps(session_policy),
        DurationSeconds=900,  # minimum AWS allows; these are single-call sessions
    )
    creds = resp["Credentials"]
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }


def put_object(key, content):
    # Deliberately ignores any "bucket" argument the caller might have
    # supplied -- always uses the one configured bucket. Honoring an
    # agent-supplied bucket name here would defeat the entire point of
    # scoping the baseline role's permissions to one specific bucket ARN.
    cfg = _config()
    object_arn = f"arn:aws:s3:::{cfg['bucket_name']}/{key}"
    session_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "s3:PutObject",
            "Resource": object_arn,
        }],
    }
    creds = _assume_scoped(session_policy, f"s3put-{int(time.time() * 1000)}", cfg["baseline_role_arn"])
    s3 = boto3.client("s3", region_name=AWS_REGION, **creds)
    s3.put_object(Bucket=cfg["bucket_name"], Key=key, Body=content.encode())
    return {"bucket": cfg["bucket_name"], "key": key, "backend": "aws"}


def send_email(to_address, subject, body):
    cfg = _config()
    session_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "ses:SendEmail",
            "Resource": cfg["ses_identity_arn"],
        }],
    }
    creds = _assume_scoped(session_policy, f"sesemail-{int(time.time() * 1000)}", cfg["baseline_role_arn"])
    ses = boto3.client("ses", region_name=AWS_REGION, **creds)
    resp = ses.send_email(
        Source=cfg["ses_sender"],
        Destination={"ToAddresses": [to_address]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
    return {"message_id": resp["MessageId"], "backend": "aws"}
