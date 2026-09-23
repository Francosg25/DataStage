import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.api import router
from app.core.config import Settings
from app.core.body_limit import BodyLimitMiddleware
from app.core.errors import ApplicationError
from app.core.logging import configure_logging
from app.modules.storage.filesystem import FileSystemStorage
from app.persistence import Base, make_engine, session_factory

log = logging.getLogger("datastage.api")

def create_app(settings=None):
    settings = settings or Settings()
    if settings.database_url.startswith("sqlite:///") and ":memory:" not in settings.database_url:
        Path(settings.database_url.removeprefix("sqlite:///")).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    storage = FileSystemStorage(settings.document_root)
    @asynccontextmanager
    async def lifespan(app):
        if settings.environment in ("development", "test"):
            Base.metadata.create_all(engine)
        yield
        engine.dispose()
    app = FastAPI(title="DataStage API", version="0.1.0", lifespan=lifespan,
                  docs_url="/docs" if settings.environment != "production" else None, redoc_url=None)
    app.state.settings, app.state.engine = settings, engine
    app.state.session_factory, app.state.storage = session_factory(engine), storage
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
                       expose_headers=["Location", "Content-Disposition", "X-Correlation-ID"])
    app.add_middleware(BodyLimitMiddleware, upload_bytes=settings.max_upload_mb * 1024 * 1024,
                       source_bytes=settings.max_file_mb * 1024 * 1024)
    def problem(status, code, detail, request):
        return JSONResponse(status_code=status, media_type="application/problem+json",
            content={"type": f"urn:datastage:problem:{code.lower()}", "title": code, "status": status,
                     "detail": detail, "instance": request.url.path,
                     "correlationId": getattr(request.state, "correlation_id", "")})
    @app.exception_handler(ApplicationError)
    async def application_error(request, error):
        return problem(error.status, error.code, error.detail, request)
    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        return problem(409, "CONCURRENT_REQUEST", "Otra solicitud equivalente se registró; reintenta con la misma clave", request)
    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return problem(error.status_code, "HTTP_ERROR", str(error.detail), request)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        fields = ["/".join(map(str, item["loc"])) for item in error.errors()]
        return problem(422, "VALIDATION_ERROR", "Revisa los campos: " + ", ".join(fields), request)
    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        log.error("Error interno", exc_info=True, extra={"correlation_id": getattr(request.state, "correlation_id", "")})
        return problem(500, "INTERNAL_ERROR", "Ocurrió un error interno. Conserva el identificador de correlación.", request)
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.correlation_id = str(uuid4())
        started = perf_counter()
        response = None
        length = request.headers.get("content-length")
        maximum = max(settings.max_upload_mb, settings.max_file_mb) * 1024 * 1024 + 1024 * 1024
        if length:
            try:
                if int(length) > maximum:
                    response = problem(413, "REQUEST_TOO_LARGE", "La solicitud supera el tamaño permitido", request)
                elif int(length) < 0:
                    response = problem(400, "INVALID_CONTENT_LENGTH", "Longitud de solicitud no válida", request)
            except ValueError:
                response = problem(400, "INVALID_CONTENT_LENGTH", "Longitud de solicitud no válida", request)
        if response is None:
            response = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        log.info("HTTP request", extra={"correlation_id": request.state.correlation_id, "method": request.method,
                 "route": route, "status": response.status_code, "duration_ms": round((perf_counter() - started) * 1000, 2)})
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response
    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "alive"}
    @app.get("/health/ready", include_in_schema=False)
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM processing_runs WHERE 1=0"))
            if not storage.root.is_dir():
                return JSONResponse(status_code=503, content={"status": "not_ready"})
            return {"status": "ready"}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
    app.include_router(router)
    def openapi_schema():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes,
                                 description="API corporativa DataStage. En producción, token Entra ID y roles por aplicación.")
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["EntraBearer"] = {
                "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                "description": "Access token para la audiencia de esta API. El bypass local se limita a desarrollo y loopback."}
            for path, operations in schema["paths"].items():
                if path.startswith("/api/v1/") and path != "/api/v1/config":
                    for verb, operation in operations.items():
                        if verb in {"get", "post", "put", "patch", "delete"}:
                            operation["security"] = [{"EntraBearer": []}]
            app.openapi_schema = schema
        return app.openapi_schema
    app.openapi = openapi_schema
    return app

configure_logging()
app = create_app()
