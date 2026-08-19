from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.rag.vector_store import VectorStore


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(percentile_value * len(ordered)) - 1))
    return ordered[rank]


def vector_for(index: int, size: int) -> list[float]:
    vector = [0.0] * size
    vector[index % size] = 1.0
    vector[(index * 7 + 3) % size] += 0.25
    return vector


async def run_benchmark(
    qdrant_url: str,
    *,
    points: int,
    requests: int,
    concurrency: int,
    vector_size: int,
    max_p95_seconds: float,
) -> dict[str, float | int | str]:
    collection = f"zkb-perf-{uuid4().hex}"
    settings = Settings(
        api_key="benchmark-local-only-secret",
        qdrant_url=qdrant_url,
        qdrant_collection=collection,
    )
    store = VectorStore(settings)
    tenant_id = "tenant-perf"
    chunks = [f"benchmark chunk {index}" for index in range(points)]
    vectors = [vector_for(index, vector_size) for index in range(points)]
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0

    async def one(index: int) -> None:
        nonlocal errors
        query = vector_for(index, vector_size)
        async with semaphore:
            started = time.perf_counter()
            try:
                results = await store.search(tenant_id, query, 10)
                if not results or any(item.tenant_id != tenant_id for item in results):
                    errors += 1
            except Exception:
                errors += 1
            finally:
                latencies.append(time.perf_counter() - started)

    try:
        await store.upsert_chunks(
            tenant_id,
            "benchmark-document",
            "benchmark.md",
            None,
            chunks,
            vectors,
        )
        started = time.perf_counter()
        await asyncio.gather(*(one(index) for index in range(requests)))
        elapsed = time.perf_counter() - started
    finally:
        if await store.client.collection_exists(collection):
            await store.client.delete_collection(collection)
        await store.client.close()

    p50 = percentile(latencies, 0.50)
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)
    report: dict[str, float | int | str] = {
        "workload": "qdrant-tenant-search",
        "points": points,
        "requests": requests,
        "concurrency": concurrency,
        "vector_size": vector_size,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 6),
        "requests_per_second": round(requests / elapsed, 3) if elapsed > 0 else 0.0,
        "latency_mean_seconds": round(statistics.fmean(latencies), 6) if latencies else 0.0,
        "latency_p50_seconds": round(p50, 6),
        "latency_p95_seconds": round(p95, 6),
        "latency_p99_seconds": round(p99, 6),
        "max_p95_seconds": max_p95_seconds,
    }
    if errors:
        raise RuntimeError(f"benchmark recorded {errors} failed searches: {json.dumps(report)}")
    if p95 > max_p95_seconds:
        raise RuntimeError(
            f"benchmark p95 {p95:.6f}s exceeds guardrail {max_p95_seconds:.6f}s: "
            f"{json.dumps(report)}"
        )
    return report


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Bounded local Qdrant performance evidence")
    command.add_argument(
        "--qdrant-url",
        default=os.getenv("ZKB_TEST_QDRANT_URL", "http://127.0.0.1:6333"),
    )
    command.add_argument("--points", type=int, default=512)
    command.add_argument("--requests", type=int, default=200)
    command.add_argument("--concurrency", type=int, default=8)
    command.add_argument("--vector-size", type=int, default=32)
    command.add_argument("--max-p95-seconds", type=float, default=2.0)
    command.add_argument("--output", type=Path, default=Path("performance-report.json"))
    return command


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.points <= 10_000:
        raise SystemExit("--points must be between 1 and 10000")
    if not 1 <= args.requests <= 10_000:
        raise SystemExit("--requests must be between 1 and 10000")
    if not 1 <= args.concurrency <= 64:
        raise SystemExit("--concurrency must be between 1 and 64")
    if not 2 <= args.vector_size <= 4096:
        raise SystemExit("--vector-size must be between 2 and 4096")
    if not 0.01 <= args.max_p95_seconds <= 60.0:
        raise SystemExit("--max-p95-seconds must be between 0.01 and 60")


async def main_async() -> int:
    args = parser().parse_args()
    validate_args(args)
    report = await run_benchmark(
        args.qdrant_url,
        points=args.points,
        requests=args.requests,
        concurrency=args.concurrency,
        vector_size=args.vector_size,
        max_p95_seconds=args.max_p95_seconds,
    )
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
