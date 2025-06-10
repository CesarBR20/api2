from fastapi import APIRouter, UploadFile, File, Form
from app.services.sat_service import process_client_files
from app.services.sat_service import authenticate_with_sat
from app.services.sat_service import create_sat_requests
from app.services.sat_service import verify_sat_requests
from app.services.sat_service import download_sat_packages
from app.services.sat_service import convert_to_pem
from app.utils.pem_converter import convert_to_pem
from app.services.s3_service import upload_to_s3
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
    upload_to_s3(cert_pem_path, bucket_name, f"{rfc}/cert.pem")
    upload_to_s3(fiel_pem_path, bucket_name, f"{rfc}/fiel.pem")

    return {
        "message": "Archivos convertidos y subidos exitosamente",
        "cert_pem_s3_path": f"{rfc}/cert.pem",
        "fiel_pem_s3_path": f"{rfc}/fiel.pem"
    }

@router.post("/upload-certificates/")
async def upload_certificates(
    cer_file: UploadFile = File(...),
    key_file: UploadFile = File(...),
    password: str = Form(...),
    rfc: str = Form(...)
):
    result = await process_client_files(cer_file, key_file, password, rfc)
    return {"message": "Archivos procesados exitosamente", "details": result}

@router.post("/auth-sat/")
async def auth_sat(
    rfc: str = Form(...),
    password: str = Form(...)
):
    temp_dir = f"/tmp/{rfc}"
    cert_pem_path = f"{temp_dir}/cert.pem"
    key_pem_path = f"{temp_dir}/key.pem"

    token_path = authenticate_with_sat(cert_pem_path, key_pem_path, password, temp_dir)

    return {"message": "Autenticación exitosa", "token_path": token_path}

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
