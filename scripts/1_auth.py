# auth.py - Autenticación
import yaml
import requests
from lxml import etree
from utils.signer import build_soap_envelope, sign_envelope
import string
import os

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

def get_token():
    config = load_config()
    env, ts, sec, bst_id = build_soap_envelope(config["cer_path"], config["key_path"])
    signed = sign_envelope(env, ts, sec, config["key_path"], config["cer_path"], bst_id)

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": config["endpoints"]["autenticacion_action"]
    }

    xml_data = etree.tostring(signed, xml_declaration=True, encoding="utf-8")
    resp = requests.post(config["endpoints"]["autenticacion"], data=xml_data, headers=headers)

    if resp.status_code != 200:
        print(f"Error en autenticación: {resp.status_code}")
        print(resp.text)
        raise Exception("Error al autenticar.")

    root = etree.fromstring(resp.content)
    token = root.find(".//{http://DescargaMasivaTerceros.gob.mx}AutenticaResult")
    return token.text if token is not None else None

if __name__ == "__main__":
    config = load_config()
    token = get_token()
    print("Token obtenido exitosamente")
    
    token_dir = os.path.dirname(config["token_path"])
    os.makedirs(token_dir, exist_ok=True)
    
    with open(config["token_path"], "w", encoding="utf-8") as f:
        f.write(token)
    print(f"Token guardado en {config['token_path']}") 