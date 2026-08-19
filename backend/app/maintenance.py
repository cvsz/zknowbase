import asyncio
import fcntl
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator


@contextmanager
def mutation_lock(path: Path, *, exclusive: bool) -> Iterator[None]:
    """Cross-process advisory lock on the shared local data volume."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@asynccontextmanager
async def async_mutation_lock(path: Path, *, exclusive: bool) -> AsyncIterator[None]:
    """Async-friendly variant so an exclusive backup lock doesn't block FastAPI's loop."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        await asyncio.to_thread(fcntl.flock, handle.fileno(), mode)
        yield
    finally:
        await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def is_mutating_api_request(method: str, path: str) -> bool:
    if not path.startswith("/api/v1/") or method in {"GET", "HEAD", "OPTIONS"}:
        return False
    # Query/search are POST for payload ergonomics but are read-only operations.
    return path not in {"/api/v1/query", "/api/v1/search"}
