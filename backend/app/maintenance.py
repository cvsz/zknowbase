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
    """Async-friendly variant so an exclusive backup/restore lock doesn't block the event loop."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        await asyncio.to_thread(fcntl.flock, handle.fileno(), mode)
        yield
    finally:
        await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def requires_data_lock(path: str) -> bool:
    # Health remains available to local orchestration while backup/restore owns
    # the exclusive data lock. Every endpoint that can observe or change KB data
    # takes a shared lock so restore never exposes a half-restored state.
    return path.startswith("/api/v1/") and path != "/api/v1/health"
