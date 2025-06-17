from datetime import datetime, timedelta
import requests
import logging

logger = logging.getLogger(__name__)

LIMITES = {
    "CFDI": 200_000,
    "Metadata": 1_000_000
}

def dividir_y_reintentar(solicitud: dict, token: str):
    """
    Divide una solicitud en dos subrangos y crea nuevas solicitudes con herencia del id original.
    """
    tipo = solicitud["tipo"]
    rfc = solicitud["rfc"]
    fecha_inicio = datetime.strptime(solicitud["fecha_inicio"], "%Y-%m-%d")
    fecha_fin = datetime.strptime(solicitud["fecha_fin"], "%Y-%m-%d")
    delta = (fecha_fin - fecha_inicio).days

    if delta < 1:
        logger.error(f"No se puede dividir más la solicitud: {solicitud}")
        return

    mitad = fecha_inicio + timedelta(days=delta // 2)

    rangos = [
        (fecha_inicio.strftime("%Y-%m-%d"), mitad.strftime("%Y-%m-%d")),
        ((mitad + timedelta(days=1)).strftime("%Y-%m-%d"), fecha_fin.strftime("%Y-%m-%d"))
    ]

    headers = {"Authorization": f"Bearer {token}"}

    for inicio, fin in rangos:
        body = {
            "rfc": rfc,
            "fecha_inicio": inicio,
            "fecha_fin": fin,
            "tipo": tipo,
            "dividida_de": solicitud["id_solicitud"]  # campo nuevo
        }

        try:
            res = requests.post("http://127.0.0.1:8000/solicitar-cfdi/", headers=headers, json=body)
            if res.status_code != 200:
                logger.error(f"Fallo creando subsolicitud: {res.status_code} {res.text}")
                continue

            nueva = res.json()
            nueva_id = nueva.get("id_solicitud")
            logger.info(f"Nueva solicitud: {nueva_id} (hija de {solicitud['id_solicitud']})")

        except Exception as e:
            logger.error(f"Error dividiendo solicitud {solicitud['id_solicitud']}: {e}")
