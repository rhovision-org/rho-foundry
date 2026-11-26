"""Measure both Foundry backends on the same guarded reservation protocol."""

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import tracemalloc

from foundry.core import SpecError, compile_protocol, manifest, rholang
from foundry.symbolic import compile_symbolic
from probe_symbolic import quota_spec


def measure(compiler, spec):
    data, source = compiler(spec)
    timings = []
    for _ in range(15):
        start = perf_counter_ns()
        compiler(spec)
        timings.append(perf_counter_ns() - start)
    tracemalloc.start()
    try:
        compiler(spec)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return {
        "median_compile_ms": round(median(timings) / 1_000_000, 3),
        "peak_python_bytes": peak,
        "source_bytes": len(source.encode()),
        "enumerated_states": len(data.get("states", [])),
    }


def benchmark():
    small = quota_spec(32, 8)
    large = quota_spec(1_000_000, 250_000)
    results = {
        "32_seats": {
            "two_enumeration_passes": measure(lambda raw: (manifest(raw), rholang(raw)), small),
            "one_enumeration_pass": measure(compile_protocol, small),
            "symbolic": measure(compile_symbolic, small),
        },
        "one_million_seats": {"symbolic": measure(compile_symbolic, large)},
    }
    try:
        compile_protocol(large)
    except SpecError as error:
        results["one_million_seats"]["enumerated"] = {"compiler_limit": str(error)}
    else:
        raise AssertionError("expected the explicit state budget to be exceeded")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.dumps(benchmark(), indent=2) + "\n"
    args.out.write_text(report)
    print(report, end="")
