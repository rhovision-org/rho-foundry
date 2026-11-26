# Symbolic counter contracts

Use `--symbolic` with the usual Foundry JSON specification. The compiler keeps the state as an integer vector and emits arithmetic guards and updates, so reachable state count does not determine source size. A call to `inspect` returns `("STATE", resourceVector, version)`. All other replies also carry the ordered vector instead of an enumerated state ID. The factory and role capability calling conventions are unchanged.

## Invariant checks

Foundry checks the initial marking, then proves every declared invariant inductive for each enabled primitive. For a linear invariant with weights `w` and a primitive delta `d`, the change is the constant `w·d`. Equalities with zero change and inequalities with change in the safe direction are preserved directly. For other cases, the compiler bounds `w·state` using the source and destination capacity boxes and any guards with the same weights. If a proof is inconclusive, symbolic compilation fails. The enumerating backend can handle some specifications where these sufficient proof rules are inconclusive.

A symbolic goal repeats a single authorized primitive. An equality in the goal must change by one unit per repetition, which fixes the unique candidate repetition count. The generated contract checks it is positive and within resource bounds. Each linear guard must hold at the first and last input, so it holds at every intermediate input. The actor checks the terminal predicates and commits the whole update at one revision. Already-met and unreachable goals are denied, matching the enumerated backend's non-mutating behavior.

## Try the large quota

```sh
python3 -m foundry examples/hold-quota.json --symbolic --out quota
PYTHONPATH=. python3 tools/benchmark_symbolic.py --out /tmp/foundry-benchmark.json
PYTHONPATH=. python3 tools/probe_symbolic.py /path/to/rnode --out /tmp/foundry-symbolic-native.json
```

Use the pinned Rholo binary from [Foundry CI](../.github/workflows/ci.yml). The native probe exercises the million-seat quota and a concurrent same-version race, then compares the symbolic contract with the enumerated reference across each reachable state of a smaller quota. The benchmark compares artifact size, peak Python allocation and compilation time on the same specifications.

The bounds on input capacities, predicate coefficients, authorizations and revisions still apply. All rules for one instance share a revision. Symbolic macros apply only to internal values and require one primitive with a unit-rate goal equality. Multi-primitive goal synthesis and portable enumeration-derived policies use the enumerating backend.
