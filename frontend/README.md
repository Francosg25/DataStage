# DataStage Web

Frontend Angular 21.2, Angular Material, TypeScript 5.9 y Chart.js. Las rutas cargan sus componentes bajo demanda. Todos los datos operativos se solicitan a la API; no se incluyen datos simulados.

## Desarrollo

El lock actual se comprobó con Node **24.13.1**. Angular 21 admite Node ^20.19.0, ^22.12.0 o ^24.0.0; `scripts/check_node.cjs` verifica también los requisitos y binarios de dependencias instaladas. En Windows usa `npm.cmd` para evitar el script PowerShell.

```sh
npm ci
npm start
```

La web se sirve en `http://127.0.0.1:4200` y reenvía `/api` y `/health` a `http://127.0.0.1:8000`. Ejecuta API y worker siguiendo el README de la raíz.

```sh
npm run build
npm test
```

La compilación de producción se genera en `dist/datastage-web/browser`. El paquete versionado copia este frontend ya compilado; Nginx lo sirve por HTTPS y reenvía `/api/` a `127.0.0.1:8000`. No se necesita Node en el servidor. La plantilla `deploy/linux/nginx.conf.template` permite 102 MiB, coordinados con los límites específicos de la API. Consulta [Linux directo](../docs/linux-direct.md).

## Autenticación

`GET /api/v1/config` decide el modo de autenticación. En desarrollo, el backend proporciona la identidad local y la aplicación muestra una advertencia visible. En modo Entra, MSAL obtiene el token y solo lo agrega a solicitudes `/api/` del mismo origen. Registra como URI SPA de redirección `https://<host>/login` en Microsoft Entra ID. El backend debe validar audiencia, emisor y permisos en cada operación. La interfaz no contiene secretos de cliente.

El asistente permanece deshabilitado si `foundryEnabled` es falso. Cuando está configurado usa conversaciones y mensajes reales de la API y muestra las evidencias devueltas.

## Validación

Las pruebas verifican selección de archivos, límites de tamaño, rutas que pueden recibir tokens, conservación de idempotencia, carga multipart, descarga autenticada y condiciones para finalizar el polling. La compilación comprueba los templates Angular en modo estricto.
