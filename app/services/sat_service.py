from app.services.mongo_service import actualizar_paquete_descargado, agregar_paquete_a_solicitud, verificar_si_completo, guardar_solicitud
from app.services.s3_service import download_from_s3, read_file_from_s3, upload_to_s3, upload_file_to_s3
from app.utils.signer import build_soap_envelope, sign_envelope
from app.utils.pem_converter import convert_to_pem
from dateutil.parser import parse as parse_date
from urllib.parse import unquote
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
from lxml import etree
from uuid import uuid4
import requests
import base64
import xmlsec
import os

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

def get_sat_token(cert_path, key_path, password, endpoint_url, endpoint_action):
    env, ts, sec, bst_id = build_soap_envelope(cert_path, key_path)
    signed = sign_envelope(env, ts, sec, key_path, cert_path, bst_id)

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": endpoint_action
    }

    xml_data = etree.tostring(signed, xml_declaration=True, encoding="utf-8")
    response = requests.post(endpoint_url, data=xml_data, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Error en autenticación: {response.status_code} - {response.text}")

    root = etree.fromstring(response.content)
    token = root.find(".//{http://DescargaMasivaTerceros.gob.mx}AutenticaResult")
    return token.text if token is not None else None

def solicitar_cfdi_desde_sat(rfc, inicio, fin, tipo_solicitud, tipo_comp, dividida_de=None):
    bucket = "satisfacture"
    base_s3_path = f"clientes/{rfc}"
    temp_dir = f"/tmp/{rfc}"
    os.makedirs(temp_dir, exist_ok=True)

    # Rutas locales temporales
    cer_path = os.path.join(temp_dir, "cert.pem")
    key_path = os.path.join(temp_dir, "fiel.pem")
    token_local_path = os.path.join(temp_dir, "token.txt")

    # Descargar archivos necesarios
    download_from_s3(bucket, f"{base_s3_path}/certificados/cert.pem", cer_path)
    download_from_s3(bucket, f"{base_s3_path}/certificados/fiel.pem", key_path)
    download_from_s3(bucket, f"{base_s3_path}/tokens/token.txt", token_local_path)

    with open(token_local_path, encoding="utf-8") as f:
        token = f.read().strip()

    # Año destino
    anio = datetime.strptime(inicio, "%Y-%m-%d").year
    solicitudes_dir = os.path.join(temp_dir, str(anio), "solicitudes")
    os.makedirs(solicitudes_dir, exist_ok=True)
    id_file_path = os.path.join(solicitudes_dir, "id_solicitud.txt")
    
    anio_path = os.path.join(temp_dir, str(anio))
    solicitudes_dir = os.path.join(anio_path, "solicitudes")
    paquetes_dir = os.path.join(anio_path, "paquetes")
    
    os.makedirs(solicitudes_dir, exist_ok=True)
    os.makedirs(paquetes_dir, exist_ok=True)

    # Construcción del XML
    solicitud_xml, soap_action = build_solicitud_xml(rfc, inicio, fin, tipo_solicitud, tipo_comp)
    signed_xml = sign_xml(solicitud_xml, cer_path, key_path)
    
    print("xml enviado: ", signed_xml.decode())
    
    response = enviar_solicitud(signed_xml, token, soap_action)
    id_solicitud = parse_id_solicitud(response)

    # Rutas
    s3_output_path = f"{base_s3_path}/{anio}/solicitudes/id_solicitud.txt"

    # Descargar archivo actual desde S3 al archivo local
    try:
        download_from_s3(bucket, s3_output_path, id_file_path)
        with open(id_file_path, "r", encoding="utf-8") as f:
            contenido_actual = set(line.strip() for line in f if line.strip())
    except Exception:
        contenido_actual = set()

    # Agregar nuevo ID si no existe
    if id_solicitud not in contenido_actual:
        contenido_actual.add(id_solicitud)

        # Guardar archivo actualizado localmente
        with open(id_file_path, "w", encoding="utf-8") as f:
            for s in sorted(contenido_actual):  # orden opcional
                f.write(s + "\n")

        # Subir archivo actualizado a S3
        upload_file_to_s3(bucket, s3_output_path, id_file_path)
    
    # Subir carpetas como .keep paa que exista aunque este vacío
    keep_paths = os.path.join(paquetes_dir, ".keep")
    with open(keep_paths, "w") as f:
        f.write("")
        
    s3_paquetes_path = f"{base_s3_path}/{anio}/paquetes/.keep"
    upload_file_to_s3(bucket, s3_paquetes_path, keep_paths)
    
    solicitud_data = {
        "rfc": rfc,
        "id_solicitud": id_solicitud,
        "tipo_solicitud": tipo_solicitud.lower(),
        "tipo_comp": tipo_comp.upper(),
        "fecha_inicio": inicio,
        "fecha_fin": fin,
        "fecha_solicitud": datetime.utcnow(),
        "estado": "pendiente",
        "paquetes": []
    }
    
    guardar_solicitud(solicitud_data)  

    return id_solicitud

def build_solicitud_xml(rfc, inicio, fin, tipo_solicitud, tipo_comp):
    NS_SOAP     = "http://schemas.xmlsoap.org/soap/envelope/"
    NS_DESCARGA = "http://DescargaMasivaTerceros.sat.gob.mx"
    NS_WSA      = "http://www.w3.org/2005/08/addressing"
    NS_DS       = "http://www.w3.org/2000/09/xmldsig#"

    tipo_comp = tipo_comp.upper()

    if tipo_solicitud.upper() == "CFDI":
        op = "SolicitaDescargaEmitidos" if tipo_comp == "E" else "SolicitaDescargaRecibidos"
    elif tipo_solicitud.lower() == "metadata":
        tipo_solicitud = "Metadata"  # Fuerza el valor correcto
        op = "SolicitaDescargaEmitidos" if tipo_comp == "E" else "SolicitaDescargaRecibidos"
    elif tipo_solicitud.upper() == "FOLIO":
        tipo_solicitud = "Folio"
        op = "SolicitaDescargaFolio"
    else:
        raise ValueError("Tipo de solicitud no reconocido.")


    soap_action = f"http://DescargaMasivaTerceros.sat.gob.mx/ISolicitaDescargaService/{op}"

    # Construcción del envelope
    env = etree.Element(f"{{{NS_SOAP}}}Envelope", nsmap={
        "s": NS_SOAP, "wsa": NS_WSA, "ds": NS_DS, "ns0": NS_DESCARGA
    })
    hdr = etree.SubElement(env, f"{{{NS_SOAP}}}Header")
    etree.SubElement(hdr, f"{{{NS_WSA}}}Action").text = soap_action
    etree.SubElement(hdr, f"{{{NS_WSA}}}To").text = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/SolicitaDescargaService.svc"
    etree.SubElement(hdr, f"{{{NS_WSA}}}MessageID").text = f"uuid:{uuid4()}"

    body = etree.SubElement(env, f"{{{NS_SOAP}}}Body")
    opnode = etree.SubElement(body, f"{{{NS_DESCARGA}}}{op}")

    sol = etree.SubElement(opnode, f"{{{NS_DESCARGA}}}solicitud", nsmap={"ds": NS_DS})
    sol.set("Id", "Solicitud")
    sol.set("RfcSolicitante", rfc)
    sol.set("FechaInicial", inicio + "T00:00:00")
    sol.set("FechaFinal",  fin + "T23:59:59")
    sol.set("TipoSolicitud", tipo_solicitud)

    # Solo CFDI o Metadata permiten filtros opcionales
    if tipo_solicitud.lower() in ("cfdi", "metadata"):
        sol.set("TipoComp", tipo_comp)
        sol.set("RfcEmisor", rfc)

    return env, soap_action


def sign_xml(doc, cert_path, key_path):
    sol = doc.find(".//solicitud") or doc.find(".//{http://DescargaMasivaTerceros.sat.gob.mx}solicitud")
    sig = xmlsec.template.create(sol, xmlsec.Transform.EXCL_C14N, xmlsec.Transform.RSA_SHA1, ns="ds")
    sol.insert(0, sig)

    ref = xmlsec.template.add_reference(sig, xmlsec.Transform.SHA1, uri="#Solicitud")
    xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
    ki = xmlsec.template.ensure_key_info(sig)
    xmlsec.template.add_x509_data(ki)

    key = xmlsec.Key.from_file(key_path, xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(cert_path, xmlsec.KeyFormat.CERT_PEM)
    ctx = xmlsec.SignatureContext(); ctx.key = key
    ctx.register_id(sol, "Id")
    ctx.sign(sig)

    return etree.tostring(doc, encoding="utf-8", xml_declaration=True)

def enviar_solicitud(xml_bytes, token, action):
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": action,
        "Authorization": f'WRAP access_token="{unquote(token)}"'
    }
    url = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/SolicitaDescargaService.svc"
    response = requests.post(url, data=xml_bytes, headers=headers, timeout=60)
    
    print ("respuesta del sat: ", response.text)

    if response.status_code != 200:
        raise Exception(f"Error HTTP {response.status_code}: {response.text}")
    return response.content

def parse_id_solicitud(xml_response):
    tree = etree.fromstring(xml_response)

    # Buscar el nodo correcto según el tipo de solicitud
    namespaces = {"ns": "http://DescargaMasivaTerceros.sat.gob.mx"}
    result = None
    for tag in [
        "SolicitaDescargaEmitidosResult",
        "SolicitaDescargaRecibidosResult",
        "SolicitaDescargaMetadataResult",
        "SolicitaDescargaResult"
    ]:
        result = tree.find(f".//ns:{tag}", namespaces)
        if result is not None:
            break

    if result is None:
        raise Exception("No se encontró un nodo de resultado válido en la respuesta del SAT.")

    cod = result.get("CodEstatus", "Sin código")
    msg = result.get("Mensaje", "Sin mensaje")

    if cod != "5000":
        raise Exception(f"Solicitud rechazada por el SAT.\nCódigo: {cod}\nMensaje: {msg}")

    return result.get("IdSolicitud")

def verify_sat_requests(token_path, rfc, temp_dir):
    
    load_dotenv()
    MONGO_URI = os.getenv("MONGO_URI")
    client = MongoClient(MONGO_URI)
    db = client["MONGO_DB_NAME"]
    solicitudes_col = db["solicitudes"]

    bucket = "satisfacture"
    year = os.path.basename(temp_dir)
    solicitud_ids_path = os.path.join(temp_dir, "id_solicitud.txt")
    cer_path = os.path.join(f"/tmp/{rfc}", "cert.pem")
    key_path = os.path.join(f"/tmp/{rfc}", "fiel.pem")

    # Descargar archivos necesarios desde S3
    download_from_s3(bucket, f"clientes/{rfc}/certificados/cert.pem", cer_path)
    download_from_s3(bucket, f"clientes/{rfc}/certificados/fiel.pem", key_path)
    download_from_s3(bucket, f"clientes/{rfc}/tokens/token.txt", token_path)
    download_from_s3(bucket, f"clientes/{rfc}/{year}/solicitudes/id_solicitud.txt", solicitud_ids_path)

    with open(token_path, encoding="utf-8") as f:
        token = f.read().strip()

    with open(solicitud_ids_path, "r", encoding="utf-8") as f:
        solicitudes = [line.strip() for line in f if line.strip()]

    resultados = []
    mensajes_estancados = []
    paquetes_totales = set()

    for id_solicitud in solicitudes:
        try:
            # Construcción del XML
            envelope = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope", nsmap={
                "s": "http://schemas.xmlsoap.org/soap/envelope/",
                "ds": "http://www.w3.org/2000/09/xmldsig#"
            })
            body = etree.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
            verif = etree.SubElement(body, "{http://DescargaMasivaTerceros.sat.gob.mx}VerificaSolicitudDescarga")
            solicitud = etree.SubElement(verif, "{http://DescargaMasivaTerceros.sat.gob.mx}solicitud")
            solicitud.set("IdSolicitud", id_solicitud)
            solicitud.set("RfcSolicitante", rfc)

            # Firma del XML
            sig = xmlsec.template.create(solicitud, xmlsec.Transform.EXCL_C14N, xmlsec.Transform.RSA_SHA1, ns="ds")
            solicitud.insert(0, sig)
            ref = xmlsec.template.add_reference(sig, xmlsec.Transform.SHA1)
            xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
            ki = xmlsec.template.ensure_key_info(sig)
            xmlsec.template.add_x509_data(ki)
            key = xmlsec.Key.from_file(key_path, xmlsec.KeyFormat.PEM)
            key.load_cert_from_file(cer_path, xmlsec.KeyFormat.CERT_PEM)
            ctx = xmlsec.SignatureContext()
            ctx.key = key
            ctx.sign(sig)

            xml_firmado = etree.tostring(envelope, encoding="utf-8", xml_declaration=True)

            # Enviar al SAT
            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "http://DescargaMasivaTerceros.sat.gob.mx/IVerificaSolicitudDescargaService/VerificaSolicitudDescarga",
                "Authorization": f'WRAP access_token="{unquote(token)}"'
            }
            url = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/VerificaSolicitudDescargaService.svc"
            response = requests.post(url, data=xml_firmado, headers=headers, timeout=60)

            # Parsear respuesta
            tree = etree.fromstring(response.content)
            result = tree.find(".//{http://DescargaMasivaTerceros.sat.gob.mx}VerificaSolicitudDescargaResult")
            estado = result.get("EstadoSolicitud", "Desconocido")
            cod_estatus = result.get("CodEstatus", "")
            mensaje = result.get("Mensaje", "")
            numero_cfdis = result.get("NumeroCFDIs", "")
            ids_paquetes = []

            nodo_paquetes = tree.find(".//{http://DescargaMasivaTerceros.sat.gob.mx}IdsPaquetes")
            if nodo_paquetes is not None and nodo_paquetes.text:
                ids_paquetes = [p for p in nodo_paquetes.text.strip().split("|") if p]

            if estado == "3":
                paquetes_totales.update(ids_paquetes)

            # Verificación de estancamiento
            if estado == "1":
                doc = solicitudes_col.find_one({"id_solicitud": id_solicitud})
                if doc:
                    fecha_solicitud = doc.get("fecha_solicitud")
                    if fecha_solicitud:
                        try:
                            if isinstance(fecha_solicitud, str):
                                fecha_solicitud = parse_date(fecha_solicitud)
                            
                            if isinstance(fecha_solicitud, datetime):
                                dias = (datetime.utcnow() - fecha_solicitud).days
                                if dias >= 4:
                                    advertencia = (
                                        f"La solicitud {id_solicitud} se encuentra en estado '1' tras {dias} días, "
                                        f"Se recomienda repetri la solicitud con los mismos parámetros."
                                    )
                                    
                                    print(advertencia)
                                    mensajes_estancados.append(advertencia)
                        except Exception as e:
                            print(f"No se pudo procesar la solicitud de {id_solicitud}: {e}")

            resultados.append({
                "id_solicitud": id_solicitud,
                "estado": estado,
                "codigo_estatus": cod_estatus,
                "mensaje": mensaje,
                "numero_cfdis": numero_cfdis,
                "paquetes": ids_paquetes
            })

        except Exception as e:
            print(f"Error procesando {id_solicitud}: {e}")

    # Guardar paquetes en S3
    if paquetes_totales:
        paquetes_path = os.path.join(temp_dir, "paquetes.txt")
        s3_paquetes_path = f"clientes/{rfc}/{year}/solicitudes/paquetes.txt"

        try:
            contenido_actual = read_file_from_s3(bucket, s3_paquetes_path).decode("utf-8").splitlines()
        except Exception:
            contenido_actual = []

        paquetes_finales = set(contenido_actual).union(paquetes_totales)

        with open(paquetes_path, "w", encoding="utf-8") as f:
            for paquete in paquetes_finales:
                f.write(paquete + "\n")

        upload_to_s3(paquetes_path, bucket, s3_paquetes_path)

    return {
        "message": "Verificación completada",
        "resultados": resultados,
        "mensajes_estancados": mensajes_estancados
    }

