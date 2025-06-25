Funciones implementadas hasta el momento:

1. REGISTRO DE CLIENTES Y GESTIÓN DE CREDENCIALES
- Al registrar un nuevo cliente, se cargan los archivos .cer, .key y la contraseña de la FIEL.
- Estos archivos son convertidos automáticamente a formato .pem, y tanto los archivos como la contraseña son almacenados en AWS S3, en la ruta:
  s3://{BUCKET}/clientes/{RFC}/certificados/
- Esta ubicación es completamente privada y segura. Solo el propietario de la cuenta AWS tiene acceso a dicha ruta.
  Nadie más puede ver, descargar ni modificar estos archivos sin tus credenciales y permisos explícitos.
- AWS S3 ofrece una infraestructura de seguridad robusta:
  - Todos los archivos están **cifrados en reposo** mediante AES-256 y también en tránsito con HTTPS/TLS.
  - El acceso a objetos puede limitarse estrictamente mediante políticas IAM, bloqueando accesos externos y asegurando que ni siquiera usuarios internos puedan acceder sin autorización.
  - Se puede habilitar **SSE-S3** o cifrado con claves personales (**SSE-KMS**) para una capa adicional de protección.
  - Además, se ecuentra habilitado el **CloudTrail** para registrar quién accede, desde dónde y cuándo, con fines de auditoría.
- En la práctica, este entorno ofrece un nivel de seguridad igual o superior al almacenamiento físico o local, con la ventaja de ser completamente rastreable y redundante.
- Estos archivos son piezas críticas del proceso, ya que permiten la autenticación oficial ante el SAT. Su almacenamiento seguro y exclusivo en S3 garantiza la continuidad operativa sin comprometer la confidencialidad del cliente.


2. AUTENTICACIÓN CON EL SAT
- Utilizando los archivos .pem y la contraseña almacenada, se realiza el proceso de autenticación.
- Se genera un token válido ante el SAT, el cual es guardado como archivo `.txt` en la siguiente ruta:
  s3://{BUCKET}/clientes/{RFC}/tokens/token.txt
- Este token se reutiliza para hacer solicitudes, verificar y descargar sin repetir autenticaciones innecesarias.

3. ENVÍO DE SOLICITUDES CFDI/METADATA
Se han desarrollado dos tipos de solicitudes:

  a) Solicitud Individual
     - Permite al usuario elegir el tipo (CFDI o Metadata), el tipo de comprobante y el periodo deseado.

  b) Solicitud Masiva
     - Ejecuta 14 solicitudes automáticamente:
         • 2 solicitudes de Metadata (enero-junio y julio-diciembre)
         • 12 solicitudes de CFDI (una por mes)

- En ambos tipos las solicitudes se registran en:
    s3://{BUCKET}/clientes/{RFC}/{AÑO}/solicitudes/id_solicitud.txt

4. GESTIÓN DE ESTRUCTURA EN S3
Cuando se realiza una solicitud, se crea automáticamente la siguiente estructura:

s3://{BUCKET}/clientes/{RFC}/
  ├── certificados/            ← Archivos .pem y contraseña
  ├── tokens/                  ← Archivo con el token actual
  └── {AÑO}/
      ├── solicitudes/         ← id_solicitud.txt y paquetes.txt
      └── paquetes/
          ├── cfdi/            ← Descarga de CFDIs .zip con xml
          └── metadata/        ← Descarga de archivos .zip con txt (Por pulir)

5. VERIFICACIÓN DE SOLICITUDES
- Una vez autenticados, se verifican los estados de todas las solicitudes activas.
- El SAT maneja los siguientes estados:
    • Estado 1: Solicitud aceptada y en proceso.
    • Estado 3: Solicitud lista, paquetes disponibles para descarga.
    • Estado 4: Solicitud excedió el límite permitido (200,000 CFDIs o 1 millón de Metadata).
- Se implementó una lógica de división automática por mes para evitar estado 4.

