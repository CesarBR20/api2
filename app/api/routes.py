from app.services.sat_service import download_sat_packages, get_sat_token, solicitar_cfdi_desde_sat, verify_sat_requests
from app.services.s3_service import upload_to_s3, download_from_s3, upload_token_to_s3
from app.services.mongo_service import existe_cliente, registrar_cliente
from app.services.cfdi_processing_service import procesar_cfdi_completo
from app.services.mongo_service import obtener_coleccion_solicitudes
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.sat_service import convert_to_pem
from app.utils.pem_converter import convert_to_pem
from datetime import date, datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from zoneinfo import ZoneInfo
from typing import Optional
import requests
import calendar
import logging
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


ALLOWED_TIPOS = {"I","E","T","N","P"}  # Ingreso, Egreso, Traslado, Nómina, Pago


@router.post("/solicitar-cfdi/")
async def solicitar_cfdi(
    rfc: str = Form(...),
    inicio: str = Form(...),                      # "YYYY-MM-DD"
    fin: str = Form(...),                         # "YYYY-MM-DD"
    tipo_solicitud: str = Form(...),              # "CFDI" | "Metadata"
    tipo_comp: str = Form(...),                   # "E" (Emitidos) | "R" (Recibidos)
    tipo_cfdi: Optional[str] = Form(None),        # "I"|"E"|"T"|"N"|"P"|"ALL"
    tipos_cfdi: Optional[str] = Form(None),       # CSV: "I,E,T,N,P"
    dividida_de: Optional[str] = Form(None),
    estado: Optional[str] = Form("ALL")           # "ALL" (no enviar) | "Vigente" | "Cancelado" | ...
):
    try:
        coleccion = obtener_coleccion_solicitudes()

        # --- validaciones de fechas ---
        try:
            _ini = datetime.strptime(inicio, "%Y-%m-%d").date()
            _fin = datetime.strptime(fin, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usa YYYY-MM-DD.")
        if _ini > _fin:
            raise HTTPException(status_code=400, detail="La fecha 'inicio' no puede ser mayor que 'fin'.")

        # (Opcional, pero recomendado) límite de ejercicios: últimos 5 + actual
        hoy_y = date.today().year
        if not ((hoy_y - 5) <= _ini.year <= hoy_y and (hoy_y - 5) <= _fin.year <= hoy_y):
            raise HTTPException(status_code=400, detail="Rango fuera de los ejercicios permitidos (últimos 5 + el actual).")

        # --- normaliza lista de tipos (solo CFDI) ---
        if (tipo_solicitud or "").upper() == "METADATA":
            tipos_lista = [None]  # Metadata no se divide por TipoComprobante
        else:
            if tipos_cfdi and tipos_cfdi.strip():
                tipos_lista = [t.strip().upper() for t in tipos_cfdi.split(",") if t.strip()]
            elif tipo_cfdi and tipo_cfdi.strip():
                tipos_lista = [tipo_cfdi.strip().upper()]
            else:
                tipos_lista = [None]  # ALL => no enviar TipoComprobante

            # "ALL" => None
            tipos_lista = [None if t == "ALL" else t for t in tipos_lista]
            for t in tipos_lista:
                if t is not None and t not in ALLOWED_TIPOS:
                    raise HTTPException(status_code=400, detail=f"tipo_cfdi inválido: {t}")

        # --- normaliza estado (solo CFDI) ---
        estado_norm = (estado or "ALL").strip()
        req_estado_cfdi = None if estado_norm.upper() == "ALL" else estado_norm  # None => no enviar atributo

        # Estado "efectivo" para la solicitud (v1.5 recomienda Vigente para CFDI)
        estado_cfdi_efectivo = req_estado_cfdi
        if (tipo_solicitud or "").upper() == "CFDI" and req_estado_cfdi is None:
            estado_cfdi_efectivo = "Vigente"

        # Regla v1.5: CFDI Recibidos Cancelados NO se entregan en XML (usar Metadata)
        if ((tipo_solicitud or "").upper() == "CFDI"
            and (tipo_comp or "").upper() == "R"
            and (estado_cfdi_efectivo or "").lower() == "cancelado"):
            raise HTTPException(
                status_code=400,
                detail="SAT v1.5: CFDI Recibidos 'Cancelado' no se entregan en XML. Solicita Metadata para cancelados."
            )

        resultados = []

        for t in tipos_lista:
            # --- filtro de dedupe (coincide con cómo guardas en Mongo) ---
            filtro = {
                "rfc": rfc.upper(),
                "tipo_solicitud": (tipo_solicitud or "").lower(),
                "tipo_comp": (tipo_comp or "").upper(),
                "fecha_inicio": inicio,
                "fecha_fin": fin,
            }

            if (tipo_solicitud or "").upper() == "CFDI":
                # Estado efectivo
                if estado_cfdi_efectivo is None:
                    filtro = {
                        **filtro,
                        "$or": [
                            {"estado_cfdi": {"$exists": False}},
                            {"estado_cfdi": None},
                            {"estado_cfdi": "ALL"},
                        ],
                    }
                else:
                    filtro["estado_cfdi"] = estado_cfdi_efectivo

            # Dimensión por tipo_cfdi (tu guardar_solicitud usa None si ALL)
            if t is None:
                # coincide con docs sin campo/None
                filtro.setdefault("$or", [])
                filtro["$or"] += [
                    {"tipo_cfdi": {"$exists": False}},
                    {"tipo_cfdi": None},
                ]
            else:
                filtro["tipo_cfdi"] = t

            existente = coleccion.find_one(filtro)
            if existente:
                estado_doc = existente.get("estado")
                id_existente = existente.get("id_solicitud")
                fecha_solicitud = existente.get("fecha_solicitud")

                if estado_doc == "descargado":
                    msg = f"La solicitud {id_existente} ya fue realizada y descargada."
                elif estado_doc in ("pendiente", "1"):
                    msg = f"La solicitud {id_existente} ya existe y está en proceso (estado: {estado_doc})."
                else:
                    msg = f"La solicitud {id_existente} ya existe (estado: {estado_doc})."

                if estado_doc == "1" and isinstance(fecha_solicitud, datetime):
                    dias = (datetime.utcnow() - fecha_solicitud).days
                    msg += f" Han pasado {dias} día(s) desde su envío."

                resultados.append({
                    "tipo_cfdi": t or "ALL",
                    "status": "existente" if estado_doc in ("pendiente","descargado") else "en_proceso",
                    "estado": estado_doc,
                    "id_solicitud": id_existente,
                    "message": msg
                })
                continue

            # --- dispara nueva solicitud ---
            try:
                new_id = solicitar_cfdi_desde_sat(
                    rfc=rfc,
                    inicio=inicio,
                    fin=fin,
                    tipo_solicitud=tipo_solicitud,
                    tipo_comp=tipo_comp,
                    tipo_cfdi=t,                     # I/E/T/N/P o None (ALL)
                    dividida_de=dividida_de,
                    estado_cfdi=estado_cfdi_efectivo, # ← usar SIEMPRE el estado efectivo
                    max_retries_5002=3
                )
                resultados.append({
                    "tipo_cfdi": t or "ALL",
                    "status": "nueva",
                    "id_solicitud": new_id,
                    "message": f"Solicitud creada: {new_id}"
                })
            except Exception as e:
                resultados.append({
                    "tipo_cfdi": t or "ALL",
                    "status": "error",
                    "error": str(e)
                })

        return {"count": len(resultados), "resultados": resultados}

    except HTTPException:
        raise
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


def _ultimo_dia_mes(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]
    
def _extract_result_items(resp_json: dict):
    """Normaliza la respuesta de /solicitar-cfdi/ a una lista de items con id/status."""
    if not isinstance(resp_json, dict):
        return []
    if "resultados" in resp_json and isinstance(resp_json["resultados"], list):
        return resp_json["resultados"]
    if "id_solicitud" in resp_json:
        return [{"status": "nueva", "id_solicitud": resp_json["id_solicitud"], "tipo_cfdi": "ALL"}]
    return []

from zoneinfo import ZoneInfo
from datetime import date, datetime
import time

@router.post("/ejecutar-solicitudes-iniciales/")
def ejecutar_solicitudes_iniciales(
    rfc: str = Form(...),
    year: int = Form(...),
    sentidos: str = Form("ambos"),
    tipos: str = Form("ALL")
):
    import time

    llamadas = 0
    detalle = []
    requeue = []

    def _ultimo_dia_mes(y: int, m: int) -> int:
        import calendar
        return calendar.monthrange(y, m)[1]

    # --- helpers de token/llamadas ---
    token_issued = 0.0

    def _auth():
        nonlocal token_issued
        res = requests.post("http://localhost:8000/auth-sat/", data={"rfc": rfc}, timeout=30)
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="Error autenticando ante el SAT")
        token_issued = time.time()

    def _needs_refresh():
        # refresca ~1 min antes del vencimiento (token ~5m)
        return (time.time() - token_issued) > 240  # 4 minutos

    def _post_solicitar(body, etiqueta):
        nonlocal llamadas, detalle, requeue
        # refresh por tiempo
        if _needs_refresh():
            _auth()

        res = requests.post("http://localhost:8000/solicitar-cfdi/", data=body, timeout=90)
        llamadas += 1

        def _append_ok(items, tag):
            detalle.append({**tag, "resultado": "OK", "resultados": items})

        def _append_err(text, status, tag):
            detalle.append({**tag, "resultado": f"ERROR {status}", "detalle": text})

        # HTTP error → requeue
        if res.status_code != 200:
            _append_err(res.text, res.status_code, etiqueta)
            requeue.append((body, {**etiqueta, "requeue_motivo": f"HTTP_{res.status_code}"}))
            return

        data = res.json()
        items = _extract_result_items(data)

        # ¿falló por token inválido? (re-auth + 1 retry inmediato)
        token_err = any(
            isinstance(it, dict) and it.get("status") == "error" and
            isinstance(it.get("error"), str) and "Token invalido" in it["error"]
            for it in items
        )
        if token_err:
            _auth()
            res2 = requests.post("http://localhost:8000/solicitar-cfdi/", data=body, timeout=90)
            llamadas += 1
            if res2.status_code != 200:
                _append_err(res2.text, res2.status_code, {**etiqueta, "retry": "token"})
                requeue.append((body, {**etiqueta, "requeue_motivo": "token_http"}))
                return
            data2 = res2.json()
            items2 = _extract_result_items(data2)
            # si aún hay algún item con error → lo dejamos marcado y lo mandamos a requeue
            still_err = any(isinstance(it, dict) and it.get("status") == "error" for it in items2)
            if still_err:
                _append_ok(items2, {**etiqueta, "retry": "token"})
                requeue.append((body, {**etiqueta, "requeue_motivo": "token_items"}))
                return
            _append_ok(items2, {**etiqueta, "retry": "token"})
            return

        # ¿otros errores en items? (p.ej. 404, “Error no controlado”, etc.)
        other_err = [it for it in items if isinstance(it, dict) and it.get("status") == "error"]
        if other_err:
            _append_ok(items, etiqueta)  # registramos tal cual para auditoría
            requeue.append((body, {**etiqueta, "requeue_motivo": "items_error"}))
            return

        _append_ok(items, etiqueta)

    try:
        # 1) primer auth
        _auth()

        tz = ZoneInfo("America/Merida")
        hoy = datetime.now(tz).date()
        Y = int(year); Ym1 = Y - 1; Yp1 = Y + 1

        # --- periodos Metadata (semestres + Q1 de Y+1) ---
        meta_periodos = [
            (date(Ym1, 1, 1), date(Ym1, 6, 30)),
            (date(Ym1, 7, 1), date(Ym1, 12, 31)),
        ]
        if hoy.year > Y:
            meta_periodos += [(date(Y, 1, 1), date(Y, 6, 30)), (date(Y, 7, 1), date(Y, 12, 31))]
        elif hoy.year == Y:
            meta_periodos += [(date(Y, 1, 1), date(Y, 6, 30)), (date(Y, 7, 1), hoy)]
        if hoy >= date(Yp1, 1, 1):
            fin_meta_y1 = min(hoy, date(Yp1, 3, 31))
            if date(Yp1, 1, 1) <= fin_meta_y1:
                meta_periodos.append((date(Yp1, 1, 1), fin_meta_y1))

        # --- periodos CFDI (mensuales) ---
        def months_of(y: int, m_from: int, m_to: int):
            for m in range(m_from, m_to + 1):
                ini = date(y, m, 1)
                fin = date(y, m, _ultimo_dia_mes(y, m))
                yield ini, fin

        cfdi_periodos = list(months_of(Ym1, 1, 12))
        if hoy.year > Y:
            cfdi_periodos += list(months_of(Y, 1, 12))
        elif hoy.year == Y:
            cfdi_periodos += [(date(Y, m, 1), min(date(Y, m, _ultimo_dia_mes(Y, m)), hoy)) for m in range(1, hoy.month + 1)]
        if hoy >= date(Yp1, 1, 1):
            m_end = min(3, hoy.month if hoy.year == Yp1 else 3)
            cfdi_periodos += list(months_of(Yp1, 1, m_end))

        # --- sentidos ---
        s = (sentidos or "").lower()
        direcciones = []
        if s in ("emitidos", "ambos"): direcciones.append("E")
        if s in ("recibidos", "ambos"): direcciones.append("R")
        if not direcciones:
            direcciones = ["E"]

        # --- tipos ---
        tipos_norm = (tipos or "ALL").strip().upper()
        tipos_csv = None if tipos_norm == "ALL" else ",".join([t for t in [x.strip().upper() for x in tipos_norm.split(",")] if t])

        # === METADATA por periodo y dirección ===
        for ini, fin in meta_periodos:
            for d in direcciones:
                body = {
                    "rfc": rfc,
                    "inicio": str(ini),
                    "fin": str(fin),
                    "tipo_solicitud": "Metadata",
                    "tipo_comp": d
                }
                etiqueta = {"tipo": f"Metadata ({'Emitidos' if d=='E' else 'Recibidos'})",
                            "inicio": str(ini), "fin": str(fin)}
                _post_solicitar(body, etiqueta)

        # === CFDI por mes × dirección (y tipos si aplica) ===
        for ini, fin in cfdi_periodos:
            for d in direcciones:
                body = {
                    "rfc": rfc,
                    "inicio": str(ini),
                    "fin": str(fin),
                    "tipo_solicitud": "CFDI",
                    "tipo_comp": d,
                    "estado": "Vigente",      # <-- clave para evitar el 301
                }
                if tipos_csv:
                    body["tipos_cfdi"] = tipos_csv
                etiqueta = {"tipo": f"CFDI ({'Emitidos' if d=='E' else 'Recibidos'})",
                            "inicio": str(ini), "fin": str(fin), "tipos": tipos_norm}
                _post_solicitar(body, etiqueta)

        # === SEGUNDA PASADA (REQUEUE) ===
        if requeue:
            _auth()  # token fresco antes del requeue
            segunda = []
            for body, tag in requeue:
                _post_solicitar(body, {**tag, "requeue": True})
                segunda.append(tag)
            detalle.append({"tipo": "REQUEUE", "conteo": len(segunda), "items": segunda})

        return {"status": "ok", "llamadas": llamadas, "detalle": detalle}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


