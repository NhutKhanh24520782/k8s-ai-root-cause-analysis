"""
scripts/data_collection/upload_to_s3.py

Uploads collected and exported datasets to AWS S3 storage under:
s3://<bucket-name>/datasets/labeled/<filename>

Usage:
    python scripts/data_collection/upload_to_s3.py --file dataset/full_metrics_dataset.csv --bucket mlops-tfstate-team
    python scripts/data_collection/upload_to_s3.py --file ml/data/dataset_cleaned.csv
"""

import argparse
import os
import sys
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

DEFAULT_BUCKET = os.getenv("S3_DATASET_BUCKET", "mlops-tfstate-team")
DEFAULT_PREFIX = "datasets/labeled"


def upload_dataset(file_path: str, bucket_name: str, prefix: str = DEFAULT_PREFIX) -> bool:
    if not os.path.exists(file_path):
        print(f"[ERR] File does not exist: {file_path}", file=sys.stderr)
        return False

    file_name = os.path.basename(file_path)
    s3_key = f"{prefix.strip('/')}/{file_name}"

    print(f"[*] Preparing to upload '{file_path}' to s3://{bucket_name}/{s3_key}")

    try:
        s3_client = boto3.client("s3")
        # Attempt upload
        s3_client.upload_file(file_path, bucket_name, s3_key)
        print(f"[OK] Successfully uploaded to s3://{bucket_name}/{s3_key}")
        return True
    except NoCredentialsError:
        print(
            "[WARN] AWS credentials not found or expired. "
            "Please configure AWS CLI with 'aws configure' or export AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY.",
            file=sys.stderr,
        )
        return False
    except ClientError as e:
        print(f"[ERR] S3 ClientError: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERR] Unexpected error uploading to S3: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Upload dataset to S3.")
    parser.add_argument("--file", required=True, help="Local file path to upload")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="Target S3 bucket name")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="Target S3 directory prefix")
    args = parser.parse_args()

    success = upload_dataset(args.file, args.bucket, args.prefix)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
