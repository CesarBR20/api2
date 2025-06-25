from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
from io import BytesIO
import xmltodict
import zipfile
import boto3
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")

mongo_client = MongoClient(MONGO_URI)
cfdi_db = mongo_client[MONGO_DB_NAME]["cfdi"]
metadata_db = mongo_client[MONGO_DB_NAME]["metadata"]

def procesar_cfdi_completo(cliente_rfc, bucket_name, prefix):
    s3 = boto3.client('s3')
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    for obj in response.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".zip"):
            continue  # Solo procesar archivos zip

        try:
            zip_obj = s3.get_object(Bucket=bucket_name, Key=key)["Body"].read()
            with zipfile.ZipFile(BytesIO(zip_obj)) as the_zip:
                for zip_info in the_zip.infolist():
                    file_name = zip_info.filename

                    # Procesamiento CFDI (XML)
                    if file_name.endswith(".xml"):
                        xml_file = the_zip.read(zip_info)
                        try:
                            xml_dict = xmltodict.parse(xml_file, force_list=None)
                            comprobante = xml_dict.get("cfdi:Comprobante", {})
                            complemento = comprobante.get("cfdi:Complemento", {})
                            tfd = complemento.get("tfd:TimbreFiscalDigital", {})
                            uuid = tfd.get("@UUID", "")

                            if not uuid:
                                print(f"❌ XML sin UUID en zip {key}, archivo {file_name}")
                                continue

                            doc = {
                                "cliente": cliente_rfc,
                                "uuid": uuid,
                                "fechaProcesado": datetime.utcnow(),
                                "xml": xml_dict
                            }

                            if not cfdi_db.find_one({"uuid": uuid}):
                                cfdi_db.insert_one(doc)
                                print(f"CFDI guardado: {uuid} desde {key} -> {file_name}")
                            else:
                                print(f"CFDI ya existe: {uuid}")
                        except Exception as e:
                            print(f"Error procesando XML {file_name} en zip {key}: {e}")

                    # Procesamiento METADATA (.txt)
                    elif file_name.endswith(".txt"):
                        try:
                            raw = the_zip.read(zip_info).decode("utf-8-sig").strip()
                            lines = raw.splitlines()
                            headers = lines[0].split("~")
                            
                            for line in lines[1:]:
                                values = line.split("~")
                                if len(values) != len(headers):
                                    print(f"Línea inválida en {file_name}: {line}")
                                    continue

                                row = dict(zip(headers, values))
                                row["cliente"] = cliente_rfc
                                row["archivoZip"] = key
                                row["fechaProcesado"] = datetime.utcnow()
                                uuid = row.get("Uuid", "")

                                if uuid and not metadata_db.find_one({"Uuid": uuid}):
                                    metadata_db.insert_one(row)
                                    print(f"Metadata guardada: {uuid} desde {file_name}")
                                else:
                                    print(f"Metadata ya existe o sin UUID: {uuid}")

                        except Exception as e:
                            print(f"Error procesando metadata {file_name} en zip {key}: {e}")

        except Exception as e:
            print(f"Error leyendo zip {key}: {e}")
