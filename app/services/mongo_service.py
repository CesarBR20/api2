import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["sat_cfdi"]
clientes_collection = db["clientes"]
solicitudes_collection = db["solicitudes"]

def existe_cliente(rfc: str) -> bool:
    return clientes_collection.count_documents({"rfc": rfc}, limit=1) > 0

def registrar_cliente(rfc: str):
    clientes_collection.insert_one({
        "rfc": rfc,
        "creado_en": datetime.utcnow()
    })

def guardar_solicitud(data: dict):
    solicitudes_collection.insert_one(data)

def existe_solicitud(rfc: str, fecha_inicio: str, fecha_fin: str, tipo_solicitud: str, tipo_comp: str) -> bool:
    query = {
        "rfc": rfc,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "tipo_solicitud": tipo_solicitud,
        "tipo_comp": tipo_comp
    }
    return solicitudes_collection.count_documents(query, limit=1) > 0
