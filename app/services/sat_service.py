import os
from app.utils.pem_converter import convert_to_pem
from app.services.s3_service import upload_to_s3
import subprocess
from datetime import datetime
from app.config_loader import load_config
from app.services.s3_service import read_file_from_s3, upload_to_s3
import base64
from lxml import etree
import xmlsec
import requests
from urllib.parse import unquote
from app.services.s3_service import download_from_s3, read_file_from_s3, upload_to_s3
#from app.services.mongo_service import update_package_status_in_db  

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
        
def verify_sat_requests(token_path, rfc, temp_dir):
    import os
    from app.services.s3_service import download_from_s3
    from lxml import etree
    import xmlsec
    import requests
    from urllib.parse import unquote

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

    # Cargar solicitudes
    with open(solicitud_ids_path, "r", encoding="utf-8") as f:
        solicitudes = [line.strip() for line in f if line.strip()]

    resultados = []

    paquetes_totales = set()
    
    for id_solicitud in solicitudes:
        # Generar XML
        envelope = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope", nsmap={
            "s": "http://schemas.xmlsoap.org/soap/envelope/",
            "ds": "http://www.w3.org/2000/09/xmldsig#"
        })
        body = etree.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
        verif = etree.SubElement(body, "{http://DescargaMasivaTerceros.sat.gob.mx}VerificaSolicitudDescarga")
        solicitud = etree.SubElement(verif, "{http://DescargaMasivaTerceros.sat.gob.mx}solicitud")
        solicitud.set("IdSolicitud", id_solicitud)
        solicitud.set("RfcSolicitante", rfc)

        # Firmar XML
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

        resultados.append({
            "id_solicitud": id_solicitud,
            "estado": estado,
            "codigo_estatus": cod_estatus,
            "mensaje": mensaje,
            "numero_cfdis": numero_cfdis,
            "paquetes": ids_paquetes
        })
        
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

    return resultados

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

            descargados.append(paquete_id)
            print(f"✓ Descargado y subido: {s3_zip_path}")

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