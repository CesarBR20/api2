import os
from app.utils.pem_converter import convert_to_pem
from app.services.s3_service import upload_to_s3
import subprocess
from datetime import datetime
from app.config_loader import load_config

async def process_client_files(cer_file, key_file, password, rfc):
    temp_dir = f"/tmp/{rfc}"
    os.makedirs(temp_dir, exist_ok=True)

    cer_path = os.path.join(temp_dir, cer_file.filename)
    key_path = os.path.join(temp_dir, key_file.filename)

    with open(cer_path, "wb") as f:
        f.write(await cer_file.read())
    with open(key_path, "wb") as f:
        f.write(await key_file.read())

    cert_pem, key_pem = convert_to_pem(cer_path, key_path, password, temp_dir)

    # Subir archivos a S3
    s3_paths = {
        "cert_pem": f"clientes/{rfc}/certificados/cert.pem",
        "key_pem": f"clientes/{rfc}/certificados/key.pem",
        "cer": f"clientes/{rfc}/certificados/{cer_file.filename}",
        "key": f"clientes/{rfc}/certificados/{key_file.filename}",
        "password": f"clientes/{rfc}/certificados/password.txt"
    }

    upload_to_s3(cert_pem, s3_paths["cert_pem"])
    upload_to_s3(key_pem, s3_paths["key_pem"])
    upload_to_s3(cer_path, s3_paths["cer"])
    upload_to_s3(key_path, s3_paths["key"])
    with open(os.path.join(temp_dir, "password.txt"), "w") as f:
        f.write(password)
    upload_to_s3(os.path.join(temp_dir, "password.txt"), s3_paths["password"])

    return s3_paths

def authenticate_with_sat(cert_pem_path, key_pem_path, password, output_path, rfc):
    config = load_config()
    auth_endpoint = config['endpoints']['autenticacion']
    auth_action = config['endpoints']['autenticacion_action']

    try:
        subprocess.run([
            "python", "scripts/1_auth.py",
            "--cert", cert_pem_path,
            "--key", key_pem_path,
            "--pass", password,
            "--output", output_path
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error al ejecutar el script de autenticación: {e}")

    bucket_name = os.getenv('S3_BUCKET_NAME')
    if not bucket_name:
        raise Exception("El nombre del bucket S3 no está configurado en las variables de entorno.")

    s3_token_path = f"clientes/{rfc}/tokens/token.txt"
    upload_to_s3(output_path, bucket_name, s3_token_path)
    
    return s3_token_path

def create_sat_requests(token_path: str, rfc: str, start_year: int, output_dir: str):
    # Leer el token desde el archivo
    with open(token_path, "r") as f:
        token = f.read().strip()

    # Crear las solicitudes de metadata (2 semestres)
    metadata_periods = [("01", "06"), ("07", "12")]
    for start_month, end_month in metadata_periods:
        start_date = f"{start_year}-{start_month}-01"
        end_date = f"{start_year}-{end_month}-30"
        subprocess.run([
            "python", "scripts/2_req.py",
            "--token", token,
            "--rfc", rfc,
            "--type", "metadata",
            "--start", start_date,
            "--end", end_date,
            "--output", output_dir
        ], check=True)

    # Crear las solicitudes de CFDI (12 meses)
    for month in range(1, 13):
        start_date = f"{start_year}-{month:02d}-01"
        end_date = f"{start_year}-{month:02d}-30"
        subprocess.run([
            "python", "scripts/2_req.py",
            "--token", token,
            "--rfc", rfc,
            "--type", "cfdi",
            "--start", start_date,
            "--end", end_date,
            "--output", output_dir
        ], check=True)
        
def verify_sat_requests(token_path: str, rfc: str, output_dir: str):
    with open(token_path, "r") as f:
        token = f.read().strip()

    # Asumiendo que tienes un archivo con los IDs de solicitud
    solicitud_ids_path = os.path.join(output_dir, "id_solicitud.txt")
    with open(solicitud_ids_path, "r") as f:
        solicitud_ids = f.read().splitlines()

    for solicitud_id in solicitud_ids:
        subprocess.run([
            "python", "scripts/3_verify.py",
            "--token", token,
            "--rfc", rfc,
            "--request_id", solicitud_id,
            "--output", output_dir
        ], check=True)
        
def download_sat_packages(token_path: str, rfc: str, output_dir: str):
    with open(token_path, "r") as f:
        token = f.read().strip()

    paquetes_ids_path = os.path.join(output_dir, "paquetes.txt")
    with open(paquetes_ids_path, "r") as f:
        paquete_ids = f.read().splitlines()

    for paquete_id in paquete_ids:
        subprocess.run([
            "python", "scripts/4_dwnld.py",
            "--token", token,
            "--rfc", rfc,
            "--package_id", paquete_id,
            "--output", output_dir
        ], check=True)
