# Rho Foundry

**Declare resources, authority, constraints and goals. Generate executable Rholang.**

Foundry is a finite-resource protocol compiler. It enumerates reachable resource states, rejects reachable invariant violations, synthesizes shortest authorized paths to declared goals, and emits a Rholang factory with private state and separate send-only role capabilities. A goal path becomes one serialized state transition rather than a sequence of external calls. No network connection or signing is required to compile.

## Quick start

Requires Python 3.11+ and no third-party Python dependencies.

```sh
python -m foundry examples/escrow.json --out generated
```

Outputs `generated/contract.rho` and `generated/machine.json`. The latter maps numeric state IDs to resource vectors and names the actions folded into each goal transition.

The escrow example has six reachable states and five primitive steps. Its settler capability can execute the entire authorized internal accounting path with one `settle` call, or continue from an intermediate state. The reservation example compiles a different resource topology with capacity conservation.

These are synthetic accounting resources, not REV, external assets, physical delivery or real-world approval. The compiler does not acquire consent or grant a role authority that was not explicitly declared. In particular, the example settler is intentionally authorized to perform all five primitive steps.

## Interface

Place the generated `contract factory(ready)` in the scope of a private `factory` name. Invoke `factory!(*ready)` and receive the returned role capabilities in the declared role order. Each instance has separate private state.

Invoke a role capability with `cap!("operation", expectedVersion, *reply)`. The reply is a tuple (status, state ID, version).

- OK: committed a modeled state transition, incremented version.
- DENIED: not authorized or not enabled, state unchanged.
- STALE: version mismatch, state unchanged.
- EXHAUSTED: reached version ceiling; no wraparound.
- STATE: inspect operation, without mutation.

All modeled resources live in a single private state token. Concurrent calls consume that token exclusively. Role capabilities are bearer capabilities; possession is authority. The caller must distribute capabilities privately and correctly. There is no identity registry, revocation service, or live deployment in this repository. State inspection is available to all issued roles. The factory must not be published as if it were an existing instance.

## Specification

Resources have integer initial balances and capacities. Invariants and guards are linear integer predicates with weights by resource and comparison eq/le/ge. Actions have integer deltas, guards, and allowed roles. Goals specify one role, a permitted subset of that role's primitive operations, and a target predicate. Goal synthesis uses reverse BFS on that restricted graph; equal-length alternatives use lexicographic action ordering. Already satisfied and unreachable goals have no mutating transition. An invariant violation reachable via any enabled primitive action rejects the entire specification, rather than silently deleting the action.

Limits: 12 resources, 16 roles, 64 actions, 32 goals, 2,048 reachable states, 24,000 edges and rules, 1,000,000 aggregate goal path steps. The compiler rejects oversized inputs, unknown fields, duplicates and unsafe names.

## Verification

```sh
python -m unittest discover -s tests -v
```

The test suite includes a forward-search reference oracle, 150 seeded randomized reservation instances, complete model admission matrices, authority checks and invariant counterexamples. The Rholo workflow downloads and digest-checks the public pinned CI binary and executes generated Rholang in a fresh loopback-only standalone devnet. No production node or upstream repository is modified.

See the Actions tab for the actual compiler and runtime outcomes. Generated code is a bounded-state accounting machine, not a general Rholang compiler, cross-chain transaction coordinator or formally verified production settlement system. Native runtime validation covers the fixtures, not every possible source or malicious process context. No external asset transfer is implemented.

License selection is pending repository-owner approval; no license grant is implied.
