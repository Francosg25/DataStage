# Mapas del proyecto

La ruta `/project-maps` es una seccion independiente bajo Asistente. Presenta las seis hojas de mapas (diapositivas 3 a 8) de `Fixed Asset ID Process & Progress - 11 August 2026.pptx`, sin importar sus datos como operaciones ni recalcular sus cifras. La portada, las instrucciones de la diapositiva 2 y el resumen de la diapositiva 9 no forman parte del visor.

Los PNG de 2880 x 1620, sus miniaturas y el manifiesto se incluyen como recursos del backend, nunca en `frontend/public`. `GET /api/v1/project-maps` y `GET /api/v1/project-maps/{id}/image?thumbnail=true|false` requieren identidad, rol de lectura y el ambito del despliegue. Solo se permiten identificadores del catalogo. Las respuestas llevan `Cache-Control: no-store`. En modo de desarrollo permanece el acceso de prueba limitado a loopback; en produccion se aplica Entra ID.

El cliente utiliza HttpClient con el interceptor corporativo, URL de objeto locales y liberacion al salir. Precarga las hojas vecinas. Ofrece anterior/siguiente, selector de hoja, miniaturas, zoom, ajuste, desplazamiento al ampliar, descarga PNG y pantalla completa. La animacion respeta `prefers-reduced-motion`; la navegacion por flechas, PageUp/PageDown y Home/End se limita al visor. El texto extraido de cada hoja esta disponible en un desplegable accesible.

Los titulos y controles se traducen ES/EN; el contenido del plano conserva el ingles original. La fecha y las cantidades son una captura historica de la presentacion, no un estado en vivo. No hay zonas interactivas ni edicion de cifras en esta version.

Para regenerar los recursos localmente, usar `scripts/export-project-maps.mjs` con Node y `ARTIFACT_NODE_MODULES` apuntando a las dependencias de artefactos del entorno. El script usa el renderizador de presentaciones incluido, conserva el archivo fuente y registra su SHA-256. No se requiere PowerPoint, Azure CLI ni el runtime de artefactos en el servidor de la aplicacion. Tras cambiar el catalogo se debe reiniciar la API.
