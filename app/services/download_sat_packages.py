import os
import base64
from lxml import etree
import xmlsec
import requests
from urllib.parse import unquote
from app.services.s3_service import download_from_s3, read_file_from_s3, upload_to_s3
# from app.services.mongo_service import update_package_status_in_db  # si luego activas Mongo
from datetime import datetime

def download_sat_packages(rfc: str, temp_dir: str):
    year = os.path.basename(os.path.dirname(temp_dir))
    bucket = "satisfacture"

    # Preparar paths locales
    cert_path = os.path.join(f"/tmp/{rfc}", "cert.pem")
    key_path = os.path.join(f"/tmp/{rfc}", "fiel.pem")
    password_path = os.path.join(f"/tmp/{rfc}", "password.txt")
    token_path = os.path.join(f"/tmp/{rfc}", "token.txt")
    paquetes_path = os.path.join(temp_dir, "paquetes.txt")

    os.makedirs(temp_dir, exist_ok=True)

    # Descargar archivos necesarios desde S3
    download_from_s3(bucket, f"clientes/{rfc}/certificados/cert.pem", cert_path)
    download_from_s3(bucket, f"clientes/{rfc}/certificados/fiel.pem", key_path)
    download_from_s3(bucket, f"clientes/{rfc}/certificados/password.txt", password_path)
    download_from_s3(bucket, f"clientes/{rfc}/tokens/token.txt", token_path)
    download_from_s3(bucket, f"clientes/{rfc}/{year}/solicitudes/paquetes.txt", paquetes_path)

    # Leer token
    with open(token_path, "r", encoding="utf-8") as f:
        token = f.read().strip()

    # Leer lista de paquetes
    with open(paquetes_path, "r", encoding="utf-8") as f:
        paquetes = [line.strip() for line in f if line.strip()]

    if not paquetes:
        print("No hay paquetes por descargar.")
        return

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
            url = "https://cfdidescargamasivaconsulta.clouda.sat.gob.mx/DescargaMasivaTercerosService.svc"
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

            # update_package_status_in_db(rfc, int(year), paquete_id, tipo)  # si activas Mongo

            print(f"✓ Descargado y subido: {s3_zip_path}")

        except Exception as e:
            print(f"✗ Error al descargar {paquete_id}: {e}")
