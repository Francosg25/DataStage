from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Request

from app.core.errors import ApplicationError


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    roles: frozenset[str]
    scope_id: str

    def require(self, *roles: str):
        if not self.roles.intersection(roles) and "Admin" not in self.roles:
            raise ApplicationError(403, "FORBIDDEN", "No tienes permiso para esta operación")


@lru_cache(maxsize=8)
def jwks_client(tenant: str):
    # Tenant is deployment configuration, never a claim-controlled URL.
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
                          cache_keys=True, lifespan=3600, timeout=10)


def current_principal(request: Request) -> Principal:
    settings = request.app.state.settings
    if settings.auth_mode == "development":
        if settings.environment not in ("development", "test"):
            raise ApplicationError(403, "DEV_AUTH_DISABLED", "La identidad local está deshabilitada")
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise ApplicationError(403, "LOCAL_ONLY", "La identidad de desarrollo solo acepta conexiones locales")
        return Principal("local-developer", "Desarrollo local", frozenset({"Reader", "Operator", "Reprocessor", "Auditor", "Admin"}), settings.scope_id)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise ApplicationError(401, "AUTH_REQUIRED", "Inicia sesión con Microsoft Entra ID")
    token = auth[7:]
    try:
        key = jwks_client(settings.entra_tenant_id).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=settings.entra_audience,
                            issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        if claims.get("tid") != settings.entra_tenant_id:
            raise ValueError("Wrong tenant")
        scope = settings.entra_api_scope.rsplit('/', 1)[-1]
        delegated = claims.get('scp')
        if not isinstance(delegated, str) or scope not in delegated.split():
            raise ApplicationError(403, "SCOPE_REQUIRED", "El token no autoriza acceso delegado a DataStage")
        roles = claims.get("roles", [])
        if not isinstance(roles, list):
            raise ValueError("Invalid roles")
        roles = frozenset(r for r in roles if r in {"Reader", "Operator", "Reprocessor", "Auditor", "Admin"})
        if not roles:
            raise ApplicationError(403, "ROLE_REQUIRED", "La cuenta no tiene un rol DataStage asignado")
        return Principal(claims.get("oid", claims["sub"]), claims.get("name", "Usuario"), roles, settings.scope_id)
    except ApplicationError:
        raise
    except (jwt.PyJWTError, ValueError, KeyError):
        raise ApplicationError(401, "INVALID_TOKEN", "El token no es válido o ha expirado") from None


def require_reader(principal: Principal = Depends(current_principal)):
    principal.require("Reader", "Operator", "Reprocessor", "Auditor")
    return principal
