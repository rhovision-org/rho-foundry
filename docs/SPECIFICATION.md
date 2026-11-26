# Foundry specification reference

Return to the [main README](../README.md) for a first example.

## Inputs

All objects must contain exactly their documented fields. Unknown and duplicate JSON keys are rejected. Identifiers match `[a-z][a-z0-9_]{0,31}`.

### Protocol

| Field | Type |
| --- | --- |
| name | Identifier |
| resources | Object keyed by resource identifier |
| roles | List of unique role identifiers |
| invariants | List of predicates |
| actions | List of primitive action objects |
| goals | List of goal objects (may be empty) |

Each resource has integer `initial` and `capacity` values with 0 <= initial <= capacity <= 1,000,000.

### Predicate

A predicate contains a nonempty `weights` object mapping resource identifiers to integer coefficients, an `op` of `eq`, `le` or `ge`, and an integer `rhs`. The compiler evaluates the weighted sum against the right-hand side. Coefficients are bounded to +/- 1,000,000 and right-hand sides to +/- 10^15. A predicate list is a conjunction; an empty list is true.

### Primitive action

`name`, `roles`, `guards`, `delta`.

The role list must be nonempty and contain only declared roles. Guards must hold in the starting state. The delta maps resources to integer changes (omitted resources have zero change). A nonzero delta is required; its coefficients are bounded to +/- 1,000,000. If the target would exceed any resource capacity or fall below zero, the action is disabled. If an otherwise enabled action violates a declared invariant, the entire compilation is rejected.

### Goal

`name`, `role`, `actions`, `predicates`.

Every listed primitive action must be authorized for the declared role. The target predicate list is nonempty. The compiler finds the shortest path over the permitted primitive edges; ties are resolved by lexicographic action order. A goal that is already satisfied or unreachable from a given state has no mutating rule for that state. All operations share a namespace; `inspect` is reserved.

## Compiler output

`contract.rho` is a Rholang factory definition, not a standalone deployed instance.

`machine.json` includes the canonical specification SHA-256, sorted resource names, role order, initial state ID, state vectors, primitive edges and generated rules. Every rule has a role, operation, source state, target state and the primitive path represented by that transition.

Call the private factory with a reply name to obtain role capabilities. Each successful operation checks the expected version and increases it by one. All resources of an instance share a single private state token. Do not leak the role capabilities or give an untrusted caller the factory or another role's capabilities. A role can read the modeled state. Goal transitions do not carry out external effects or collect independent approvals.

## Limits

| Item | Maximum |
| --- | ---: |
| Specification file size | 262,144 bytes |
| Resources | 12 |
| Roles | 16 |
| Primitive actions | 64 |
| Goals | 32 |
| Predicates per list | 32 |
| Reachable states | 2,048 |
| Primitive edges | 24,000 |
| Generated role rules | 24,000 |
| Aggregate synthesized path steps | 1,000,000 |
| Runtime version | 2,147,483,647 |

Exhausting a compiler budget is a compilation error, not evidence of an unreachable goal. The CLI returns code 0 for a successful compilation and 2 for a handled error. It requires a new output directory whose parent exists. The compiler performs no network operations.

## Validation boundary

See [CI](https://github.com/rhovision-org/rho-foundry/actions) for actual outcomes. The solver explores the full reachable finite graph of an accepted specification; this is not a formal proof that generated Rholang implements every possible model under every possible runtime context. Runtime tests exercise two synthetic examples. The state token serializes internal changes, but does not provide distributed transactions, external consent, custody, identity verification or capability revocation.
