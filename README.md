# SATisFacture

## Descripción del Proyecto

Plataforma SaaS multiusuario diseñada para automatizar el análisis de precios de transferencia y la gestión fiscal de empresas en México. El sistema integra los Web Services del SAT (Servicio de Administración Tributaria) versión 1.5 para la descarga masiva y procesamiento automático de CFDI (Comprobantes Fiscales Digitales por Internet) y metadata.

### Objetivo Principal

Resolver la problemática cliente-despacho contable al permitir que los contribuyentes suban su FIEL (e.firma) y el sistema obtenga automáticamente todos sus comprobantes fiscales desde la fuente oficial del SAT, eliminando el intercambio manual de archivos y reduciendo el tiempo de análisis de días a minutos.

### Propuesta de Valor

- **Velocidad:** Análisis de precios de transferencia generados en minutos vs días del proceso manual
- **Precisión:** Datos obtenidos directamente del SAT, eliminando errores de selección manual
- **Automatización completa:** Desde la solicitud hasta el procesamiento, sin intervención manual
- **Escalabilidad:** Estrategia de descarga adaptativa según tamaño de empresa (diaria/semanal/mensual)

### Usuarios Objetivo

1. **Despachos contables:** Que necesitan hacer precios de transferencia para múltiples clientes
2. **Contadores independientes:** Que buscan automatizar análisis fiscales
3. **Empresas:** Que requieren análisis fiscal interno periódico
4. **Personas físicas con actividad empresarial:** Que necesitan cumplir con obligaciones de precios de transferencia

### Tipo de Proyecto

**API REST (Backend)** - Microservicio especializado en integración con SAT

## Stack Tecnológico

### Lenguajes y Frameworks

