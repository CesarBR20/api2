import subprocess
import os

def convert_to_pem(cer_path: str, key_path: str, password_path: str, output_dir: str):
    # Leer la contraseña desde el archivo
    with open(password_path, 'r') as f:
        password = f.read().strip()

    # Definir las rutas de salida
    cert_pem_path = os.path.join(output_dir, 'cert.pem')
    fiel_pem_path = os.path.join(output_dir, 'fiel.pem')

    # Convertir el archivo .cer a cert.pem
    subprocess.run([
        'openssl', 'x509',
        '-inform', 'DER',
        '-outform', 'PEM',
        '-in', cer_path,
        '-out', cert_pem_path
    ], check=True)

    # Convertir el archivo .key a fiel.pem usando la contraseña
    subprocess.run([
        'openssl', 'pkcs8',
        '-inform', 'DER',
        '-in', key_path,
        '-passin', f'pass:{password}',
        '-out', fiel_pem_path
    ], check=True)

    return cert_pem_path, fiel_pem_path