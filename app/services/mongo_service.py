from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["sat_db"]
solicitudes_collection = db["solicitudes"]

def guardar_solicitud(data: dict):
    solicitudes_collection.insert_one(data)

def obtener_solicitudes(rfc: str):
    return list(solicitudes_collection.find({"rfc": rfc}))
