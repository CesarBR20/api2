# c_dwnld.py - Descarga masiva de CFDIs
import base64
import os
import pathlib
import yaml, string
import requests
import xmlsec
from lxml import etree
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

def load_paquetes(config):
    try:
        with open(config["paquetes_path"], encoding="utf-8") as f:
            return [p.strip() for p in f if p.strip()]
    except FileNotFoundError:
        return []

def build_descarga_xml(cfg, paquete_id):
    NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
    NS_DES  = "http://DescargaMasivaTerceros.sat.gob.mx"
    NS_DS   = "http://www.w3.org/2000/09/xmldsig#"

    env  = etree.Element("{%s}Envelope" % NS_SOAP,
                         nsmap={'s': NS_SOAP, 'des': NS_DES, 'ds': NS_DS})
    body = etree.SubElement(env, "{%s}Body" % NS_SOAP)

    entrada = etree.SubElement(
        body, "{%s}PeticionDescargaMasivaTercerosEntrada" % NS_DES)

    pet = etree.SubElement(
        entrada, "{%s}peticionDescarga" % NS_DES,
        Id="_0",
        RfcSolicitante=cfg["rfc"],
        IdPaquete=paquete_id)

    return env, pet

def sign_peticion(node, cfg):
    sig = xmlsec.template.create(
        node,
        xmlsec.Transform.EXCL_C14N,
        xmlsec.Transform.RSA_SHA1,
        ns="ds")

    node.insert(0, sig)

    ref = xmlsec.template.add_reference(
        sig, xmlsec.Transform.SHA1, uri="#_0")
    xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)

    ki = xmlsec.template.ensure_key_info(sig)
    xmlsec.template.add_x509_data(ki)

    key = xmlsec.Key.from_file(cfg["key_path"], xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(cfg["cer_path"], xmlsec.KeyFormat.CERT_PEM)

    ctx = xmlsec.SignatureContext()
    ctx.key = key
    ctx.register_id(node, "Id")

    ctx.sign(sig)
    print("✓ Firma digital aplicada al nodo peticionDescarga")

def send_descarga(xml_bytes, cfg, token):
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": cfg["endpoints"]["descarga_action"],
        "Authorization": f'WRAP access_token="{unquote(token)}"'
    }
    url = cfg["endpoints"]["descarga"]
    resp = requests.post(url, data=xml_bytes, headers=headers, timeout=120)
    print(f"→ HTTP {resp.status_code}")
    resp.raise_for_status()

    with open("respuesta_descarga.xml", "wb") as f:
        f.write(resp.content)
    return resp.content

def parse_and_save(xml_bytes, paquete_id, config):
    root = etree.fromstring(xml_bytes)
    cod = root.xpath("//*[local-name()='respuesta']/@CodEstatus")
    msg = root.xpath("//*[local-name()='respuesta']/@Mensaje")

    if not cod or cod[0] != "5000":
        raise RuntimeError(f"SAT devolvió {cod}:{msg}")

    b64 = root.xpath("//*[local-name()='Paquete']/text()")
    if not b64 or not b64[0].strip():
        raise RuntimeError("Respuesta 5000 pero Paquete vacío")

    raw = base64.b64decode(b64[0])
    dest_dir = pathlib.Path(config["paquetes_dir"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = dest_dir / f"{paquete_id}.zip"
    fname.write_bytes(raw)
    print(f"✓ Paquete guardado → {fname}")
    
def marcar_descargado_en_historial(config, paquete_id):
    path = config["historial_path"]
    if not os.path.exists(path):
        print(f"(⚠) Historial no encontrado: {path}")
        return

    actualizado = []
    encontrado = False

    with open(path, "r", encoding="utf-8") as f:
        lineas = f.readlines()

    for linea in lineas:
        if linea.startswith(paquete_id + ","):
            partes = linea.strip().split(",")
            partes[7] = "descargado"
            partes[8] = str(datetime.now().date())
            actualizado.append(",".join(partes) + "\n")
            encontrado = True
        else:
            actualizado.append(linea)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(actualizado)

    if encontrado:
        print(f"✓ Historial actualizado: {paquete_id} marcado como descargado")
    else:
        print(f"(⚠) No se encontró {paquete_id} en historial")

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
    print("=== Descarga masiva de CFDI – Paso 4 ===")
    config = load_config()
    config = preparar_paths_por_anio(config)
    token = load_token(config)
    paquetes = load_paquetes(config)

    if not paquetes:
        print("No hay paquetes por descargar.")
        return

    nuevos_pendientes = []

    for paquete_id in paquetes:
        print(f"\nDescargando {paquete_id} …")
        try:
            env, pet = build_descarga_xml(config, paquete_id)
            sign_peticion(pet, config)
            xml_out = etree.tostring(env, encoding="utf-8", xml_declaration=True)
            respuesta = send_descarga(xml_out, config, token)
            parse_and_save(respuesta, paquete_id, config)
            marcar_descargado_en_historial(config, paquete_id)
        except Exception as e:
            print(f"✗ Error al descargar paquete {paquete_id}: {e}")
            nuevos_pendientes.append(paquete_id)

    with open(config["paquetes_path"], "w", encoding="utf-8") as f:
        for p in nuevos_pendientes:
            f.write(p + "\n")

    print(f"\n✓ Descarga completada. Pendientes restantes: {len(nuevos_pendientes)}")


if __name__ == "__main__":
    main()
