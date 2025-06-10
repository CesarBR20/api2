# request_cfdis.py  –  versión 2025-05-30 21:45
import yaml, requests, xmlsec, base64
from lxml import etree
from uuid import uuid4
from urllib.parse import unquote
import string
import os
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

def build_solicitud_xml(config):
    NS_SOAP     = "http://schemas.xmlsoap.org/soap/envelope/"
    NS_DESCARGA = "http://DescargaMasivaTerceros.sat.gob.mx"
    NS_WSA      = "http://www.w3.org/2005/08/addressing"
    NS_DS       = "http://www.w3.org/2000/09/xmldsig#"

    d  = config["descarga"]
    op = "SolicitaDescargaRecibidos"
    if "folio" in d:
        op = "SolicitaDescargaFolio"
    elif d.get("tipo_comp", "").upper() == "E" or "rfc_emisor" in d:
        op = "SolicitaDescargaEmitidos"

    soap_action = (f"http://DescargaMasivaTerceros.sat.gob.mx/"
                   f"ISolicitaDescargaService/{op}")

    env = etree.Element(f"{{{NS_SOAP}}}Envelope", nsmap={
        "s": NS_SOAP, "wsa": NS_WSA, "ds": NS_DS, "ns0": NS_DESCARGA
    })
    hdr = etree.SubElement(env, f"{{{NS_SOAP}}}Header")

    act = etree.SubElement(hdr, f"{{{NS_WSA}}}Action")
    act.text = soap_action          # sin mustUnderstand

    to  = etree.SubElement(hdr, f"{{{NS_WSA}}}To")
    to.text = config["endpoints"]["solicitud"]

    mid = etree.SubElement(hdr, f"{{{NS_WSA}}}MessageID")
    mid.text = f"uuid:{uuid4()}"

    body   = etree.SubElement(env, f"{{{NS_SOAP}}}Body")
    opnode = etree.SubElement(body, f"{{{NS_DESCARGA}}}{op}")

    sol = etree.SubElement(opnode, f"{{{NS_DESCARGA}}}solicitud", nsmap={"ds": NS_DS})
    sol.set("Id", "Solicitud")
    sol.set("RfcSolicitante", config["rfc"])
    sol.set("FechaInicial", config["fechas"]["inicio"] + "T00:00:00")
    sol.set("FechaFinal",  config["fechas"]["fin"]    + "T23:59:59")
    sol.set("TipoSolicitud", d.get("tipo_solicitud", "CFDI"))

    # ← aquí el cambio: aplica filtros cuando sea CFDI **o** Metadata
    if d.get("tipo_solicitud") in ("CFDI", "Metadata"):
        if "tipo_comp"    in d: sol.set("TipoComp",    d["tipo_comp"])
        if "rfc_emisor"   in d: sol.set("RfcEmisor",   d["rfc_emisor"])
        if "rfc_receptor" in d: sol.set("RfcReceptor", d["rfc_receptor"])
        if "folio"        in d: sol.set("Folio",       d["folio"])

    return env, soap_action

def sign_solicitud_xml(doc, config):
    sol = doc.find(".//solicitud") or \
          doc.find(".//{http://DescargaMasivaTerceros.sat.gob.mx}solicitud")

    sig = xmlsec.template.create(sol, xmlsec.Transform.EXCL_C14N,
                                 xmlsec.Transform.RSA_SHA1, ns="ds")
    sol.insert(0, sig)
    ref = xmlsec.template.add_reference(sig, xmlsec.Transform.SHA1, uri="#Solicitud")
    xmlsec.template.add_transform(ref, xmlsec.Transform.ENVELOPED)
    ki = xmlsec.template.ensure_key_info(sig)
    xmlsec.template.add_x509_data(ki)

    key = xmlsec.Key.from_file(config["key_path"], xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(config["cer_path"], xmlsec.KeyFormat.CERT_PEM)
    ctx = xmlsec.SignatureContext(); ctx.key = key
    ctx.register_id(sol, "Id")
    ctx.sign(sig)

    return etree.tostring(doc, encoding="utf-8", xml_declaration=True, pretty_print=True)

# --------------------------------------------------
def send_solicitud_request(xml_bytes, config, token, soap_action):
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction":  soap_action,
        "Authorization": f'WRAP access_token="{unquote(token)}"'
    }
    url = config["endpoints"]["solicitud"]
    print(f"Enviando a: {url}\nSOAPAction: {soap_action}")

    resp = requests.post(url, data=xml_bytes, headers=headers, timeout=60)
    print(f"Código HTTP: {resp.status_code}")
    if resp.status_code != 200:
        print(resp.text); raise Exception(f"HTTP {resp.status_code}")
    return resp.content

