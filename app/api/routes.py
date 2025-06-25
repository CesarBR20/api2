from app.services.sat_service import download_sat_packages, get_sat_token, solicitar_cfdi_desde_sat, verify_sat_requests
from app.services.s3_service import upload_to_s3, download_from_s3, upload_token_to_s3
from app.services.mongo_service import existe_cliente, registrar_cliente
from app.services.cfdi_processing_service import procesar_cfdi_completo
from app.services.mongo_service import obtener_coleccion_solicitudes
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.sat_service import convert_to_pem
from app.utils.pem_converter import convert_to_pem
from datetime import date, timedelta, datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import requests
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
    tipo_comp: str = Form(...),
    dividida_de: Optional[str] = Form(None)
):
    try:
        coleccion = obtener_coleccion_solicitudes()
        filtro = {
            "rfc": rfc.upper(),
            "tipo_solicitud": tipo_solicitud.lower(),
            "tipo_comp": tipo_comp.upper(),
            "fecha_inicio": inicio,
            "fecha_fin": fin
        }

        solicitud_existente = coleccion.find_one(filtro)

        if solicitud_existente:
            estado = solicitud_existente.get("estado")
            fecha_solicitud = solicitud_existente.get("fecha_solicitud")

            if estado in ("pendiente", "descargado"):
                raise HTTPException(
                    status_code=400,
                    detail="Ya existe una solicitud con los mismos parámetros."
                )

            if estado == "1":
                if isinstance(fecha_solicitud, datetime):
                    dias = (datetime.utcnow() - fecha_solicitud).days
                    if dias < 4:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Solicitud previa aún activa (estado 1, {dias} días). Espera o reintenta después."
                        )

        # Si no hay conflicto, lanzar la nueva solicitud
        id_solicitud = solicitar_cfdi_desde_sat(
            rfc=rfc,
            inicio=inicio,
            fin=fin,
            tipo_solicitud=tipo_solicitud,
            tipo_comp=tipo_comp,
            dividida_de=dividida_de
        )
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

    resultado = verify_sat_requests(token_path, rfc, temp_dir)

    return resultado

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

@router.post("/ejecutar-solicitudes-iniciales/")
def ejecutar_solicitudes_iniciales(rfc: str = Form(...), year: int = Form(...)):
    try:
        auth_res = requests.post("http://localhost:8000/auth-sat/", data={"rfc": rfc})
        if auth_res.status_code != 200:
            raise HTTPException(status_code=500, detail="Error autenticando ante el SAT")
        token = auth_res.json().get("token")

        headers = {"Authorization": f"Bearer {token}"}
        solicitudes = []

        # Metadata: 2 semestres
        metadata_periodos = [
            (f"{year}-01-01", f"{year}-06-30"),
            (f"{year}-07-01", f"{year}-12-31")
        ]

        for inicio, fin in metadata_periodos:
            body = {
                "rfc": rfc,
                "inicio": inicio,
                "fin": fin,
                "tipo_solicitud": "Metadata",
                "tipo_comp": "E"
            }
            res = requests.post("http://localhost:8000/solicitar-cfdi/", headers=headers, data=body)
            if res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail=res.text)
            solicitudes.append(res.json())

        # CFDI: 12 meses
        for mes in range(1, 13):
            inicio = date(year, mes, 1)
            if mes == 12:
                fin = date(year, 12, 31)
            else:
                fin = date(year, mes + 1, 1) - timedelta(days=1)

            body = {
                "rfc": rfc,
                "inicio": str(inicio),
                "fin": str(fin),
                "tipo_solicitud": "CFDI",
                "tipo_comp": "E"
            }
            res = requests.post("http://localhost:8000/solicitar-cfdi/", headers=headers, data=body)
            if res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail=res.text)
            solicitudes.append(res.json())

        return {"status": "ok", "solicitudes_generadas": len(solicitudes)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
class ProcesarCFDIRequest(BaseModel):
    cliente_rfc: str
    bucket_name: str
    prefix: str

@router.post("/procesar-cfdi/")
async def procesar_cfdi(request: ProcesarCFDIRequest):
    try:
        procesar_cfdi_completo(
            cliente_rfc=request.cliente_rfc,
            bucket_name=request.bucket_name,
            prefix=request.prefix
        )
        return {"detail": "Procesamiento finalizado correctamente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))