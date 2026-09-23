# Validación de la implementación

Ejecutada el 22 de septiembre de 2026 (hora de México). Estado: aplicación funcional local; sustitución operativa de Office Scripts pendiente de certificar.

| Comprobación | Resultado |
|---|---|
| Backend completo: motor, exportación, API, worker, persistencia, autorización y Foundry | 198 pruebas aprobadas |
| Integración SQL Server real | 1 prueba omitida: falta conexión a una base de pruebas corporativa |
| Angular | 11 pruebas aprobadas y compilación de producción correcta |
| Calidad Python | Ruff aprobado; 57 versiones verificadas; pip check correcto |
| Migraciones | Upgrade/downgrade SQLite, comparación con metadata y DDL SQL Server offline aprobados |
| Contratos | OpenAPI generado con 21 rutas y 17 esquemas |
| Contenedores e infraestructura | Configuración Compose y manifiestos revisados; imágenes y despliegue no ejecutados |

La prueba con API y worker como procesos separados recibió dos ASC sintéticos y completó el mensual y el anual automático. Ambos produjeron dos tablas, tres filas, una advertencia de calidad y cero errores. Se descargaron los dos Excel. La evidencia local se conserva en `.data/qa-ui`, fuera del control de versiones. La aplicación de uso comienza vacía.

En navegador se verificaron dashboard conectado, navegación, formulario mensual, diseño de escritorio y consola sin errores. La automatización del selector de archivos quedó bloqueada; el envío se verificó por API y por pruebas de Angular, sin afirmar una prueba completa de carga mediante navegador.

Las pruebas cubren reintentos, conflicto entre publicaciones, aislamiento por ámbito, roles, validación JWT, cargas multipart sin Content-Length, ZIP malicioso, fechas, texto con ceros iniciales, deduplicación, limpieza de documentos sin referencia y consultas anuales contra resultados inmutables. El adaptador Foundry utiliza el SDK real con transporte simulado en las pruebas; no se llamó al servicio corporativo.

La salida JUnit del backend está en `.data/test-results/backend.xml`. Los tests usan carpetas temporales y datos sintéticos; no modifican los Excel entregados.

Antes del cambio operativo quedan cuatro comprobaciones externas: paridad con los ASC/ZIP y scripts originales; SQL Server real y volumen de producción; Entra ID/roles; Foundry y la infraestructura aprobada por IT. Las diferencias provisionales están en [compatibility.md](compatibility.md), y el despliegue en [deploy/README.md](../deploy/README.md).
