import asyncio

import pytest

from app.maintenance import async_mutation_lock, mutation_lock, requires_data_lock


def test_data_lock_scope():
    assert requires_data_lock("/api/v1/documents") is True
    assert requires_data_lock("/api/v1/query") is True
    assert requires_data_lock("/api/v1/health") is False
    assert requires_data_lock("/docs") is False


@pytest.mark.asyncio
async def test_exclusive_lock_waits_for_async_shared_holder(tmp_path):
    path = tmp_path / ".mutation.lock"
    shared_ready = asyncio.Event()
    release_shared = asyncio.Event()
    exclusive_acquired = asyncio.Event()

    async def shared_holder():
        async with async_mutation_lock(path, exclusive=False):
            shared_ready.set()
            await release_shared.wait()

    async def exclusive_holder():
        await shared_ready.wait()
        async with async_mutation_lock(path, exclusive=True):
            exclusive_acquired.set()

    shared = asyncio.create_task(shared_holder())
    exclusive = asyncio.create_task(exclusive_holder())
    await shared_ready.wait()
    await asyncio.sleep(0.05)
    assert exclusive_acquired.is_set() is False
    release_shared.set()
    await asyncio.wait_for(exclusive_acquired.wait(), timeout=2)
    await shared
    await exclusive


def test_sync_lock_file_is_created(tmp_path):
    path = tmp_path / "locks" / ".mutation.lock"
    with mutation_lock(path, exclusive=True):
        assert path.is_file()
