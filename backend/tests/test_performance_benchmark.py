import argparse

import pytest

from scripts.benchmark_qdrant import percentile, validate_args, vector_for


def test_percentile_and_vector_generation_are_deterministic():
    assert percentile([0.4, 0.1, 0.3, 0.2], 0.50) == 0.2
    assert percentile([0.4, 0.1, 0.3, 0.2], 0.95) == 0.4
    assert vector_for(3, 8) == vector_for(3, 8)
    assert len(vector_for(3, 8)) == 8


def test_benchmark_arguments_are_bounded():
    valid = argparse.Namespace(
        points=512,
        requests=200,
        concurrency=8,
        vector_size=32,
        max_p95_seconds=2.0,
    )
    validate_args(valid)

    for field, value in (
        ("points", 0),
        ("requests", 10_001),
        ("concurrency", 65),
        ("vector_size", 1),
        ("max_p95_seconds", 0.0),
    ):
        invalid = argparse.Namespace(**vars(valid))
        setattr(invalid, field, value)
        with pytest.raises(SystemExit):
            validate_args(invalid)
