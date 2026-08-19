import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.queue_routes import router as queue_router
from app.api.routes import router
from app.core.config import get_settings
from app.maintenance import async_mutation_lock, requires_data_lock
from app.observability import HTTP_DURATION, HTTP_REQUESTS, configure_tracing, metrics_response, tracer

settings = get_settings()
configure_tracing(settings)
app = FastAPI(title="zknowbase", version="0.1.0", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
)


@app.middleware("http")
async def local_backup_barrier(request: Request, call_next):
    if not requires_data_lock(request.url.path):
        return await call_next(request)
    async with async_mutation_lock(settings.maintenance_lock_path, exclusive=False):
        return await call_next(request)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    started = time.perf_counter()
    status_code = 500
    with tracer("zknowbase.http").start_as_current_span("http.request") as span:
        span.set_attribute("http.request.method", request.method)
        span.set_attribute("http.request_id", rid)
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", request.url.path)
            elapsed = time.perf_counter() - started
            HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
            HTTP_DURATION.labels(request.method, route).observe(elapsed)
            span.set_attribute("http.route", route)
            span.set_attribute("http.response.status_code", status_code)
            if "response" in locals():
                response.headers["X-Request-ID"] = rid


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if not settings.metrics_enabled:
        return Response(status_code=404)
    return metrics_response(settings)


app.include_router(router, prefix="/api/v1")
app.include_router(queue_router, prefix="/api/v1")
