import boto3
import os

def upload_to_s3(file_path: str, bucket_name: str, object_name: str):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION')
    )
    s3_client.upload_file(file_path, bucket_name, object_name)
