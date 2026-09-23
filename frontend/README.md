# DataStage Web

Frontend Angular 22.1, Angular Material, TypeScript 6 y Chart.js. Las rutas cargan sus componentes bajo demanda. Todos los datos operativos se solicitan a la API; no se incluyen datos simulados.

## Desarrollo

Requiere Node **22.22.3+ en la rama 22, 24.15+ en la rama 24, o 26+** y npm. La versión 22.14 de Node no es compatible con Angular 22.

```sh
npm ci
npm start
```

La web se sirve en `http://127.0.0.1:4200` y reenvía `/api` y `/health` a `http://127.0.0.1:8000`. Ejecuta API y worker siguiendo el README de la raíz.

```sh
npm run build
npm test
```

La compilación de producción se genera en `dist/datastage-web/browser`. `Dockerfile` compila con Node 24 y sirve mediante Nginx sin usuario root en el puerto 8080. El servicio API debe resolverse como `api:8000` o ajustarse en `nginx.conf`. El límite Nginx de carga debe corresponder al configurado en la API (actualmente el proxy permite 256 MB).

## Autenticación

`GET /api/v1/config` decide el modo de autenticación. En desarrollo, el backend proporciona la identidad local y la aplicación muestra una advertencia visible. En modo Entra, MSAL obtiene el token y solo lo agrega a solicitudes `/api/` del mismo origen. Registra como URI SPA de redirección `https://<host>/login` en Microsoft Entra ID. El backend debe validar audiencia, emisor y permisos en cada operación. La interfaz no contiene secretos de cliente.

El asistente permanece deshabilitado si `foundryEnabled` es falso. Cuando está configurado usa conversaciones y mensajes reales de la API y muestra las evidencias devueltas.

## Validación

Las pruebas verifican selección de archivos, límites de tamaño, rutas que pueden recibir tokens, conservación de idempotencia, carga multipart, descarga autenticada y condiciones para finalizar el polling. La compilación comprueba los templates Angular en modo estricto.
