import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import Depends

from app.core.config import Settings, get_settings


@contextmanager
def mutation_lock(path: Path, *, exclusive: bool) -> Iterator[None]:
    """Coordinate local backend/worker mutations with backup and restore.

    Shared locks are held by normal mutating operations. Backup/restore holds an
    exclusive lock, which waits for in-flight work and prevents new mutations.
    The lock file lives on the shared backend data volume so separate local
    containers/processes participate in the same lock domain.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if not exclusive:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def mutation_guard(settings: Settings = Depends(get_settings)) -> Iterator[None]:
    with mutation_lock(settings.maintenance_lock_path, exclusive=False):
        yield