def download_sat_packages(rfc: str, temp_dir: str):
    year = os.path.basename(os.path.dirname(temp_dir))
    bucket = "satisfacture"

    # Preparar paths locales
    cert_path = os.path.join(f"/tmp/{rfc}", "cert.pem")
    key_path = os.path.join(f"/tmp/{rfc}", "fiel.pem")
    password_path = os.path.join(f"/tmp/{rfc}", "password.txt")
    token_path = os.path.join(f"/tmp/{rfc}", "token.txt")
    paquetes_path = os.path.join(temp_dir, "paquetes.txt")
    id_solicitud_path = os.path.join(temp_dir, "id_solicitud.txt")

    os.makedirs(temp_dir, exist_ok=True)

    # Descargar archivos necesarios desde S3
    download_from_s3(bucket, f"clientes/{rfc}/certificados/cert.pem", cert_path)
    download_from_s3(bucket, f"clientes/{rfc}/certificados/fiel.pem", key_path)
    download_from_s3(bucket, f"clientes/{rfc}/certificados/password.txt", password_path)
    download_from_s3(bucket, f"clientes/{rfc}/tokens/token.txt", token_path)
    download_from_s3(bucket, f"clientes/{rfc}/{year}/solicitudes/paquetes.txt", paquetes_path)
    download_from_s3(bucket, f"clientes/{rfc}/{year}/solicitudes/id_solicitud.txt", id_solicitud_path)

    # Leer token
    with open(token_path, "r", encoding="utf-8") as f:
        token = f.read().strip()

    # Leer lista de paquetes
    with open(paquetes_path, "r", encoding="utf-8") as f:
        paquetes = [line.strip() for line in f if line.strip()]

    if not paquetes:
        print("No hay paquetes por descargar.")
        return

    pendientes = []
    descargados = []

    for paquete_id in paquetes:
        try:
            # Crear XML de descarga
            NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
            NS_DES = "http://DescargaMasivaTerceros.sat.gob.mx"
            NS_DS = "http://www.w3.org/2000/09/xmldsig#"

            envelope = etree.Element("{%s}Envelope" % NS_SOAP, nsmap={'s': NS_SOAP, 'des': NS_DES, 'ds': NS_DS})
            body = etree.SubElement(envelope, "{%s}Body" % NS_SOAP)
            entrada = etree.SubElement(body, "{%s}PeticionDescargaMasivaTercerosEntrada" % NS_DES)
            pet = etree.SubElement(entrada, "{%s}peticionDescarga" % NS_DES, Id="_0", RfcSolicitante=rfc, IdPaquete=paquete_id)

            # Firmar XML
            sig = xmlsec.template.create(pet, xmlsec.Transform.EXCL_C14N, xmlsec.Transform.RSA_SHA1, ns="ds")
            pet.insert(0, sig)
            ref = xmlsec.template.add_reference(sig, xmlsec.Transform.SHA1, uri="#_0")
            xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
            ki = xmlsec.template.ensure_key_info(sig)
            xmlsec.template.add_x509_data(ki)

            key = xmlsec.Key.from_file(key_path, xmlsec.KeyFormat.PEM)
            key.load_cert_from_file(cert_path, xmlsec.KeyFormat.CERT_PEM)
            ctx = xmlsec.SignatureContext()
            ctx.key = key
            ctx.register_id(pet, "Id")
            ctx.sign(sig)

            xml_bytes = etree.tostring(envelope, encoding="utf-8", xml_declaration=True)

            # Enviar solicitud al SAT
            headers = {
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "http://DescargaMasivaTerceros.sat.gob.mx/IDescargaMasivaTercerosService/Descargar",
                "Authorization": f'WRAP access_token="{unquote(token)}"'
            }
            url = "https://cfdidescargamasiva.clouda.sat.gob.mx/DescargaMasivaService.svc"
            response = requests.post(url, data=xml_bytes, headers=headers, timeout=90)
            response.raise_for_status()

            # Parsear respuesta
            tree = etree.fromstring(response.content)
            cod = tree.xpath("//*[local-name()='respuesta']/@CodEstatus")
            msg = tree.xpath("//*[local-name()='respuesta']/@Mensaje")
            b64 = tree.xpath("//*[local-name()='Paquete']/text()")

            if not cod or cod[0] != "5000":
                raise RuntimeError(f"SAT devolvió {cod}:{msg}")
            if not b64 or not b64[0].strip():
                raise RuntimeError("Paquete vacío o no disponible")

            raw_zip = base64.b64decode(b64[0])
            tipo = "metadata" if "M" in paquete_id.upper() else "cfdi"
            s3_zip_path = f"clientes/{rfc}/{year}/paquetes/{tipo}/{paquete_id}.zip"

            # Guardar ZIP local y subir a S3
            local_zip = os.path.join(temp_dir, f"{paquete_id}.zip")
            with open(local_zip, "wb") as f:
                f.write(raw_zip)
            upload_to_s3(local_zip, bucket, s3_zip_path)
            
            id_solicitud = paquete_id.split("_")[0].lower()
            
            # actualizar paquete en db
            agregar_paquete_a_solicitud(rfc,  id_solicitud, paquete_id)
            actualizar_paquete_descargado(rfc, id_solicitud, "descargado")

            descargados.append(paquete_id)
            print(f"✓ Descargado y subido: {s3_zip_path}")
            
            verificar_si_completo(rfc, id_solicitud, descargados)

        except Exception as e:
            print(f"✗ Error al descargar {paquete_id}: {e}")
            pendientes.append(paquete_id)

    # Actualizar paquetes.txt (solo los que no se pudieron descargar)
    with open(paquetes_path, "w", encoding="utf-8") as f:
        for p in pendientes:
            f.write(p + "\n")
    upload_to_s3(paquetes_path, bucket, f"clientes/{rfc}/{year}/solicitudes/paquetes.txt")

    # Limpiar id_solicitud.txt de los descargados
    try:
        with open(id_solicitud_path, "r", encoding="utf-8") as f:
            todas = [line.strip() for line in f if line.strip()]

        ids_descargados = set(p.split("_")[0].lower() for p in descargados)
        nuevas = [s for s in todas if s.lower() not in ids_descargados]

        with open(id_solicitud_path, "w", encoding="utf-8") as f:
            for s in nuevas:
                f.write(s + "\n")

        upload_to_s3(id_solicitud_path, bucket, f"clientes/{rfc}/{year}/solicitudes/id_solicitud.txt")
        print("✓ id_solicitud.txt actualizado, eliminadas las solicitudes descargadas")

    except Exception as e:
        print(f"(⚠) Error al limpiar id_solicitud.txt: {e}")