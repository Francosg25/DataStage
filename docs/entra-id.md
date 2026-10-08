# Entra ID: piloto corporativo

La guia para TI se mantiene en `docs/entra-id-primeros-pasos.txt`, se publica
mediante `frontend/scripts/sync-guides.mjs` y se descarga desde Administracion.
No requiere Azure CLI. La identidad de
Foundry y el inicio de sesion de usuarios son configuraciones diferentes.

## Estado y activacion

No se ha activado Entra ni se han creado recursos en el tenant. Se requieren
los identificadores y la aprobacion de TI. `scripts/start-dev.ps1` configura
autenticacion local para la demostracion y no es el lanzador del piloto SSO.

En un entorno de prueba autorizado, TI debe configurar las cuatro variables
`DATASTAGE_ENTRA_*` descritas en la guia, `DATASTAGE_AUTH_MODE=entra`, los
origenes CORS exactos y el proxy/API del frontend. Arrancar API y worker con
ese entorno, sin ejecutar `start-dev.ps1` sobre el mismo despliegue. Para
arranque manual, desde `backend` y con el entorno virtual activado:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Este ejemplo enlaza solo loopback; no publica el servicio en la red. Conservar
las rutas de BD, documentos y referencia existentes del entorno de prueba.
No conectar datos corporativos a un despliegue sin proteccion. El proceso de
despliegue de produccion debe cumplir ademas los requisitos de Settings.

La SPA usa MSAL, codigo con PKCE y almacenamiento de sesion; solicita el scope
configurado. La API verifica firma RS256, expiracion, emisor v2, audiencia,
tenant, scope delegado y roles. El ambito de datos lo fija el despliegue, nunca
un claim controlado por el cliente. No admite acceso app-only para sustituir
la sesion de una persona en estas rutas.

Un rol presente no implica todos los permisos: probar cada accion con cuentas
Reader y Operator independientes, y una cuenta sin asignacion. No cambiar al
modo development para resolver errores de un despliegue corporativo.
