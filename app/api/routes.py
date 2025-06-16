from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.sat_service import process_client_files
from app.services.sat_service import authenticate_with_sat
from app.services.sat_service import create_sat_requests
from app.services.sat_service import verify_sat_requests
from app.services.sat_service import download_sat_packages
from app.services.sat_service import convert_to_pem
from app.utils.pem_converter import convert_to_pem
from app.services.s3_service import upload_to_s3, download_from_s3, upload_token_to_s3
from app.services.auth_service import get_sat_token
from app.services.request_service import solicitar_cfdi_desde_sat
from app.services.mongo_service import existe_cliente, registrar_cliente
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
    
    if not existe_cliente(rfc):
        registrar_cliente(rfc)

    return {
        "message": "Archivos convertidos y subidos exitosamente",
        "cert_pem_s3_path": f"{rfc}/cert.pem",
        "fiel_pem_s3_path": f"{rfc}/fiel.pem",
        "password_s3_path": f"{rfc}/{password_file.filename}"
    }

@router.post("/auth-sat/")
def auth_sat(rfc: str = Form(...)):
    try:
        base_path = f"/tmp/{rfc}"
        cert_path = f"{base_path}/cert.pem"
        key_path = f"{base_path}/fiel.pem"
        password_path = f"{base_path}/password.txt"

        BUCKET_NAME = "satisfacture"

        # Descargar credenciales
        download_from_s3(BUCKET_NAME, f"clientes/{rfc}/certificados/cert.pem", cert_path)
        download_from_s3(BUCKET_NAME, f"clientes/{rfc}/certificados/fiel.pem", key_path)
        download_from_s3(BUCKET_NAME, f"clientes/{rfc}/certificados/password.txt", password_path)

        # Leer contraseña
        with open(password_path, "r", encoding="utf-8") as f:
            password = f.read().strip()

        # SAT endpoints
        endpoint_url = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/Autenticacion/Autenticacion.svc"
        endpoint_action = "http://DescargaMasivaTerceros.gob.mx/IAutenticacion/Autentica"

        # Obtener token
        token = get_sat_token(cert_path, key_path, password, endpoint_url, endpoint_action)

        # Subir token a S3
        s3_token_key = f"clientes/{rfc}/tokens/token.txt"
        upload_token_to_s3(BUCKET_NAME, s3_token_key, token)

        return {"token": token}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al autenticar con el SAT: {str(e)}")

@router.post("/solicitar-cfdi/")
async def solicitar_cfdi(
    rfc: str = Form(...),
    inicio: str = Form(...),
    fin: str = Form(...),
    tipo_solicitud: str = Form(...),
    tipo_comp: str = Form(...)
):
    try:
        id_solicitud = solicitar_cfdi_desde_sat(rfc, inicio, fin, tipo_solicitud, tipo_comp)
        return {"id_solicitud": id_solicitud}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verificar-solicitudes/")
async def verificar_solicitudes(
    rfc: str = Form(...),
    year: int = Form(...)
):
    temp_dir = f"/tmp/{rfc}/solicitudes/{year}"
    token_path = f"/tmp/{rfc}/token.txt"

    resultados = verify_sat_requests(token_path, rfc, temp_dir)

    return {
        "message": "Verificación de solicitudes completada",
        "resultados": resultados
    }

@router.post("/descargar-paquetes/")
async def descargar_paquetes(
    rfc: str = Form(...),
    year: int = Form(...)
):
    temp_dir = f"/tmp/{rfc}/{year}/paquetes"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        download_sat_packages(rfc, temp_dir)
        return {"message": "Descarga de paquetes completada"}
    except Exception as e:
        return {"error": str(e)}
