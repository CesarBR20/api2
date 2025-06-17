from apscheduler.schedulers.background import BackgroundScheduler
from services.division_service import dividir_y_reintentar
import requests
import pytz
import logging

logger = logging.getLogger(__name__)
tz = pytz.timezone("America/Mexico_City")

def verificacion_programada():
    """
    Verifica el estado de las solicitudes y divide las que excedan los límites.
    """
    try:
        # Autenticación
        auth_res = requests.post("http://localhost:8000/auth-sat/")
        if auth_res.status_code != 200:
            logger.error("Error en autenticación")
            return
        token = auth_res.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}

        # Obtener solicitudes pendientes
        res = requests.get("http://localhost:8000/solicitudes-pendientes/", headers=headers)
        if res.status_code != 200:
            logger.error("Error al obtener solicitudes pendientes")
            return
        solicitudes = res.json()

        for solicitud in solicitudes:
            if solicitud["estado"] == 4:
                dividir_y_reintentar(solicitud, token)
            elif solicitud["estado"] == 3:
                pass

    except Exception as e:
        logger.error(f"Error en verificación programada: {e}")

def iniciar_scheduler():
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(verificacion_programada, "cron", hour=23, minute=0)
    scheduler.start()
