#verify.py - Verificación
import yaml, string, os
import requests
from lxml import etree
import xmlsec
from urllib.parse import unquote
from datetime import datetime


def load_config():
    with open("config.yml", encoding="utf-8") as f:
        raw = f.read()
        prelim = yaml.safe_load(raw)
        vars_dict = {
            "cliente_rfc": prelim["cliente_rfc"],
            "base_path": f"clientes/{prelim['cliente_rfc']}"
        }
        template = string.Template(raw)
        substituted = template.safe_substitute(vars_dict)
        return yaml.safe_load(substituted)

def load_token(config):
    with open(config["token_path"], encoding="utf-8") as f:
        return f.read().strip()
    
def load_pending_ids(config):
    try:
        with open(config["ids_path"], encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def load_solicitud_id():
    with open("id_solicitud.txt", "r", encoding="utf-8") as f:
        return f.read().strip()

def build_verificacion_xml(config, id_solicitud):
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
    solicitud.set("RfcSolicitante", config["rfc"])

    return envelope

def sign_xml(doc, config):
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

    key = xmlsec.Key.from_file(config["key_path"], xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(config["cer_path"], xmlsec.KeyFormat.CERT_PEM)

    ctx = xmlsec.SignatureContext()
    ctx.key = key

    try:
        ctx.sign(signature_node)
    except Exception as e:
        print(f"Error durante la firma: {e}")
        raise

    return etree.tostring(doc, encoding="utf-8", xml_declaration=True, pretty_print=True)

def send_verificacion_request(xml_bytes, config, token):
    clean_token = unquote(token) if '%' in token else token

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": config["endpoints"]["verificacion_action"],
        "Authorization": f'WRAP access_token="{clean_token}"'
    }

    url = config["endpoints"]["verificacion"]

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

def parse_verificacion_response(xml_response, config, id_solicitud):
    with open("respuesta_verificacion.xml", "wb") as f:
        f.write(xml_response)
    print("Respuesta guardada en 'respuesta_verificacion.xml'")

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

                if paquetes:
                    os.makedirs(os.path.dirname(config["paquetes_path"]), exist_ok=True)
                    with open(config["paquetes_path"], "w", encoding="utf-8") as f:
                        for paquete in paquetes:
                            f.write(paquete + "\n")
                    print(f"Paquetes guardados en {config['paquetes_path']}")

                return {"estado": estado, "paquetes": paquetes}

            return {"estado": estado, "paquetes": []}

        print("✗ No se encontró el nodo de resultado en la respuesta")
        return None

    except Exception as e:
        print(f"✗ Error al parsear respuesta: {e}")
        return None
    
def actualizar_historial(config, id_solicitud, nuevo_estado):
    path = config["historial_path"]
    if not os.path.exists(path):
        print(f"(⚠) Historial no encontrado: {path}")
        return

    actualizado = []
    with open(path, "r", encoding="utf-8") as f:
        lineas = f.readlines()

    for linea in lineas:
        if linea.startswith(id_solicitud + ","):
            partes = linea.strip().split(",")
            partes[7] = nuevo_estado  # campo estado
            if nuevo_estado == "listo_para_descarga":
                partes[8] = str(datetime.now().date())  # fecha_descarga
            actualizado.append(",".join(partes) + "\n")
        else:
            actualizado.append(linea)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(actualizado)

    print(f"✓ Historial actualizado para {id_solicitud} → {nuevo_estado}")

def preparar_paths_por_anio(config):
    fecha_inicio = config["fechas"]["inicio"]
    anio = datetime.strptime(fecha_inicio, "%Y-%m-%d").year
    base_path = config["base_path"]
    anio_path = os.path.join(base_path, str(anio))
    config["anio_path"] = anio_path

    config["ids_path"]       = os.path.join(anio_path, "solicitudes", "id_solicitud.txt")
    config["historial_path"] = os.path.join(anio_path, "solicitudes", "historial.csv")
    config["paquetes_path"]  = os.path.join(anio_path, "solicitudes", "paquetes.txt")
    config["paquetes_dir"]   = os.path.join(anio_path, "paquetes")

    return config


def main():
    print("=== Verificación de solicitudes de descarga SAT ===")
    try:
        config = load_config()
        config = preparar_paths_por_anio(config)
        token = load_token(config)
        ids = load_pending_ids(config)
        if not ids:
            print("No hay solicitudes pendientes.")
            return

        nuevos_pendientes = []

        for id_solicitud in ids:
            print(f"\n→ Verificando Solicitud: {id_solicitud}")

            try:
                doc = build_verificacion_xml(config, id_solicitud)
                xml_firmado = sign_xml(doc, config)
                response = send_verificacion_request(xml_firmado, config, token)

                result = parse_verificacion_response(response, config, id_solicitud)

                if result and result["estado"] == "3":
                    actualizar_historial(config, id_solicitud, "listo_para_descarga")
                else:
                    nuevos_pendientes.append(id_solicitud)

            except Exception as e:
                print(f"✗ Error al verificar {id_solicitud}: {e}")
                nuevos_pendientes.append(id_solicitud)

        # Reescribe el archivo de pendientes
        with open(config["ids_path"], "w", encoding="utf-8") as f:
            for id_ in nuevos_pendientes:
                f.write(id_ + "\n")

        print(f"\n Pendientes restantes: {len(nuevos_pendientes)}")

    except Exception as e:
        print(f"✗ Error general: {e}")


if __name__ == "__main__":
    main()
