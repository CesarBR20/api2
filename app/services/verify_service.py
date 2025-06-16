# app/services/verify_service.py

import os
from lxml import etree
import xmlsec
import requests
from urllib.parse import unquote
from datetime import datetime

def build_verificacion_xml(rfc, id_solicitud):
    NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
    NS_DESCARGA = "http://DescargaMasivaTerceros.sat.gob.mx"
    NS_DS = "http://www.w3.org/2000/09/xmldsig#"

    envelope = etree.Element("{%s}Envelope" % NS_SOAP, nsmap={
        's': NS_SOAP,
        'ds': NS_DS
    })

    header = etree.SubElement(envelope, "{%s}Header" % NS_SOAP)
    body = etree.SubElement(envelope, "{%s}Body" % NS_SOAP)

    verifica = etree.SubElement(body, "{%s}VerificaSolicitudDescarga" % NS_DESCARGA)
    solicitud = etree.SubElement(verifica, "{%s}solicitud" % NS_DESCARGA)
    solicitud.set("IdSolicitud", id_solicitud)
    solicitud.set("RfcSolicitante", rfc)

    return envelope

def sign_xml(doc, cert_path, key_path):
    solicitud_node = doc.find(".//{http://DescargaMasivaTerceros.sat.gob.mx}solicitud")
    if solicitud_node is None:
        raise Exception("No se encontró el nodo <solicitud> para firmar.")

    signature_node = xmlsec.template.create(
        solicitud_node,
        xmlsec.Transform.EXCL_C14N,
        xmlsec.Transform.RSA_SHA1,
        ns="ds"
    )

    solicitud_node.insert(0, signature_node)

    ref = xmlsec.template.add_reference(
        signature_node,
        xmlsec.Transform.SHA1,
        uri=""
    )
    xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)

    key_info = xmlsec.template.ensure_key_info(signature_node)
    xmlsec.template.add_x509_data(key_info)

    key = xmlsec.Key.from_file(key_path, xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(cert_path, xmlsec.KeyFormat.CERT_PEM)

    ctx = xmlsec.SignatureContext()
    ctx.key = key

    try:
        ctx.sign(signature_node)
    except Exception as e:
        print(f"Error durante la firma: {e}")
        raise

    return etree.tostring(doc, encoding="utf-8", xml_declaration=True, pretty_print=True)

def send_verificacion_request(xml_bytes, token):
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://DescargaMasivaTerceros.sat.gob.mx/IVerificaSolicitudDescargaService/VerificaSolicitudDescarga",
        "Authorization": f'WRAP access_token="{unquote(token)}"'
    }

    url = "https://cfdidescargamasivaconsulta.clouda.sat.gob.mx/VerificaSolicitudDescargaService.svc"

    try:
        response = requests.post(url, data=xml_bytes, headers=headers, timeout=60)
        print(f"Código de respuesta: {response.status_code}")

        if response.status_code == 200:
            print("Solicitud de verificación enviada exitosamente")
            return response.content
        else:
            print(f"✗ Error en la solicitud: {response.status_code}")
            print(response.text)
            raise Exception(f"Error HTTP {response.status_code}: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"✗ Error de conexión: {e}")
        raise

def parse_verificacion_response(xml_response):
    try:
        tree = etree.fromstring(xml_response)
        result_nodes = tree.xpath("//*[local-name()='VerificaSolicitudDescargaResult']")

        if result_nodes:
            result = result_nodes[0]
            estado = result.get("EstadoSolicitud")
            cod_estatus = result.get("CodEstatus")
            mensaje = result.get("Mensaje", "")
            numero_cfdis = result.get("NumeroCFDIs", "0")

            print(f"Estado de la solicitud: {estado}")
            print(f"Código de estatus: {cod_estatus}")
            print(f"Mensaje: {mensaje}")
            print(f"Número de CFDIs: {numero_cfdis}")

            if estado == "3":
                paquetes_nodo = tree.xpath("//*[local-name()='IdsPaquetes']")
                paquetes = []

                if paquetes_nodo:
                    texto = paquetes_nodo[0].text
                    if texto:
                        paquetes = [p.strip() for p in texto.split("|") if p.strip()]

                return {"estado": estado, "paquetes": paquetes}

            return {"estado": estado, "paquetes": []}

        print("✗ No se encontró el nodo de resultado en la respuesta")
        return None

    except Exception as e:
        print(f"✗ Error al parsear respuesta: {e}")
        return None
