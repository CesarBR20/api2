# app/services/auth_service.py

import os
import requests
from lxml import etree
from app.utils.signer import build_soap_envelope, sign_envelope

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
