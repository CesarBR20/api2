import os
import requests
from lxml import etree
from uuid import uuid4
from datetime import datetime
from urllib.parse import unquote
import xmlsec
from app.services.mongo_service import guardar_solicitud

from app.services.s3_service import read_file_from_s3, upload_file_to_s3, download_from_s3

def solicitar_cfdi_desde_sat(rfc, inicio, fin, tipo_solicitud, tipo_comp):
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

    # Guardar id en archivo (modo append)
    with open(id_file_path, "a", encoding="utf-8") as f:
        f.write(id_solicitud + "\n")

    # Subir a S3
    s3_output_path = f"{base_s3_path}/{anio}/solicitudes/id_solicitud.txt"
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

    tipo_solicitud = tipo_solicitud.upper()
    tipo_comp = tipo_comp.upper()

    # Determinar el nodo y SOAPAction correcto según reglas del SAT
    if "folio" in tipo_solicitud.lower():
        op = "SolicitaDescargaFolio"
    elif tipo_comp == "E":  # Emitidos
        op = "SolicitaDescargaEmitidos"
    else:
        op = "SolicitaDescargaRecibidos"

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
    if tipo_solicitud in ("CFDI", "METADATA"):
        sol.set("TipoComp", tipo_comp)
        sol.set("RfcEmisor", rfc)  # si el cliente siempre es el emisor
        # puedes agregar más filtros si luego quieres: folio, rfc receptor, etc.

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


