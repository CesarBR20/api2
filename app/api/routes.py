from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.sat_service import process_client_files
from app.services.sat_service import authenticate_with_sat
from app.services.sat_service import create_sat_requests
from app.services.sat_service import verify_sat_requests
from app.services.sat_service import download_sat_packages
from app.services.sat_service import convert_to_pem
from app.utils.pem_converter import convert_to_pem
from app.services.s3_service import upload_to_s3, download_from_s3
import os

router = APIRouter()

@router.post("/convert-and-upload-certificates/")
async def convert_and_upload_certificates(
    cer_file: UploadFile = File(...),
    key_file: UploadFile = File(...),
    password_file: UploadFile = File(...),
    rfc: str = Form(...)
):
    # Crear un directorio temporal para almacenar los archivos
    temp_dir = f"/tmp/{rfc}"
    os.makedirs(temp_dir, exist_ok=True)

    # Guardar los archivos subidos
    cer_path = os.path.join(temp_dir, cer_file.filename)
    key_path = os.path.join(temp_dir, key_file.filename)
    password_path = os.path.join(temp_dir, password_file.filename)

    with open(cer_path, "wb") as f:
        f.write(await cer_file.read())
    with open(key_path, "wb") as f:
        f.write(await key_file.read())
    with open(password_path, "wb") as f:
        f.write(await password_file.read())

    # Convertir los archivos a formato PEM
    cert_pem_path, fiel_pem_path = convert_to_pem(cer_path, key_path, password_path, temp_dir)

    # Subir los archivos a S3
    bucket_name = os.getenv('S3_BUCKET_NAME')
    if not bucket_name:
        raise Exception("No se ha definido el nombre del bucket en el archivo .env")
    upload_to_s3(cert_pem_path, bucket_name, f"clientes/{rfc}/certificados/cert.pem")
    upload_to_s3(fiel_pem_path, bucket_name, f"clientes/{rfc}/certificados/fiel.pem")
    upload_to_s3(password_path, bucket_name, f"clientes/{rfc}/certificados/{password_file.filename}")

    return {
        "message": "Archivos convertidos y subidos exitosamente",
        "cert_pem_s3_path": f"{rfc}/cert.pem",
        "fiel_pem_s3_path": f"{rfc}/fiel.pem",
        "password_s3_path": f"{rfc}/{password_file.filename}"
    }

@router.post("/auth-sat/")
async def auth_sat(
    rfc: str = Form(...)
):
    temp_dir = f"/tmp/{rfc}"
    os.makedirs(temp_dir, exist_ok=True)

    bucket_name = os.getenv('S3_BUCKET_NAME')
    if not bucket_name:
        raise HTTPException(status_code=500, detail="No se ha definido el nombre del bucket en el archivo .env")

    # Definir rutas en S3
    cert_s3_key = f"clientes/{rfc}/certificados/cert.pem"
    key_s3_key = f"clientes/{rfc}/certificados/fiel.pem"
    password_s3_key = f"clientes/{rfc}/certificados/password.txt"

    # Definir rutas locales
    cert_local_path = os.path.join(temp_dir, "cert.pem")
    key_local_path = os.path.join(temp_dir, "fiel.pem")
    password_local_path = os.path.join(temp_dir, "password.txt")

    # Descargar archivos desde S3
    try:
        download_from_s3(bucket_name, cert_s3_key, cert_local_path)
        download_from_s3(bucket_name, key_s3_key, key_local_path)
        download_from_s3(bucket_name, password_s3_key, password_local_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al descargar archivos desde S3: {str(e)}")

    # Leer la contraseña
    try:
        with open(password_local_path, "r") as f:
            password = f.read().strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer el archivo de contraseña: {str(e)}")

    # Autenticarse con el SAT
    try:
        token_path = authenticate_with_sat(cert_local_path, key_local_path, password, temp_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al autenticar con el SAT: {str(e)}")

    # Subir el token a S3
    token_s3_key = f"clientes/{rfc}/tokens/token.txt"
    try:
        upload_to_s3(token_path, bucket_name, token_s3_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir el token a S3: {str(e)}")

    return {"message": "Autenticación exitosa", "token_s3_path": token_s3_key}

@router.post("/solicitar-cfdi/")
async def solicitar_cfdi(
    rfc: str = Form(...),
    year: int = Form(...)
):
    temp_dir = f"/tmp/{rfc}"
    token_path = f"{temp_dir}/token.txt"
    output_dir = f"{temp_dir}/solicitudes"

    os.makedirs(output_dir, exist_ok=True)

    create_sat_requests(token_path, rfc, year, output_dir)

    return {"message": "Solicitudes realizadas exitosamente"}

@router.post("/verificar-solicitudes/")
async def verificar_solicitudes(
    rfc: str = Form(...),
    year: int = Form(...)
):
    temp_dir = f"/tmp/{rfc}/solicitudes/{year}"
    token_path = f"/tmp/{rfc}/token.txt"

    verify_sat_requests(token_path, rfc, temp_dir)

    return {"message": "Verificación de solicitudes completada"}

@router.post("/descargar-paquetes/")
async def descargar_paquetes(
    rfc: str = Form(...),
    year: int = Form(...)
):
    temp_dir = f"/tmp/{rfc}/solicitudes/{year}"
    token_path = f"/tmp/{rfc}/token.txt"

    download_sat_packages(token_path, rfc, temp_dir)

    return {"message": "Descarga de paquetes completada"}