# --------------------------------------------------
def parse_solicitud_response(xml_bytes):
    open("respuesta_solicitud.xml", "wb").write(xml_bytes)
    tree = etree.fromstring(xml_bytes)

    # 1. ¿Fault?
    fault = tree.xpath("//*[local-name()='Fault']")
    if fault:
        code = tree.xpath("//*[local-name()='faultcode']/text()")[0]
        msg  = tree.xpath("//*[local-name()='faultstring']/text()")[0]
        raise Exception(f"SOAP Fault {code}: {msg}")

    # 2. Cualquier nodo ...Result
    result_nodes = tree.xpath("//*[substring(local-name(), string-length(local-name())-5) = 'Result']")
    if not result_nodes:
        print("No se encontró nodo *Result*. Revisa respuesta_solicitud.xml")
        print(xml_bytes.decode("utf-8", errors="ignore"))
        raise IndexError("Sin nodo Result")

    res = result_nodes[0]
    cod = res.get("CodEstatus")
    msg = res.get("Mensaje", "")
    if cod != "5000":
        raise Exception(f"CodEstatus {cod}: {msg}")

    return res.get("IdSolicitud")

def ya_existe_solicitud(historial_path, tipo_solicitud, fecha_inicio, fecha_fin, tipo_comp, rfc_emisor):
    if not os.path.exists(historial_path):
        return False

    with open(historial_path, encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("id_solicitud"):
                continue 
            campos = linea.strip().split(",")
            if len(campos) < 6:
                continue
            if (
                campos[1] == tipo_solicitud and
                campos[2] == fecha_inicio and
                campos[3] == fecha_fin and
                campos[4] == tipo_comp and
                campos[5] == rfc_emisor
            ):
                return campos[0]
    return False

def crear_estructura_anual(config):
    fecha_inicio = config["fechas"]["inicio"]
    anio = datetime.strptime(fecha_inicio, "%Y-%m-%d").year
    base_path = config["base_path"]
    anio_path = os.path.join(base_path, str(anio))
    config["anio_path"] = anio_path

    # Definir rutas completas para el año
    config["ids_path"]       = os.path.join(anio_path, "solicitudes", "id_solicitud.txt")
    config["historial_path"] = os.path.join(anio_path, "solicitudes", "historial.csv")
    config["paquetes_path"]  = os.path.join(anio_path, "solicitudes", "paquetes.txt")
    config["paquetes_dir"]   = os.path.join(anio_path, "paquetes")

    rutas = [
        os.path.join(anio_path, "paquetes", "cfdi"),
        os.path.join(anio_path, "paquetes", "metadata", "semestre1"),
        os.path.join(anio_path, "paquetes", "metadata", "semestre2"),
        os.path.join(anio_path, "solicitudes")
    ]

    for ruta in rutas:
        os.makedirs(ruta, exist_ok=True)

    return config

def main():
    print("=== Solicitud de Descarga Masiva de CFDIs del SAT ===")
    cfg   = load_config()
    token = load_token(cfg)
    
    cfg = crear_estructura_anual(cfg)

    tipo_solicitud = cfg["descarga"].get("tipo_solicitud", "")
    fecha_inicio   = cfg["fechas"].get("inicio", "")
    fecha_fin      = cfg["fechas"].get("fin", "")
    tipo_comp      = cfg["descarga"].get("tipo_comp", "")
    rfc_emisor     = cfg["descarga"].get("rfc_emisor", "")
    historial_path = cfg.get("historial_path") or f"clientes/{cfg['rfc']}/solicitudes/historial.csv"

    existente = ya_existe_solicitud(historial_path, tipo_solicitud, fecha_inicio, fecha_fin, tipo_comp, rfc_emisor)
    if existente:
        print(f"✗ Ya existe una solicitud con la misma combinación:")
        print(f"  → IdSolicitud existente: {existente}")
        print("→ Esta solicitud ha sido cancelada para evitar duplicados.")
        return

    doc, action = build_solicitud_xml(cfg)
    xml_firmado = sign_solicitud_xml(doc, cfg)
    open("solicitud_firmada.xml", "wb").write(xml_firmado)

    resp = send_solicitud_request(xml_firmado, cfg, token, action)
    id_solic = parse_solicitud_response(resp)

    print(f"\n✓ Solicitud aceptada – IdSolicitud: {id_solic}")
    os.makedirs(os.path.dirname(cfg["ids_path"]), exist_ok=True)
    with open(cfg["ids_path"], "a", encoding="utf-8") as f:
        f.write(id_solic + "\n")
        print(f"IdSolicitud guardado en {cfg['ids_path']}")

    os.makedirs(os.path.dirname(historial_path), exist_ok=True)
    es_nuevo = not os.path.exists(historial_path)
    with open(historial_path, "a", encoding="utf-8") as f:
        if es_nuevo:
            f.write("id_solicitud,tipo_solicitud,fecha_inicio,fecha_fin,tipo_comp,rfc_emisor,fecha_solicitud,estado,fecha_descarga\n")
        f.write(f"{id_solic},{tipo_solicitud},{fecha_inicio},{fecha_fin},{tipo_comp},{rfc_emisor},{datetime.now().date()},solicitado,\n")

    print(f"Registro añadido a historial → {historial_path}")
    print("→ Espera unos minutos y corre tu verificación.")     

if __name__ == "__main__":
    main()
