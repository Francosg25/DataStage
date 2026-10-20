# Despliegue principal: Linux directo

La instalación soportada por esta rama usa **Nginx/HTTPS + systemd + FastAPI + worker + SQL Server + Entra**. Foundry es opcional. No requiere contenedores, Node en producción ni un antivirus integrado.

Guía completa, responsabilidades y comandos: [docs/linux-direct.md](../docs/linux-direct.md).

- `linux/prepare-host.sh`: cuentas, directorios y servicios; ejecutado una sola vez por TI.
- `linux/*.service`: API/worker persistentes y migración separada por versión.
- `linux/*.env.example`: configuración externa y credenciales separadas.
- `linux/nginx.conf.template`: HTTPS, SPA y proxy API a loopback.
- `linux/release.py`: verificar, instalar y activar releases conservando datos/configuración.
- `../scripts/build_release.py`: construir paquete de código con frontend ya compilado.

Los anteriores archivos Docker/Compose/Kubernetes se retiran de esta rama para no mantener dos procedimientos contradictorios; siguen disponibles en el historial Git. No se ha ejecutado un despliegue de producción.
