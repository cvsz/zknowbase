import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.observability import AUTH_FAILURES, AUTHORIZATION_DENIALS
from app.store_factory import security_store

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
ZWORKFORCE_CONTEXT_VERSION = "1"
ZWORKFORCE_CONTEXT_HEADERS = {
    "tenant_id": "X-ZWorkforce-Tenant-ID",
    "actor_id": "X-ZWorkforce-Actor-ID",
    "agent_id": "X-ZWorkforce-Agent-ID",
    "tool_id": "X-ZWorkforce-Tool-ID",
    "policy_context": "X-ZWorkforce-Policy-Context",
    "request_id": "X-ZWorkforce-Request-ID",
    "trace_id": "X-ZWorkforce-Trace-ID",
}


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    tenant_id: str
    key_prefix: str
    scopes: frozenset[str]
    bootstrap: bool = False

    def has_scope(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes


@dataclass(frozen=True)
class ZWorkforceContext:
    tenant_id: str
    actor_id: str
    agent_id: str
    tool_id: str
    policy_context: str
    request_id: str
    trace_id: str


def authenticate_principal(
    request: Request,
    supplied: str | None = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> Principal:
    store = security_store(settings)
    resource = f"{request.method} {request.url.path}"

    if not supplied:
        AUTH_FAILURES.inc()
        store.audit(None, None, "authenticate", resource, "denied", "missing API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    if settings.bootstrap_api_key_enabled and secrets.compare_digest(supplied, settings.api_key):
        principal = Principal(
            id="bootstrap",
            name="bootstrap",
            tenant_id=settings.default_tenant_id,
            key_prefix="bootstrap",
            scopes=frozenset({"*"}),
            bootstrap=True,
        )
        request.state.principal = principal
        return principal

    key = store.verify(supplied)
    if key is None:
        AUTH_FAILURES.inc()
        store.audit(
            None,
            store.token_prefix(supplied),
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
        tenant_id=key.tenant_id,
        key_prefix=key.key_prefix,
        scopes=frozenset(key.scopes),
    )
    request.state.principal = principal
    return principal


def require_scopes(*required: str):
    def dependency(
        request: Request,
        principal: Principal = Depends(authenticate_principal),
        settings: Settings = Depends(get_settings),
    ) -> Principal:
        missing = [scope for scope in required if not principal.has_scope(scope)]
        if missing:
            AUTHORIZATION_DENIALS.labels(reason="scope").inc()
            security_store(settings).audit(
                principal.id,
                principal.key_prefix,
                "authorize",
                f"{request.method} {request.url.path}",
                "denied",
                f"tenant={principal.tenant_id};missing scopes:{','.join(missing)}",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient API key scope",
            )
        return principal

    return dependency


def _bounded_context_value(request: Request, header: str) -> str:
    value = request.headers.get(header, "").strip()
    if not value or len(value) > 256 or any(ord(char) < 32 for char in value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zworkforce execution context",
        )
    return value


def validate_zworkforce_context(
    request: Request,
    principal: Principal = Depends(authenticate_principal),
    settings: Settings = Depends(get_settings),
) -> ZWorkforceContext | None:
    """Validate optional governed zworkforce retrieval metadata.

    The service key remains authoritative for tenant authorization. When a caller marks
    a request as a governed zworkforce invocation, every context field is required and
    the declared tenant/request identities must match server-authenticated state.
    """
    version = request.headers.get("X-ZWorkforce-Context-Version")
    if version is None:
        return None
    if version != ZWORKFORCE_CONTEXT_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported zworkforce execution context version",
        )

    values = {
        name: _bounded_context_value(request, header)
        for name, header in ZWORKFORCE_CONTEXT_HEADERS.items()
    }
    if values["tenant_id"] != principal.tenant_id:
        AUTHORIZATION_DENIALS.labels(reason="tenant_context").inc()
        security_store(settings).audit(
            principal.id,
            principal.key_prefix,
            "authorize",
            f"{request.method} {request.url.path}",
            "denied",
            "zworkforce tenant context mismatch",
            tenant_id=principal.tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="zworkforce tenant context does not match authenticated tenant",
        )

    server_request_id = getattr(request.state, "request_id", None)
    if server_request_id is not None and values["request_id"] != server_request_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="zworkforce request context does not match X-Request-ID",
        )

    context = ZWorkforceContext(**values)
    request.state.zworkforce_context = context
    return context


def require_api_key(principal: Principal = Depends(authenticate_principal)) -> Principal:
    """Backward-compatible authentication dependency for internal/tests callers."""
    return principal