- **Python:** 3.12.9 - [https://www.python.org/](https://www.python.org/)
- **FastAPI:** Framework web moderno y de alto rendimiento - [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)

### Bibliotecas Principales

- **lxml:** 5.2.2 - Procesamiento de XML y manejo de documentos grandes - [https://lxml.de/](https://lxml.de/)
- **xmltodict:** 0.14.2 - Conversión de XML a diccionarios Python
- **xmlsec:** 1.3.15 - Firma digital con certificados FIEL - [https://pypi.org/project/xmlsec/](https://pypi.org/project/xmlsec/)
- **requests:** 2.32.3 - Cliente HTTP para consumir Web Services del SAT
- **pymongo:** 4.12.0 - Driver de MongoDB para Python
- **boto3:** 1.38.7 - SDK de AWS para Python (S3 principalmente)

### Infraestructura

- **MongoDB:** Base de datos NoSQL para almacenamiento de solicitudes y metadatos
- **Amazon S3:** Almacenamiento de certificados FIEL, tokens y archivos descargados
- **Docker:** Contenedorización de la aplicación
- **AWS ECS (Elastic Container Service):** Orquestación y deployment de contenedores
- **Amazon ECR:** Registro de imágenes Docker

## Dependencias Externas

### Servicios Requeridos

#### 1. Base de Datos MongoDB

- Debe estar accesible en la red
- Se requieren las colecciones: `solicitudes`, `paquetes`, `cfdi`, `metadata`, `clientes`, `grupos`, `usuarios`, `uploads`
- Variables de entorno necesarias: `MONGO_URI`, `MONGO_DB`

#### 2. Amazon S3

- Bucket configurado para almacenar:
  - Certificados FIEL (`.cer`, `.key`)
  - Tokens de autenticación
  - Archivos descargados (`.zip`)
- Credenciales AWS configuradas: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

#### 3. Web Services del SAT

- URL de autenticación: Configurada en variable de entorno
- URL de solicitud de descarga
- URL de verificación
- URL de descarga de paquetes
- **Nota:** Las URLs son proporcionadas por el SAT y pueden variar entre ambientes

#### 4. Certificados FIEL del Contribuyente

- Certificado (.cer convertido a .pem)
- Llave privada (.key convertida a .pem)
- Contraseña de la llave privada en txt con el nombre de **password.txt**

## Iniciar el Repositorio

### Instalar Dependencias

#### Dependencias del Sistema (Linux/Ubuntu)

```bash
# Instalar librerías necesarias para xmlsec y lxml
sudo apt-get update
sudo apt-get install -y \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    python3-dev \
    build-essential
```

#### Dependencias de Python

```bash
# Instalar dependencias del proyecto
pip install -r requirements.txt
```

**Nota:** No hay dependencias adicionales no documentadas. Todas las dependencias están en `requirements.txt`.

### Configuración de Variables de Entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
# MongoDB
MONGO_URI=mongodb://usuario:password@host:27017/
MONGO_DB=sat_cfdi

# AWS S3
AWS_ACCESS_KEY_ID=tu_access_key
AWS_SECRET_ACCESS_KEY=tu_secret_key
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET=satisfacture

# Configuración de la API
API_HOST=0.0.0.0
API_PORT=8000
```

### Migraciones

Este proyecto **no requiere migraciones de base de datos** tradicionales ya que utiliza MongoDB (base de datos NoSQL orientada a documentos).

Las colecciones se crean automáticamente cuando se insertan los primeros documentos. Sin embargo, puedes crear índices para mejorar el rendimiento:

```python
# Script opcional para crear índices (ejecutar una sola vez)
from pymongo import MongoClient, ASCENDING

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

# Crear índices en la colección de solicitudes
db.solicitudes.create_index([
    ("rfc", ASCENDING),
    ("fecha_inicio", ASCENDING),
    ("fecha_fin", ASCENDING)
])

# Crear índices en la colección de paquetes
db.paquetes.create_index([("id_paquete", ASCENDING)])
```

### Pruebas Unitarias

**Actualmente no hay pruebas unitarias implementadas en el código.**

Se recomienda agregar pruebas utilizando `pytest`:

```bash
# Para implementar pruebas en el futuro
pip install pytest pytest-asyncio httpx

# Ejecutar pruebas (cuando estén implementadas)
pytest tests/ -v
```

### Iniciar el Proyecto

#### Modo Desarrollo (Local)

```bash
# Iniciar el servidor con auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

El servidor estará disponible en:
- API: http://localhost:8000
- Documentación interactiva (Swagger): http://localhost:8000/docs
- Documentación alternativa (ReDoc): http://localhost:8000/redoc

#### Con Docker (Desarrollo)

```bash
# Construir la imagen
docker build -t sat-api .

# Ejecutar el contenedor
docker run -p 8000:8000 --env-file .env sat-api
```

#### Con Docker (Producción - AWS ECS)

```bash
# 1. Autenticarse en Amazon ECR
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    423623837880.dkr.ecr.us-east-1.amazonaws.com

# 2. Construir la imagen
docker build -t sat-api .

# 3. Etiquetar la imagen
docker tag sat-api:latest \
    423623837880.dkr.ecr.us-east-1.amazonaws.com/sat-api:latest

# 4. Subir la imagen al registro
docker push 423623837880.dkr.ecr.us-east-1.amazonaws.com/sat-api:latest

# 5. Forzar nuevo deployment en ECS
aws ecs update-service \
    --cluster sat-api \
    --service sat-api-service \
    --force-new-deployment
```

## Arquitectura del Sistema

### Modelo de Datos

#### Jerarquía de Usuarios

```
Usuario (role: "cliente" | "admin")
    └── Grupo (opcional, según plan contratado)
        └── Cliente (RFC)
            ├── Certificados FIEL
            ├── Tokens SAT
            └── Años Fiscales (2023, 2024, 2025...)
                ├── Solicitudes
                └── Paquetes (CFDI + Metadata)
```

#### Colecciones de MongoDB

**1. usuarios**
```javascript
{
  _id: ObjectId,
  username: String,
  password_hash: String,  // Hasheado con bcrypt
  role: String,           // "cliente" | "admin"
  active: Boolean,
  created_at: DateTime,
  group_id: ObjectId      // Opcional
}
```

**2. grupos**
```javascript
{
  _id: ObjectId,
  nombre: String,
  slug: String,
  miembros: [ObjectId],   // Array de user IDs
  creado_en: DateTime
}
```

**3. clientes**
```javascript
{
  _id: ObjectId,
  rfc: String,            // RFC del contribuyente
  creado_en: DateTime,
  grupo_id: ObjectId,     // Opcional
  razon_social: String
}
```

**4. solicitudes**
```javascript
{
  _id: ObjectId,
  rfc: String,
  id_solicitud: String,           // UUID del SAT
  tipo_solicitud: String,         // "cfdi" | "metadata"
  tipo_comp: String,              // "E" (Emitidos) | "R" (Recibidos)
  tipo_cfdi: String | null,       // null = ALL
  estado_cfdi: String,            // "ALL" | "Vigente" | "Cancelado"
  fecha_inicio: String,           // YYYY-MM-DD
  fecha_fin: String,              // YYYY-MM-DD
  fecha_inicio_efectiva: DateTime,
  fecha_fin_efectiva: DateTime,
  intento: Number,                // Número de intento (máx 2 por el SAT)
  offset_segundos: Number,
  retokenizado: Boolean,
  reintentos_404: Number,
  fecha_solicitud: DateTime,
  estado: String,                 // "pendiente" | "descargado"
  paquetes: [String],             // IDs de paquetes descargados
  dividida_de: ObjectId | null    // Cuando una solicitud se estanca se divide
}
```

**5. cfdi**
```javascript
{
  _id: ObjectId,
  cliente: String,                // RFC del cliente
  uuid: String,                   // UUID del CFDI
  fechaProcesado: DateTime,
  xml: Object                     // Estructura completa del CFDI parseada
}
```

**6. metadata**
```javascript
{
  _id: ObjectId,
  Uuid: String,
  RfcEmisor: String,
  NombreEmisor: String,
  RfcReceptor: String,
  NombreReceptor: String,
  RfcPac: String,
  FechaEmision: String,
  FechaCertificacionSat: String,
  Monto: String,
  EfectoComprobante: String,      // "I" (Ingreso) | "E" (Egreso) | "P" (Pago)
  Estatus: String,                // "1" (Vigente) | "0" (Cancelado)
  FechaCancelacion: String,
  cliente: String,
  archivoZip: String,             // Ruta en S3
  fechaProcesado: DateTime
}
```

**7. uploads**
```javascript
{
  _id: ObjectId,
  rfc: String,
  uploader_username: String,
  uploader_name: String,
  group_id: ObjectId,
  consent_registered: Boolean,    // Aceptación de términos y condiciones
  status_code: Number,
  created_at: DateTime
}
```

### Estructura de Almacenamiento en S3

#### Estructura Actual

```
bucket: satisfacture/
├── clientes/
│   └── {RFC}/
│       ├── certificados/
│       │   ├── cert.pem         # Certificado FIEL convertido
│       │   ├── fiel.pem         # Llave privada FIEL
│       │   └── password.txt     # Contraseña de la FIEL
│       ├── tokens/
│       │   └── token.txt        # Token de autenticación SAT
│       └── {YEAR}/              # 2023, 2024, 2025...
│           ├── solicitudes/
│           │   ├── solicitudes.txt  # Lista de IDs de solicitudes
│           │   ├── paquetes.txt     # Lista de IDs de paquetes listos
│           │   └── id_solicitud.txt
│           └── paquetes/
│               └── cfdi/        # ZIPs de CFDI y metadata descargados
```

#### Estructura Futura (Roadmap)

```
bucket: satisfacture/
├── clientes/
│   └── {RESPONSABLE}/       # Responsable/administrador
│       ├── grupos/              # Solo para personas morales
│       │   └── {NOMBRE_GRUPO}/
│       │       └── {RFC_PM}/    # RFC de cada persona moral del grupo
│       │           ├── certificados/
│       │           └── {YEAR}/
│       └── certificados/        # Si es persona física sin grupo
```

### Estados de Solicitud SAT

| Estado | Código | Descripción |
|--------|--------|-------------|
| Aceptada | 1 | Solicitud recibida por el SAT |
| En Proceso | 2 | SAT está generando los paquetes |
| Terminada | 3 | Paquetes listos para descarga |
| Error | 4 | Error en el procesamiento |
| Rechazada | 5 | Solicitud rechazada (no hay CFDI para el periodo o error en parámetros) |
| Vencida/Caducada | 6 | Más de 7 días sin descarga (los paquetes expiran) |

**Estado adicional del sistema:**
- `descargado`: Paquetes descargados y procesados exitosamente en nuestra BD

## Estructura del Proyecto

```
.
├── app/
│   ├── main.py                         # Punto de entrada de la aplicación FastAPI
│   ├── routes.py                       # Definición de endpoints de la API
│   └── services/
│       ├── sat_service.py              # Lógica de integración con Web Services del SAT
│       ├── s3_service.py               # Operaciones con Amazon S3
│       ├── mongo_service.py            # Operaciones con MongoDB
│       ├── download_sat_packages.py    # Descarga los paquetes del SAT
│       └── cfdi_processing_service.py  # Procesa los zip devueltos por el SAT
├── Dockerfile                          # Configuración de contenedor Docker
├── requirements.txt                    # Dependencias de Python
├── .env                                # Variables de entorno (no incluir en git)
├── .gitignore                          # Archivos a ignorar en git
├── config.yml                          # URLs proporcionados por el SAT
└── README.md                           # Este archivo
```

## Flujo del Sistema

### Flujo Automatizado (Objetivo)

```
1. Usuario sube FIEL
   ↓
2. Sistema almacena certificados en S3
   ↓
3. Sistema determina estrategia de descarga según tamaño de empresa:
   - Grande: Solicitudes diarias (por día)
   - Mediana: Solicitudes semanales (por semana)
   - Pequeña: Solicitudes mensuales (por mes)
   ↓
4. Sistema genera solicitudes automáticas al SAT:
   - Año a analizar: 2024
   - CFDI Emitidos: 12 solicitudes (una por mes)
   - CFDI Recibidos: 12 solicitudes (una por mes)
   - Metadata Emitidos: 2 solicitudes (ene-jun, jul-dic)
   - Metadata Recibidos: 2 solicitudes (ene-jun, jul-dic)
   - Total por año: 28 solicitudes
   ↓
5. Sistema verifica estado de solicitudes periódicamente
   ↓
6. Cuando estado = 3 (Terminada), descarga paquetes automáticamente
   ↓
7. Procesa ZIPs y almacena:
   - XMLs → Colección cfdi
   - TXTs → Colección metadata
   ↓
8. Usuario puede consultar datos procesados instantáneamente de CFDI
   Para metadata el tiempo de espera son 6 días
```

### Flujo Manual (Actual - Desarrollo)

1. **Convertir a .pem:** `POST /convert-and-upload-certificates/`
2. **Autenticar con el SAT:** `POST /auth-sat/`
3. **Solicitar descarga:** `POST /solicitar-cfdi/`
4. **Verificar estado:** `POST /verificar-solicitudes/` (verificar si estado = 3)
5. **Descargar paquetes:** `POST /descargar-paquetes/`
6. **Analizar un año:** `POST /ejecutar-solicitudes-iniciales/` (Solicitudes de n, n-1 y n+1 primeros 3 meses)
7. **Procesar archivos:** `POST /procesar-cfdi/`

### Estrategia de Descarga según Tamaño

El tamaño de empresa se determina al momento del registro del contribuyente basándose en el giro empresarial:

| Tamaño | Giro Ejemplo | Frecuencia de Solicitudes | Solicitudes/Año |
|--------|--------------|---------------------------|-----------------|
| **Grande** | Gasolineras, Retail, E-commerce | Diaria (1 por día) | ~1,095+ |
| **Mediana** | Servicios profesionales, Manufactura | Semanal (1 por semana) | ~52 |
| **Pequeña** | Autónomos, Pequeños negocios | Mensual (1 por mes) | 12 |

**Razón técnica:** Los paquetes CFDI del SAT tienen un límite de ~10MB. Empresas grandes generan paquetes que exceden este límite, por lo que se requieren periodos más cortos.

### Alcance Temporal de Descarga

Cuando se ejecuta `/ejecutar-solicitudes-iniciales/` para analizar un año fiscal, el sistema descarga:

- **Año anterior completo** (ej. 2023 si se analiza 2024)
- **Año solicitado completo** (ej. 2024)
- **Primeros 3 meses del año siguiente** (ej. ene-mar 2025)

Esto permite análisis de comparación anual y captura de facturas con fecha de emisión retrasada.

## Endpoints Principales

### Autenticación

#### `POST /auth-sat/`

Autentica usuario ante el SAT y devuelve token.

**Form Data:**
- `rfc`: RFC del contribuyente

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Gestión de FIEL

#### `POST /convert-and-upload-certificates/`

Sube certificados FIEL del contribuyente a S3.

**Form Data:**
- `rfc`: RFC del contribuyente
- `cert_file`: Archivo .cer (certificado)
- `key_file`: Archivo .key (llave privada)
- `password`: Contraseña de la llave privada

**Response:**
```json
{
  "status": "success",
  "message": "FIEL almacenada correctamente",
  "s3_paths": {
    "cert": "clientes/RFC123456/certificados/cert.pem",
    "key": "clientes/RFC123456/certificados/fiel.pem"
  }
}
```

### Solicitudes SAT

#### `POST /solicitar-cfdi/`

Crea una solicitud de descarga masiva en el SAT.

**Form Data:**
- `rfc`: "RFC123456789"
- `inicio`: "2024-01-01" (Fecha inicio)
- `fin`: "2024-01-31" (Fecha fin)
- `tipo_solicitud`: "CFDI" ("CFDI" | "Metadata")
- `tipo_comprobante`: "E" ("E" Emitidos | "R" Recibidos)
- `tipo_cfdi`: null (null = ALL, o "I","E","P","N","T")
- `estado_cfdi`: "ALL" ("ALL" | "Vigente" | "Cancelado")

**Response:**
```json
{
  "status": "success",
  "id_solicitud": "96cc1ecb-4e8b-4016-b55c-1e26c7cc1a69",
  "codigo_estado": "5000",
  "mensaje": "Solicitud Aceptada"
}
```

**Códigos de respuesta SAT:**
- `5000`: Solicitud aceptada
- `5001`: Tercero no autorizado
- `5002`: Límite de solicitudes alcanzado (máx 2 con mismos criterios)
- `5005`: Ya existe una solicitud con los mismos criterios

#### `POST /verificar-solicitudes/`

Verifica el estado de una solicitud previamente realizada.

**Form Data:**
- `rfc`: "RFC123456789"
- `year`: "2024" (Año)

**Response (Estado 1 - Aceptada):**
```json
{
  "message": "Verificacion completada",
  "resultados": [
    {
      "id_solicitud": "96cc1ecb-4e8b-4016-b55c-1e26c7cc1a69",
      "estado": "1",
      "codigo_estados": "5000",
      "numero_cfdis": "0",
      "paquetes": []
    }
  ]
}
```

**Response (Estado 3 - Terminada):**
```json
{
  "message": "Verificacion completada",
  "resultados": [
    {
      "id_solicitud": "96cc1ecb-4e8b-4016-b55c-1e26c7cc1a69",
      "estado": "3",
      "codigo_estados": "5000",
      "numero_cfdis": "23",
      "paquetes": [
        "96CC1ECB-4E8B-4016-B55C-1E26C7CC1A69_01",
        "96CC1ECB-4E8B-4016-B55C-1E26C7CC1A69_02"
      ]
    }
  ]
}
```

#### `POST /descargar-paquetes/`

Descarga los paquetes de una solicitud completada (estado = 3).

**Form Data:**
- `rfc`: "RFC123456789"
- `year`: "2024" (Año)

**Response:**
```json
{
  "status": "Descarga Completa"
}
```

## Características Técnicas Especiales

### 1. Manejo Robusto de XML Grandes

El SAT puede devolver paquetes con archivos XML extremadamente grandes (>10MB) que exceden los límites por defecto de los parsers XML. El sistema implementa una estrategia dual:

**Estrategia de Parsing:**

```python
# 1. Intento con parser robusto (Implementado)
parser = etree.XMLParser(
    huge_tree=True,      # Permite nodos de texto >10MB
    recover=True,        # Intenta recuperarse de errores
    encoding='utf-8'
)
tree = etree.fromstring(response.content, parser)

# 2. Fallback con regex si el parser falla
if parser_fails:
    # Extrae contenido Base64 del ZIP directamente con regex
    zip_content = re.search(r'<content>(.*?)</content>', xml_text)
```

**Problema resuelto:** Error "Resource limit exceeded: Text node too long, try XML_PARSE_HUGE"

### 2. Firma Digital con FIEL

Todas las peticiones SOAP al SAT deben estar firmadas digitalmente con el certificado FIEL (e.firma) del contribuyente.

**Conversión de certificados:**

```bash
# De .cer/.key (formato DER) a .pem
openssl x509 -inform DER -in certificado.cer -out cert.pem
openssl pkcs8 -inform DER -in llave.key -out fiel.pem
```

### 3. Gestión de Tokens SAT

Los tokens de autenticación del SAT tienen validez limitada (típicamente 10 minutos). El sistema implementará:

- Almacena tokens en S3 para compartir entre instancias ECS
- Verifica validez antes de cada operación
- Re-autentica automáticamente cuando expiran
- Implementa retry logic para manejar tokens expirados mid-request

### 4. Estrategia de Descarga Adaptativa

Para evitar el límite de 10MB por paquete del SAT, el sistema ajusta la granularidad de las solicitudes:

| Volumen de Facturas | Periodo de Solicitud | Paquetes/Año |
|---------------------|---------------------|--------------|
| Alto (>1000/mes) | Diario | ~365 |
| Medio (100-1000/mes) | Semanal | ~52 |
| Bajo (<100/mes) | Mensual | 12 |

### 5. Procesamiento Asíncrono

Las descargas del SAT pueden tardar varios minutos (especialmente metadata, hasta 6 días). El sistema implementará:

- Verificación periódica de estados (polling)
- Procesamiento en background para no bloquear la API
- Almacenamiento de estados intermedios en MongoDB

### 6. Almacenamiento Distribuido

**Por qué S3 en lugar de sistema de archivos local:**

- **Persistencia:** Los contenedores ECS son efímeros
- **Compartición:** Múltiples instancias acceden a los mismos certificados
- **Escalabilidad:** No depende del almacenamiento del contenedor
- **Backup:** S3 maneja versionado y durabilidad automáticamente

**Por qué MongoDB:**

- **Flexibilidad:** Estructura XML se mapea naturalmente a documentos JSON
- **Velocidad de consulta:** Índices eficientes para búsquedas por RFC, fecha, UUID
- **Análisis:** Agregaciones para reportes y estadísticas

### 7. Manejo de Límites del SAT

**Límite de solicitudes duplicadas:**

- El SAT solo permite **2 solicitudes** con los mismos criterios exactos
- A la tercera solicitud con mismos parámetros: rechazo permanente con los mismos criterios
- **Solución:** El sistema almacena TODAS las facturas en la primera descarga y hace queries locales

**Límite de descarga de paquetes:**

- Cada paquete solo se puede descargar **2 veces**
- Después de 7 días sin descarga: el paquete expira (estado 6)
- **Solución:** Descarga y almacenamiento inmediato en S3

**Límite de vigencia de solicitudes:**

- Estado 1 (Aceptada) → Estado 2 (En proceso) → Estado 3 (Terminada): típicamente 1-30 minutos para CFDI desde la solicitud
- Estado 1 → Estado 3: hasta 6 días para Metadata
- Si permanece en estado 1 por >7 días → Estado 6 (Caducada)

### 8. Seguridad

**Implementado:**

- ✅ Contraseñas hasheadas con bcrypt para el login de las demos en streamlit
- ✅ Autenticación JWT para endpoints de API
- ✅ HTTPS en tránsito (ECS Load Balancer)
- ✅ Validación de términos y condiciones (`consent_registered`)

**Roadmap de seguridad:**

- 🔲 Encriptación de FIELs en S3 con AWS KMS
- 🔲 Rotación automática de tokens JWT
- 🔲 Rate limiting por usuario/IP
- 🔲 Audit logs de acceso a FIELs
- 🔲 2FA para usuarios

### 9. Ventaja Competitiva: Velocidad

**SATisFacture vs Competencia (OneFacture, etc.):**

| Aspecto | SATisFacture | Competencia |
|---------|--------------|-------------|
| Solicitud CFDI | Segundos - Minutos | Horas |
| Descarga automática | Sí (background) | Manual |
| Procesamiento | Automático | Semi-manual |
| Re-descargas | No necesarias (todo en BD) | Frecuentes |
| Análisis | Minutos (desde BD local) | Días (descarga cada vez) |

**Razón técnica:** Almacenamiento local de todos los CFDI procesados vs solicitud al SAT en cada consulta.

## Ambientes de Desarrollo

### Ambientes Disponibles

| Ambiente | Descripción | Infraestructura | URL |
|----------|-------------|-----------------|-----|
| **Local** | Desarrollo y pruebas | Localhost | http://localhost:8000 |
| **Producción** | Sistema en vivo para usuarios | AWS ECS + Load Balancer | http://sat-api-alb-532045601.us-east-1.elb.amazonaws.com |

**Nota sobre URL de producción:** URL funcional. Agregar los endpoints desde Postman para probar, por ejemplo: `http://sat-api-alb-532045601.us-east-1.elb.amazonaws.com/auth-sat/`

**Nota:** No existe un ambiente de staging separado. Todas las pruebas se realizan localmente antes del deployment a producción.

### Deployment a Producción

El sistema de integración SAT corre en **AWS ECS (Elastic Container Service)**. Un sistema separado de procesamiento de XMLs manuales corre en **EC2**.

**Proceso de deployment:**

```bash
# 1. Pruebas locales
uvicorn app.main:app --reload

# 2. Build y push a ECR
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    423623837880.dkr.ecr.us-east-1.amazonaws.com

docker build -t sat-api .
docker tag sat-api:latest 423623837880.dkr.ecr.us-east-1.amazonaws.com/sat-api:latest
docker push 423623837880.dkr.ecr.us-east-1.amazonaws.com/sat-api:latest

# 3. Force new deployment en ECS
aws ecs update-service --cluster sat-api --service sat-api-service --force-new-deployment

# 4. Monitorear deployment
aws ecs describe-services --cluster sat-api --service sat-api-service
```

## Frontend e Interfaces

### Estado Actual

**Demo en Streamlit (Interna):**

- **Propósito:** Pruebas internas y validación de flujo UX
- **Usuarios:** Solo equipo de desarrollo
- **Funcionalidad:** Simulación del flujo completo de solicitud-descarga-procesamiento

**Frontend EC2 (Procesamiento Manual):**

- Sistema separado para subir XMLs sin FIEL
- No conectado al módulo SAT (ECS)
- En producción para usuarios

### Roadmap Frontend

**Frontend Web Completo (Planeado):**

- **Framework:** Por definir (React/Next.js probable)

**Funcionalidades para servicio del SAT:**

- Dashboard de análisis de precios de transferencia
- Gestión de FIELs y certificados
- Visualización de CFDI descargados
- Selector de RFCs para análisis
- Reportes y exportación
- Chat bot de ayuda integrado
- IA para insights

**Funcionalidades para gestión de contratos:**

- Alta de contratos (arrendamiento, financiamiento)
- Cálculo de Valor Presente, Amortización y Depreciación
- Editor de contratos
- Aplicador de tasa para contratos
- Dashboards interactivos

## Estrategia de Análisis de Transacciones

### Selector de RFCs para Análisis

Cuando un usuario quiere generar un análisis de precios de transferencia, puede seleccionar:

**Opción 1: RFCs del Grupo (Default)**

```
Usuario: Cesar (REM150313D57)
Grupo: REMYT
  ├── APT230814DW5 (Artículos Promocionales)
  ├── NAV090511KV8 (Naviyuc)
  └── REM150313D57 (Remyt)

→ El análisis incluirá automáticamente transacciones entre estos 3 RFCs
```

**Opción 2: RFCs Personalizados**

El usuario puede:

- Quitar RFCs del grupo
- Agregar RFCs externos con los que tuvo transacciones
- Guardar configuraciones de análisis

**Criterios de análisis:**

```json
{
  "analisis_id": "...",
  "periodo": {"inicio": "2024-01-01", "fin": "2024-12-31"},
  "rfc_base": "REM150313D57",
  "rol": "emisor",           // o "receptor" o "ambos"
  "rfcs_incluidos": [
    "APT230814DW5",
    "NAV090511KV8",
    "XYZ010101ABC"           // RFC externo al grupo
  ],
  "rfcs_excluidos": [
    "REM150313D57"           // Excluir a sí mismo
  ]
}
```

El sistema consulta la base de datos local (no al SAT) para análisis instantáneo.

## Límites y Restricciones

### Límites del SAT

#### 1. Solicitudes Duplicadas

- Máximo **2 solicitudes** con los mismos criterios exactos
- Tercera solicitud con mismos parámetros: **rechazo permanente**
- Aplica por: RFC + Fechas + Tipo + Comprobante + Estado

#### 2. Descargas de Paquetes

- Cada paquete se puede descargar **máximo 2 veces**
- Después: el paquete ya no está disponible

#### 3. Expiración de Paquetes

- Paquetes listos (estado 3) expiran en **72 horas** si no se descargan
- Después de 7 días en estado 1: solicitud pasa a estado 6 (Caducada)

#### 4. Tiempos de Procesamiento

- **CFDI:** 1-60 minutos (típicamente <5 minutos)
- **Metadata:** 1-6 días (típicamente 2-3 días)

#### 5. Tamaño de Paquetes

- Límite aproximado: **10MB por paquete**
- El SAT divide automáticamente en múltiples paquetes si excede

### Límites del Sistema

#### 1. Almacenamiento

- Sin límite hard-coded actualmente
- Dependiente de cuota de S3 y MongoDB Atlas

#### 2. Tasa de Requests

- Sin rate limiting implementado actualmente
- **Roadmap:** Implementar rate limiting por usuario

#### 3. Retención de Datos

- Con política de retención
- **Roadmap:** Definir política de retención y archivado

## Notas Importantes

### 1. Manejo de Certificados FIEL

**CRÍTICO - SEGURIDAD:**

Los certificados FIEL son **equivalentes a una firma autógrafa** y permiten realizar trámites fiscales oficiales en nombre del contribuyente.

**Mejores prácticas actuales:**

- Almacenados en S3 (no en código fuente)
- Usuario debe aceptar términos y condiciones
- Acceso restringido via IAM roles

**Mejoras de seguridad planeadas:**

- Encriptación con AWS KMS
- Logs de auditoría de acceso
- Opción de usar FIEL solo temporalmente (no almacenar)
- 2FA obligatorio para subir FIEL

**Responsabilidad del usuario:**

```
Al subir su FIEL a SATisFacture, el usuario acepta que:
1. El certificado será usado ÚNICAMENTE para descargar facturas del SAT
2. No se realizarán operaciones fiscales sin su consentimiento explícito
3. El certificado se almacenará de forma segura pero no encriptada (actualmente)
4. El usuario puede solicitar eliminación de su FIEL en cualquier momento
```

**Conversión de formatos:**

```bash
# Convertir certificado (.cer → .pem)
openssl x509 -inform DER -in certificado.cer -out cert.pem

# Convertir llave privada (.key → .pem)
openssl pkcs8 -inform DER -in llave.key -out fiel.pem
```

### 2. Estrategia de Almacenamiento

**Por qué almacenar todas las facturas localmente:**

1. **Límite del SAT:** Solo 2 solicitudes con mismos criterios
2. **Velocidad:** Query a MongoDB es instantánea vs minutos/días del SAT
3. **Costo:** Solicitudes ilimitadas a BD propia vs límites del SAT
4. **Confiabilidad:** No dependemos de disponibilidad del SAT para consultas
5. **Análisis:** Podemos hacer agregaciones complejas sin restricciones

### 3. Metadata vs CFDI

**CFDI (XML completo):**

- Contiene TODOS los detalles del comprobante
- Tamaño: 5-50 KB por archivo
- Se usa para: Análisis detallado, contabilidad, auditorías
- Frecuencia de descarga: Mensual/semanal/diaria

**Metadata (archivo TXT):**

- Contiene solo campos clave del comprobante
- Tamaño: <1 KB por registro
- Se usa para: Verificar cancelaciones, sustituciones, validez
- Frecuencia de descarga: Semestral
- **Importancia crítica:** Identifica facturas canceladas

**Ambos son necesarios:** CFDI para análisis + Metadata para validación de estatus.

### 4. Diferencia con Otras Soluciones

| Característica | SATisFacture | Competencia |
|----------------|--------------|-------------|
| **Almacenamiento** | Local (BD propia) | Re-solicita al SAT cada vez |
| **Velocidad de análisis** | Segundos (query local) | Minutos/días (solicitud SAT) |
| **Límites de consulta** | Ilimitadas | 2 por criterio (SAT) |
| **Análisis histórico** | Instantáneo | Requiere nueva solicitud |
| **Costo de infraestructura** | Mayor (S3 + MongoDB) | Menor (sin almacenamiento) |
| **Dependencia del SAT** | Solo en descarga inicial | En cada consulta |

### 5. Tipos de Comprobantes

El SAT maneja múltiples tipos de CFDI:

| Tipo | Clave | Descripción | Uso Común |
|------|-------|-------------|-----------|
| **Ingreso** | I | Factura de venta | Venta de productos/servicios |
| **Egreso** | E | Nota de crédito | Devoluciones, descuentos |
| **Traslado** | T | Carta porte | Movimiento de mercancías |
| **Pago** | P | Complemento de pago | Pagos diferidos |
| **Nómina** | N | Recibo de nómina | Pago a empleados |

Para precios de transferencia, los más relevantes son **Ingreso (I)** y **Egreso (E)**.

### 6. Consideraciones de Timezone

- El SAT usa **horario del centro de México (CST/CDT)**
- Las fechas en MongoDB se almacenan en **UTC**
- Las fechas mostradas al usuario deben convertirse a su timezone local
- Al hacer solicitudes al SAT, las fechas deben estar en formato: `YYYY-MM-DDTHH:MM:SS`

## Monitoreo y Observabilidad

### CloudWatch Logs (AWS)

Los logs de la aplicación en AWS ECS están disponibles en CloudWatch Logs.

### Métricas Importantes

**Monitorear:**

- Errores de parsing XML: "Text node too long"
- Errores de autenticación: "Token expirado"
- Errores del SAT: Códigos 5001, 5002, 5005
- Timeouts en descarga de paquetes (>5 minutos)
- Errores de conexión a MongoDB
- Errores de conexión a S3

## Troubleshooting

### Problemas Comunes

#### 1. Error: "Resource limit exceeded: Text node too long"

**Causa:** Paquete SAT con XML >10MB que excede límites del parser.

**Solución:** Ya implementada con parser robusto y fallback a regex.

#### 2. Error: "Token expirado" / "401 Unauthorized"

**Causa:** El token SAT tiene validez limitada (~10 minutos).

**Solución:** Reautenticar (actualmente manual con `/auth-sat/`)

#### 3. Error: "5002 - Límite de solicitudes alcanzado"

**Causa:** Ya se hicieron 2 solicitudes con los mismos criterios exactos.

**Solución:**

- Cambiar ligeramente los criterios (ej. ajustar fecha_fin en 1 segundo)
- O consultar la base de datos local en lugar de hacer nueva solicitud al SAT

#### 4. Solicitud permanece en estado 1 por mucho tiempo

**Causa normal:** Metadata puede tardar hasta 6 días en procesarse. En caso de estancarse realizar solicitud nuevamente.

**Causa anormal:** El SAT puede tener problemas de saturación.

#### 5. MongoDB connection timeout

**Causa:** MongoDB Atlas puede estar inaccesible o IP no whitelisted.

**Solución:** Verificar conectividad y configuración de whitelist en MongoDB Atlas.

### Scripts de Diagnóstico

#### Verificar salud del sistema

```python
# health_check.py
import requests
from pymongo import MongoClient
import boto3

# 1. Verificar API
response = requests.get("http://sat-api-alb-532045601.us-east-1.elb.amazonaws.com/health")
print(f"API Status: {response.status_code}")

# 2. Verificar MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
count = db.solicitudes.count_documents({})
print(f"Solicitudes en BD: {count}")

# 3. Verificar S3
s3 = boto3.client('s3')
response = s3.list_objects_v2(Bucket='satisfacture', Prefix='clientes/', MaxKeys=1)
print(f"S3 accesible: {'Contents' in response}")
```

#### Limpiar solicitudes caducadas

**Aún no implementado**

## Performance y Optimización

**Aún no implementado** - Ver sección de Roadmap

### Optimizaciones de Consulta

**Aún no implementado**

### Caché

**Roadmap** - Implementación futura con Redis

## Soporte y Referencias

### Documentación Oficial del SAT

- **Portal del SAT - Factura Electrónica:** [https://www.sat.gob.mx/aplicacion/operacion/31274/consulta-y-recuperacion-de-comprobantes](https://www.sat.gob.mx/aplicacion/operacion/31274/consulta-y-recuperacion-de-comprobantes)
- **Documentación Web Services:** Ver carpeta `/documentacion/actualizacion` de este proyecto para obtener las más recientes
  - `0_URLs_WS_Descarga_Masiva_V1_5_VF.pdf`
  - `1_WS_Solicitud_Descarga_Masiva_V1_5_VF.pdf`
  - `2_WS_Verificacion_de_Descarga_Masiva_V1_5_VF.pdf`
  - `3_WS_Descarga_de_Solicitudes_Exitosas_V1_5_VF.pdf`

### Recursos Técnicos

- **lxml documentation:** [https://lxml.de/](https://lxml.de/)
- **xmlsec Python bindings:** [https://pypi.org/project/xmlsec/](https://pypi.org/project/xmlsec/)
- **FastAPI documentation:** [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
- **MongoDB Python Driver:** [https://pymongo.readthedocs.io/](https://pymongo.readthedocs.io/)
- **AWS ECS documentation:** [https://docs.aws.amazon.com/ecs/](https://docs.aws.amazon.com/ecs/)

### Preguntas Frecuentes

**P: ¿Por qué necesito subir mi FIEL?**

R: La FIEL es requerida por el SAT para autenticar que eres el contribuyente legítimo y tienes derecho a descargar tus comprobantes fiscales. Sin ella, no es posible acceder a los Web Services del SAT.

**P: ¿Es seguro subir mi FIEL?**

R: Actualmente las FIELs se almacenan en S3 sin encriptación adicional. Estamos trabajando en implementar encriptación con AWS KMS. Si tienes preocupaciones de seguridad, puedes optar por subir tus XMLs manualmente sin proporcionar la FIEL.

**P: ¿Puedo usar mi FIEL para múltiples RFCs?**

R: No. Cada RFC requiere su propia FIEL única. Si administras múltiples contribuyentes, necesitarás la FIEL de cada uno.

**P: ¿Qué pasa si mi FIEL expira?**

R: Necesitarás renovarla con el SAT y subir la nueva versión a la plataforma. Las descargas existentes seguirán disponibles, pero no podrás hacer nuevas solicitudes con la FIEL expirada.

**P: ¿Por qué tarda tanto la descarga de Metadata?**

R: El SAT procesa solicitudes de Metadata de forma diferente a CFDI. Mientras que los CFDI están listos en minutos, la Metadata puede tardar de 1 a 6 días porque el SAT valida el estatus de cada comprobante.

**P: ¿Puedo descargar facturas de años anteriores a 2023?**

R: Sí, el SAT permite descargar facturas desde 2014 (cuando comenzó el CFDI 3.3). Solo ajusta las fechas en tu solicitud.

**P: ¿Qué pasa si el SAT rechaza mi solicitud?**

R: Verifica los códigos de error:
- `5001`: RFC no autorizado (verifica tu FIEL)
- `5002`: Límite alcanzado (ya hiciste 2 solicitudes idénticas)
- `5005`: Solicitud duplicada (espera a que termine la anterior)

**P: ¿Puedo exportar mis datos?**

R: Sí, todos los XMLs están en MongoDB y pueden exportarse. Estamos trabajando en una funcionalidad de exportación masiva en el frontend.

## Equipo y Contacto

### Desarrollador Principal

- **Nombre:** César
- **Rol:** Data Engineer
- **Responsabilidades:** Backend SAT, infraestructura AWS, arquitectura

### Stack Técnico del Desarrollador

- **Backend:** Python, FastAPI, MongoDB
- **Cloud:** AWS (ECS, ECR, S3, CloudWatch)
- **DevOps:** Docker, Git
- **Especializaciones:** Integración SAT, procesamiento XML, análisis fiscal

### Contacto

- **Email:** apps@basterisreyes.com

## Roadmap General

### Completado

- [x] Integración Web Services SAT v1.5
- [x] Procesamiento de CFDI y Metadata
- [x] Almacenamiento en MongoDB + S3
- [x] Deployment en AWS ECS

### En Desarrollo

- [ ] Automatización completa de descarga
- [ ] Frontend web profesional

### Planeado

- [ ] Sistema de notificaciones
- [ ] Chat bot de ayuda
- [ ] Encriptación de FIELs con KMS
- [ ] Módulo de análisis de precios de transferencia
- [ ] Integración de IA para insights
- [ ] Generación automática de reportes
- [ ] Dashboard interactivo
- [ ] Multi-tenancy completo
- [ ] API pública
- [ ] Módulo de contratos de arrendamiento
- [ ] White-label para despachos

## Changelog

### [Versión Actual] - En Desarrollo

**Añadido:**

- Integración completa con Web Services SAT v1.5
- Descarga de CFDI y Metadata
- Procesamiento automático de XMLs
- Almacenamiento en MongoDB
- Manejo robusto de XMLs >10MB
- Firma digital con FIEL

**En Progreso:**

- Reestructuración
- Automatización de flujo completo
- Frontend web

**Conocido:**

- FIELs no están encriptadas en S3
- No hay pruebas unitarias
- No hay rate limiting

---

## Apéndice: Glosario

- **CFDI:** Comprobante Fiscal Digital por Internet - Factura electrónica oficial en México
- **FIEL:** Firma Electrónica Avanzada - Equivalente digital de firma autógrafa
- **SAT:** Servicio de Administración Tributaria - Autoridad fiscal de México
- **RFC:** Registro Federal de Contribuyentes - Identificador fiscal único
- **Metadata:** Datos resumen de CFDIs (sin contenido completo)
- **Precio de Transferencia:** Análisis fiscal de operaciones entre partes relacionadas
- **UUID:** Folio Fiscal único de cada CFDI
- **PAC:** Proveedor Autorizado de Certificación - Entidad que timbra CFDIs
- **Timbrado:** Proceso de certificación de un CFDI por el SAT

---

**SATisFacture** - Automatización fiscal inteligente 🇲🇽

Este sistema ha sido inspirado y desarrollado con base en la implementación de referencia:  
https://github.com/lunasoft/sw-descargamasiva-dotnet

*Última actualización: Noviembre 2025*
