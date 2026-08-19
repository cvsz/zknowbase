import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.security_store import SecurityStore

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    key_prefix: str
    scopes: frozenset[str]
    bootstrap: bool = False

    def has_scope(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes


def _security_store(settings: Settings) -> SecurityStore:
    return SecurityStore(settings.metadata_db)


def authenticate_principal(
    request: Request,
    supplied: str | None = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> Principal:
    store = _security_store(settings)
    resource = f"{request.method} {request.url.path}"

    if not supplied:
        store.audit(None, None, "authenticate", resource, "denied", "missing API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    if settings.bootstrap_api_key_enabled and secrets.compare_digest(supplied, settings.api_key):
        principal = Principal(
            id="bootstrap",
            name="bootstrap",
            key_prefix="bootstrap",
            scopes=frozenset({"*"}),
            bootstrap=True,
        )
        request.state.principal = principal
        store.audit(principal.id, principal.key_prefix, "authenticate", resource, "allowed")
        return principal

    key = store.verify(supplied)
    if key is None:
        store.audit(
            None,
            SecurityStore.token_prefix(supplied),
            "authenticate",
            resource,
            "denied",
            "unknown, expired, or revoked service key",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    principal = Principal(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=frozenset(key.scopes),
    )
    request.state.principal = principal
    store.audit(principal.id, principal.key_prefix, "authenticate", resource, "allowed")
    return principal


def require_scopes(*required: str):
    def dependency(
        request: Request,
        principal: Principal = Depends(authenticate_principal),
        settings: Settings = Depends(get_settings),
    ) -> Principal:
        missing = [scope for scope in required if not principal.has_scope(scope)]
        if missing:
            _security_store(settings).audit(
                principal.id,
                principal.key_prefix,
                "authorize",
                f"{request.method} {request.url.path}",
                "denied",
                f"missing scopes: {','.join(missing)}",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient API key scope",
            )
        return principal

    return dependency


def require_api_key(principal: Principal = Depends(authenticate_principal)) -> Principal:
    """Backward-compatible authentication dependency for internal/tests callers."""
    return principal
