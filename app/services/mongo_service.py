import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db_name = os.getenv("MONGO_DB_NAME", "sat_cfdi") 
db = client[db_name]
clientes_collection = db["clientes"]
solicitudes_collection = db["solicitudes"]

def existe_cliente(rfc: str) -> bool:
    return clientes_collection.count_documents({"rfc": rfc}, limit=1) > 0

def registrar_cliente(rfc: str):
    clientes_collection.insert_one({
        "rfc": rfc,
        "creado_en": datetime.utcnow()
    })

def guardar_solicitud(data):
    # Normalizar
    data["rfc"] = data["rfc"].upper()
    data["tipo_solicitud"] = data["tipo_solicitud"].lower()
    data["tipo_comp"] = data["tipo_comp"].upper()
    solicitudes = obtener_coleccion_solicitudes()
    solicitudes.insert_one(data)


def existe_solicitud(rfc: str, fecha_inicio: str, fecha_fin: str, tipo_solicitud: str, tipo_comp: str) -> bool:
    query = {
        "rfc": rfc,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "tipo_solicitud": tipo_solicitud,
        "tipo_comp": tipo_comp
    }
    return solicitudes_collection.count_documents(query, limit=1) > 0

def actualizar_paquete_descargado(rfc: str, paquete_id: str, estado: str = "descargado"):
    solicitudes_collection.update_one(
        {"rfc": rfc, "paquetes": paquete_id},
        {"$set": {"estado": estado}}
    )

def agregar_paquete_a_solicitud(rfc: str, id_solicitud: str, paquete_id: str):
    solicitudes_collection.update_one(
        {"rfc": rfc, "id_solicitud": id_solicitud},
        {"$addToSet": {"paquetes": paquete_id}}
    )

def actualizar_estado_solicitud(rfc: str, id_solicitud: str, nuevo_estado: str):
    solicitudes_collection.update_one(
        {"rfc": rfc, "id_solicitud": id_solicitud},
        {"$set": {"estado": nuevo_estado}}
    )

def verificar_si_completo(rfc: str, id_solicitud: str, paquetes_descargados: list):
    # Buscar la solicitud correspondiente
    solicitud = solicitudes_collection.find_one({
        "rfc": rfc,
        "id_solicitud": id_solicitud
    })

    if not solicitud:
        print(f"Solicitud con ID {id_solicitud} no encontrada para el RFC {rfc}.")
        return

    # Obtener la lista de paquetes asociados a la solicitud
    paquetes_solicitud = solicitud.get("paquetes", [])

    # Verificar si todos los paquetes han sido descargados
    if all(paquete in paquetes_descargados for paquete in paquetes_solicitud):
        # Actualizar el estado de la solicitud a 'descargado'
        solicitudes_collection.update_one(
            {"_id": solicitud["_id"]},
            {"$set": {"estado": "descargado"}}
        )
        print(f"Solicitud con ID {id_solicitud} actualizada a estado 'descargado'.")
    else:
        print(f"No todos los paquetes de la solicitud con ID {id_solicitud} han sido descargados.")

def obtener_coleccion_solicitudes():
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise ValueError("No se ha definido MONGO_URI en el entorno")

    db_name = os.getenv("MONGO_DB_NAME", "sat_cfdi")
    client = MongoClient(uri)
    db = client[db_name]
    return db["solicitudes"]


def obtener_tipo_paquete(rfc: str, paquete_id: str) -> str:
    solicitud = solicitudes_collection.find_one({
        "rfc": rfc,
        "paquetes": paquete_id
    })
    if solicitud:
        return solicitud.get("tipo_solicitud", "cfdi")  # default cfdi si no se encuentra
    return "cfdi"
