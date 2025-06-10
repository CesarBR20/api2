import subprocess
import os
import shutil
import yaml
import string

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

def es_formato_pem(file_path):
    with open(file_path, 'rb') as f:
        inicio = f.read(64)
        return b'-----BEGIN' in inicio

def leer_password_desde_txt(password_path):
    try:
        with open(password_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        raise RuntimeError(f"❌ No se pudo leer la contraseña desde {password_path}: {e}")

def buscar_archivo_por_extension(directorio, extension):
    archivos = [f for f in os.listdir(directorio) if f.lower().endswith(extension.lower())]
    if len(archivos) == 0:
        raise FileNotFoundError(f"❌ No se encontró ningún archivo con extensión {extension} en {directorio}")
    if len(archivos) > 1:
        raise ValueError(f"⚠️ Se encontró más de un archivo con extensión {extension} en {directorio}. Solo debe haber uno.")
    return os.path.join(directorio, archivos[0])

def convertir_clave_privada_der_cifrada(key_path, key_pem, pfx_pass):
    temp_pem = key_pem + ".tmp"
    try:
        # Paso 1: DER cifrado → PEM cifrado
        subprocess.run([
            "openssl", "pkcs8",
            "-inform", "DER",
            "-in", key_path,
            "-out", temp_pem,
            "-passin", f"pass:{pfx_pass}"
        ], check=True)

        # Paso 2: PEM cifrado → PEM sin cifrar (RSA)
        subprocess.run([
            "openssl", "rsa",
            "-in", temp_pem,
            "-out", key_pem
        ], check=True)

        os.remove(temp_pem)
        print(f"✅ Clave privada convertida: {key_pem}")

    except subprocess.CalledProcessError as e:
        print("❌ Error al convertir clave privada:")
        print(e)
        raise

def convertir_y_generar_desde_config():
    config = load_config()
    certificados_dir = os.path.join(config["base_path"], "certificados")

    pfx_pass = leer_password_desde_txt(config["pfx_password_path"])
    cer_path = buscar_archivo_por_extension(certificados_dir, ".cer")
    key_path = buscar_archivo_por_extension(certificados_dir, ".key")

    cert_pem = os.path.join(certificados_dir, "cert.pem")
    key_pem = os.path.join(certificados_dir, "fiel.pem")
    pfx_tmp = os.path.join(certificados_dir, "tmp_cert.pfx")
    final_pem = os.path.join(certificados_dir, "cert_expandido.pem")

    try:
        # Convertir certificado
        subprocess.run([
            'openssl', 'x509',
            '-inform', 'DER',
            '-in', cer_path,
            '-out', cert_pem
        ], check=True)
        print(f"✅ Certificado convertido: {cert_pem}")

        # Convertir clave privada
        if es_formato_pem(key_path):
            shutil.copyfile(key_path, key_pem)
            print(f"🔁 Clave ya estaba en PEM. Copiada como: {key_pem}")
        else:
            convertir_clave_privada_der_cifrada(key_path, key_pem, pfx_pass)

        # Generar archivo PFX temporal
        subprocess.run([
            'openssl', 'pkcs12',
            '-export',
            '-inkey', key_pem,
            '-in', cert_pem,
            '-name', 'miFIEL',
            '-out', pfx_tmp,
            '-passout', f'pass:{pfx_pass}'
        ], check=True)
        print(f"📦 PFX generado: {pfx_tmp}")

        # Extraer cert_expandido.pem con Bag Attributes
        subprocess.run([
            'openssl', 'pkcs12',
            '-in', pfx_tmp,
            '-out', final_pem,
            '-clcerts',
            '-nokeys',
            '-passin', f'pass:{pfx_pass}'
        ], check=True)
        
        # Renombrar cert_expandido.pem → cert.pem (reemplaza el anterior)
        os.replace(final_pem, cert_pem)
        print(f"✅ Se renombró {final_pem} como {cert_pem}")

        # Eliminar archivo temporal pfx
        os.remove(pfx_tmp)

        # Proteger archivos
        for path in [cert_pem, key_pem]:
            os.chmod(path, 0o600)


    except subprocess.CalledProcessError as e:
        print("❌ Error al ejecutar OpenSSL:")
        print(e)
    except Exception as ex:
        print(f"❌ Error inesperado: {ex}")

# Ejecutar
if __name__ == "__main__":
    convertir_y_generar_desde_config()
