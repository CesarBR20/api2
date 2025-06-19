Funciones implementadas hasta el momento:

- Conversión de certificado y key a formato .pem
- Autenticación ante el SAT:
	* Autenticación utilizando los archivos de la FIEL y generación del token.
	* El token se almacena para ser reutilizado en otros pasos.

- Solicitudes de CFDIs/Metadata:
	Actualmente se han desarrollado dos maneras de enviar solicitudes al SAT:
	1. Solicitud individual: se especifica el tipo de solicitud (Metadata o CFDI), el tipo de comprobante (E = Emitidos), y el periodo deseado.
	2. Solicitud masiva (14 solicitudes en un solo clic): se envían 2 solicitudes de Metadata (una por semestre) y 12 solicitudes de CFDI (una por mes).

- Verificación de Solicitudes:
	* Se realiza un nuevo proceso de autenticación para obtener un token actualizado.
	* Una vez autenticados, se verifican las solicitudes para identificar cuáles paquetes están listos (el paquete es un archivo ZIP que contiene los CFDIs correspondientes a una solicitud).
	* El SAT maneja distintos estados para las solicitudes. Los más relevantes para este proyecto son:
		- Estado 1: La solicitud fue aceptada y está en proceso. Se recomienda esperar hasta 48 horas según pruebas anteriores.
		- Estado 3: El SAT ya generó los paquetes y están listos para descargarse.
		- Estado 4: Se excedió el límite de CFDIs permitido (200,000 para CFDI y 1 millón para Metadata). En este caso, es necesario dividir la solicitud.
	* Se implementó lógica para prevenir el estado 4 dividiendo automáticamente por mes. Si aún así se excede, se activa una función que subdivide y reenvía la solicitud.
	* El proceso de automatización de verificación y descarga está pendiente. Se planea ejecutar diariamente a las 11:00 PM utilizando AWS EventBridge o APScheduler.

- Descarga de Paquetes:
	* Una vez que una solicitud pasa al estado 3, se realiza la descarga del paquete desde el SAT.
	* Los archivos se almacenan en la carpeta correspondiente en S3, organizada por cliente (RFC) y por año.

- Base de Datos:
	* Se utiliza MongoDB para registrar todas las solicitudes realizadas.
	* Antes de enviar una nueva solicitud, se verifica si ya existe una con los mismos parámetros (RFC, tipo de solicitud, tipo de comprobante, fecha de inicio y fin).
	* Si ya existe, se bloquea el reenvío para evitar errores y posibles sanciones por parte del SAT.

- Bucket:
	* Se utiliza el servicio AWS S3 para almacenar los archivos descargados de forma estructurada y organizada por cliente y año.

Estructura de Almacenamiento en S3:
s3://{Nombre del Bucket (confidencial)}/clientes/
  └── {RFC}/
       ├── certificados/
       ├── tokens/
       └── {AÑO}/
            ├── solicitudes/
            │    ├── id_solicitud.txt
            │    ├── paquetes.txt
            │    └── historial.csv (opcional)
            └── paquetes/
                 ├── cfdi/
                 └── metadata/

Pruebas Realizadas:
- Las pruebas de endpoints se han hecho utilizando Postman, validando el comportamiento esperado en distintos escenarios: envío de solicitudes, verificación, validación contra duplicados, y descarga de paquetes.


Next Steps:
1. Automatizar verificación y descarga diaria con AWS EventBridge o APScheduler (11:00 PM).
2. Documentación y apertura segura de la API.
3. Desarrollo del frontend para facilitar el uso por parte de usuarios finales.
4. Implementación de dashboards para monitoreo visual de solicitudes y descargas.
5. Integración de pruebas automáticas (unitarias y de integración).
6. Descarga directa desde interfaz.
7. Preparación para despliegue (deployment) en entorno productivo.

Este proyecto está en avance constante, aunque condicionado a los tiempos de respuesta del SAT, lo que impone pausas naturales. Aun así, se han establecido bases sólidas para automatizar y escalar el proceso.  
Este sistema ha sido inspirado y desarrollado con base en la implementación de referencia:  
https://github.com/lunasoft/sw-descargamasiva-dotnet