logger = logging.getLogger(__name__)

@router.post("/verificar-solicitudes-automatico/")
async def verificar_solicitudes_automatico(rfc: str = Form(...)):
    """
    Verifica solicitudes para todos los años disponibles en S3.
    """
    import boto3
    from datetime import datetime
    
    try:
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = "satisfacture"
        
        # 1. Listar carpetas de años
        prefix = f"clientes/{rfc}/"
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
        
        years = []
        if 'CommonPrefixes' in response:
            for obj in response['CommonPrefixes']:
                folder = obj['Prefix'].replace(prefix, '').strip('/')
                if folder.isdigit() and 2020 <= int(folder) <= 2030:
                    years.append(int(folder))
        
        if not years:
            return {"message": f"No se encontraron años para {rfc}", "resultados": []}
        
        years.sort()
        
        # 2. Procesar cada año
        resultados_globales = []
        
        for year in years:
            try:
                # Usar la función existente
                temp_dir = f"/tmp/{rfc}/solicitudes/{year}"
                token_path = f"/tmp/{rfc}/token.txt"
                
                resultado = verify_sat_requests(token_path, rfc, temp_dir)
                
                resultados_globales.append({
                    "year": year,
                    "verificacion": resultado
                })
                
            except Exception as e:
                logger.error(f"Error verificando año {year} para {rfc}: {str(e)}")
                resultados_globales.append({
                    "year": year,
                    "error": str(e)
                })
        
        return {
            "rfc": rfc,
            "years_procesados": years,
            "resultados": resultados_globales
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

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