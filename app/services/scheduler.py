from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
import os
import requests

tz = pytz.timezone("America/Mexico_City")

def ejecutar_auth_y_verify():
    try:
        print(f"[{datetime.now(tz)}] Ejecutando auth y verify...")

        # 1. Autenticación
        res_auth = requests.post("http://localhost:8000/auth-sat/")
        print("Auth status:", res_auth.status_code)

        # 2. Verificación
        res_verify = requests.post("http://localhost:8000/verificar-solicitudes/")
        print("Verify status:", res_verify.status_code)

    except Exception as e:
        print(f"Error en tarea programada: {e}")

def iniciar_scheduler():
    scheduler = BackgroundScheduler(timezone=tz)
    # Ejecutar todos los días a las 08:00 AM y 04:00 PM
    scheduler.add_job(ejecutar_auth_y_verify, "cron", hour=8, minute=0)
    scheduler.add_job(ejecutar_auth_y_verify, "cron", hour=16, minute=0)
    scheduler.start()
