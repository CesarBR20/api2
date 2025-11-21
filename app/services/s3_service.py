import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError

# Crear cliente S3 sin credenciales explícitas
# Usará el task role automáticamente
def get_s3_client():
    return boto3.client('s3', region_name='us-east-1')

def upload_to_s3(file_path: str, bucket_name: str, object_name: str):
    s3_client = get_s3_client()
    s3_client.upload_file(file_path, bucket_name, object_name)

def download_from_s3(bucket_name: str, s3_key: str, local_path: str):
    s3_client = get_s3_client()
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3_key = s3_key.replace("\\", "/")
        print(f"Descargando {s3_key} desde el bucket {bucket_name}")
        s3_client.download_file(bucket_name, s3_key, local_path)
    except NoCredentialsError:
        raise Exception("Credenciales de AWS no encontradas.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            raise Exception(f"El objeto {s3_key} no existe en el bucket {bucket_name}.")
        else:
            raise Exception(f"Error al descargar el archivo desde S3: {e}")

def upload_token_to_s3(bucket_name: str, s3_key: str, content: str):
    s3 = get_s3_client()
    try:
        s3.put_object(Bucket=bucket_name, Key=s3_key, Body=content.encode("utf-8"))
        print(f"Token subido correctamente a S3 en {s3_key}")
    except Exception as e:
        raise Exception(f"Error al subir el token a S3: {str(e)}")

def read_file_from_s3(bucket_name: str, s3_key: str) -> str:
    s3 = get_s3_client()
    obj = s3.get_object(Bucket=bucket_name, Key=s3_key)
    return obj['Body'].read().decode("utf-8")

def upload_file_to_s3(bucket_name: str, s3_key: str, local_path: str):
    s3 = get_s3_client()
    with open(local_path, "rb") as f:
        s3.put_object(Bucket=bucket_name, Key=s3_key, Body=f)