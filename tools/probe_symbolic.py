"""Compare symbolic actors with enumerated semantics and run the large example."""

import argparse
import json
from pathlib import Path

from foundry.core import compile_protocol, simulate
from foundry.symbolic import compile_symbolic
from runtime_check import ROOT, decode, prefixes, run, seq_body, sha, wrap


def quota_spec(capacity, quota):
    raw = json.loads((ROOT / "examples/hold-quota.json").read_text())
    for place in raw["resources"].values():
        place["capacity"] = capacity
    raw["resources"]["free"]["initial"] = capacity
    raw["invariants"][0]["rhs"] = capacity
    raw["invariants"][1]["rhs"] = quota
    raw["actions"][0]["guards"][0]["rhs"] = quota - 1
    raw["goals"][0]["predicates"][0]["rhs"] = quota
    return raw


def probe(request, anchor, _quick):
    rows = []

    def compare(name, term, expected):
        body = {"term": term, "blockHash": anchor, "usePreStateHash": False}
        result = request("/api/explore-deploy-by-block-hash", body)
        if result.get("block", {}).get("blockHash") != anchor or result.get("replySource") != "firstPrivateName":
            raise ValueError("unexpected origin of native replies")
        actual = sorted((decode(v) for v in result["expr"]), key=lambda v: v[0])
        if actual != expected:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")
        rows.append({"name": name, "passed": True, "actual": actual})

    large = quota_spec(1_000_000, 250_000)
    _, source = compile_symbolic(large)
    calls = [
        ("clerk", "fill_quota", 0), ("manager", "fill_quota", 0),
        ("manager", "fill_quota", 1), ("clerk", "reserve", 1), ("clerk", "issue", 0),
        ("clerk", "issue", 1), ("manager", "fill_quota", 2), ("clerk", "inspect", 0),
    ]
    expect = [
        [0, "DENIED", [1_000_000, 0, 0], 0],
        [1, "OK", [750_000, 250_000, 0], 1],
        [2, "DENIED", [750_000, 250_000, 0], 1],
        [3, "DENIED", [750_000, 250_000, 0], 1],
        [4, "STALE", [750_000, 250_000, 0], 1],
        [5, "OK", [750_000, 249_999, 1], 2],
        [6, "OK", [749_999, 250_000, 1], 3],
        [7, "STATE", [749_999, 250_000, 1], 3],
    ]
    compare("million-seat-quota", wrap(large["roles"], source, seq_body(large, calls)), expect)
    race = '''new a, b in {
      cap1!("fill_quota", 0, *a) | cap1!("fill_quota", 0, *b) |
      for (@(x, u, v) <- a; @(y, s, t) <- b) {
        match (x, y) {
          ("OK", "STALE") => { out!((0, x, u, v)) | out!((1, y, s, t)) }
          ("STALE", "OK") => { out!((0, y, s, t)) | out!((1, x, u, v)) }
          _ => { out!((0, "BAD_RACE", [], 0)) }
        }
      }
    }'''
    compare("concurrent-quota", wrap(large["roles"], source, race), [
        [0, "OK", [750_000, 250_000, 0], 1],
        [1, "STALE", [750_000, 250_000, 0], 1],
    ])

    small = quota_spec(3, 2)
    flat, _ = compile_protocol(small)
    _, source = compile_symbolic(small)
    paths = prefixes(flat)
    operations = ["reserve", "issue", "release", "fill_quota", "inspect", "unknown"]
    for state, prefix in sorted(paths.items()):
        for role in small["roles"]:
            for op in operations:
                calls = prefix + [(role, op, len(prefix)), (role, "inspect", 0)]
                position, version = 0, 0
                expected = []
                for i, (who, action, revision) in enumerate(calls):
                    status, position, version = simulate(flat, position, version, who, action, revision)
                    expected.append([i, status, flat["states"][position], version])
                compare(f"{state}:{role}:{op}", wrap(small["roles"], source, seq_body(small, calls)), expected)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.binary.resolve(), probe=probe)
    report["symbolic_compiler_sha256"] = sha(ROOT / "foundry/symbolic.py")
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS", report["runs"], "native symbolic executions")