6. VERIFICACIÓN AVANZADA (NUEVO – POR IMPLEMENTAR)
- Si una solicitud permanece en estado 1 más de 4 días desde su fecha (`fecha_solicitud`), se considera estancada.
- En ese caso:
   a) Se genera automáticamente una nueva solicitud con los mismos parámetros.
   b) Se elimina la solicitud anterior de la base de datos.
   c) Se registra la nueva en su lugar, evitando duplicidad y bloqueos.
- Esto permite mantener el sistema limpio, actualizado y confiable.

7. DESCARGA DE PAQUETES
- Cuando una solicitud pasa a estado 3, los paquetes .zip son descargados del SAT.
- Se almacenan en:
  s3://{BUCKET}/clientes/{RFC}/{AÑO}/paquetes/cfdi/
  s3://{BUCKET}/clientes/{RFC}/{AÑO}/paquetes/metadata/

8. PROCESAMIENTO DE PAQUETES (CFDI Y METADATA)
Una vez descargados los .zip, se procesan directamente:

  a) CFDI:
     - Archivos .xml se convierten a JSON con estructura completa utilizando `xmltodict`.
     - Se guarda en la colección `cfdi` en MongoDB, junto con:
        • cliente (RFC)
        • uuid
        • fechaProcesado
        • xml completo

  b) Metadata:
     - Archivos .txt son separados por `~` conforme al estándar del SAT.
     - Cada línea se transforma en un documento JSON.
     - Se guarda en la colección `metadata` con:
        • Uuid, RfcEmisor, RfcReceptor, Monto, Estatus, etc.
        • cliente, nombre del zip, fechaProcesado

9. BASE DE DATOS (MongoDB)
- Cada solicitud enviada es registrada en MongoDB.
- Se valida que no exista una solicitud con los mismos parámetros (RFC, tipo, fechas).
- En caso de duplicado, se evita reenviarla para cumplir con las políticas del SAT.

10. PRUEBAS REALIZADAS
- Se han ejecutado pruebas completas utilizando Postman para cada endpoint.
- Se validó la autenticación, envío de solicitudes, verificación de estados, descarga de paquetes y procesamiento sin errores.
- Se confirmó el control de duplicados tanto en solicitudes como en documentos CFDI/Metadata mediante validación por `uuid`.


11. Estructura de Almacenamiento en S3:

s3://{Nombre del Bucket (confidencial)}/clientes/
  └── {RFC}/
       ├── certificados/
       ├── tokens/
       └── {AÑO}/
            ├── solicitudes/
            │    ├── id_solicitud.txt
            │    ├── paquetes.txt
            └── paquetes/
                 ├── cfdi/
                 └── metadata/


PRÓXIMOS PASOS
1. Automatización con AWS EventBridge o APScheduler para ejecutar verificación y descarga diaria a las 11:00 PM.
2. Documentación técnica detallada y protección de la API con autenticación segura (API Key o JWT).
3. Desarrollo de frontend visual para carga de archivos, gestión de solicitudes y descargas.
4. Implementación de dashboards para monitoreo de solicitudes, estado de verificación y métricas.
5. Pruebas unitarias e integración continua para garantizar calidad.
6. Interfaz web para descarga directa de paquetes.
7. Despliegue productivo en infraestructura segura y escalable.


* ESTADO ACTUAL
El proyecto se encuentra en evolución constante, con avances significativos a pesar de los tiempos de espera inherentes al SAT, los cuales introducen pausas operativas naturales. No obstante, se han consolidado cimientos técnicos robustos que permiten la automatización y escalabilidad del sistema.

Actualmente, se ha alcanzado un nivel funcional completo en los módulos de descarga, verificación y procesamiento tanto de CFDIs como de su metadata. Entre las funcionalidades clave ya implementadas se encuentran:

- Control inteligente de duplicados, evitando reprocesamiento innecesario.
- Reemplazo automático de solicitudes estancadas, asegurando continuidad operativa sin intervención manual.
- Infraestructura escalable, con almacenamiento optimizado en Amazon S3 y persistencia estructurada en MongoDB, lo que facilita el crecimiento a gran escala del volumen de información procesada.

Este sistema ha sido inspirado y desarrollado con base en la implementación de referencia:  
https://github.com/lunasoft/sw-descargamasiva-dotnet
