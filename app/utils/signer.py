import base64
import uuid
from lxml import etree
import xmlsec


def build_soap_envelope(cert_path, key_path):
    # Fechas
    import datetime
    created = datetime.datetime.now(datetime.timezone.utc)
    expires = created + datetime.timedelta(minutes=5)
    created_str = created.strftime('%Y-%m-%dT%H:%M:%SZ')
    expires_str = expires.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Namespaces
    NSMAP = {
        's': 'http://schemas.xmlsoap.org/soap/envelope/',
        'u': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd',
        'o': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd'
    }

    # SOAP Envelope
    envelope = etree.Element('{%s}Envelope' % NSMAP['s'], nsmap=NSMAP)
    header = etree.SubElement(envelope, '{%s}Header' % NSMAP['s'])
    body = etree.SubElement(envelope, '{%s}Body' % NSMAP['s'])

    # WS-Security
    security = etree.SubElement(header, '{%s}Security' % NSMAP['o'], nsmap=NSMAP)
    security.set('{%s}mustUnderstand' % NSMAP['s'], '1')

    # Timestamp
    timestamp = etree.SubElement(security, '{%s}Timestamp' % NSMAP['u'])
    timestamp.set('{%s}Id' % NSMAP['u'], 'TS')
    created_el = etree.SubElement(timestamp, '{%s}Created' % NSMAP['u'])
    created_el.text = created_str
    expires_el = etree.SubElement(timestamp, '{%s}Expires' % NSMAP['u'])
    expires_el.text = expires_str

    # BinarySecurityToken
    cert_data = open(cert_path, 'rb').read()
    cert_b64 = base64.b64encode(cert_data).decode()
    bst_id = f"uuid-{uuid.uuid4()}"
    bst = etree.SubElement(security, '{%s}BinarySecurityToken' % NSMAP['o'])
    bst.set('{%s}Id' % NSMAP['u'], bst_id)
    bst.set("ValueType", "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3")
    bst.set("EncodingType", "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary")
    bst.text = cert_b64

    # Cuerpo de autenticación
    auth = etree.SubElement(body, '{http://DescargaMasivaTerceros.gob.mx}Autentica')


    return envelope, timestamp, security, bst_id


def sign_envelope(envelope, timestamp, security, key_path, cert_path, bst_id):
    # Crear template de firma
    signature_node = xmlsec.template.create(
        envelope,
        c14n_method=xmlsec.Transform.EXCL_C14N,
        sign_method=xmlsec.Transform.RSA_SHA1,
        ns='ds'
    )

    security.append(signature_node)

    # Referencia al Timestamp
    ref = xmlsec.template.add_reference(
        signature_node,
        xmlsec.Transform.SHA1,
        uri="#TS"
    )
    xmlsec.template.add_transform(ref, xmlsec.Transform.EXCL_C14N)

    # KeyInfo y SecurityTokenReference
    key_info = xmlsec.template.ensure_key_info(signature_node)
    str_el = etree.SubElement(key_info, '{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd}SecurityTokenReference')
    ref_el = etree.SubElement(str_el, '{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd}Reference')
    ref_el.set("URI", f"#{bst_id}")
    ref_el.set("ValueType", "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3")

    # 🔑 Esta línea es la que corrige el fallo
    xmlsec.tree.add_ids(timestamp, ["Id"])

    # Cargar clave
    ctx = xmlsec.SignatureContext()
    key = xmlsec.Key.from_file(key_path, xmlsec.KeyFormat.PEM)
    key.load_cert_from_file(cert_path, xmlsec.KeyFormat.PEM)
    ctx.key = key

    # Firmar
    ctx.sign(signature_node)

    return envelope
