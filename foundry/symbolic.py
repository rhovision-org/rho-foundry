"""Compile inductive counter protocols without enumerating reachable states."""

import hashlib
import json

from .core import MAX_VERSION, SpecError, digest, parse, require


def _dot(weights, values):
    return sum(w * value for w, value in zip(weights, values))


def _obligation(invariant, action, caps):
    """Prove preservation over all enabled states satisfying the invariant."""
    change = _dot(invariant.weights, action.delta)
    if change == 0 or invariant.op == "le" and change < 0 or invariant.op == "ge" and change > 0:
        return "inductive"

    # Intersect the source box with the inverse image of the destination box.
    bounds = [(max(0, -d), min(c, c - d)) for d, c in zip(action.delta, caps)]
    if any(lo > hi for lo, hi in bounds):
        return "disabled_by_capacity"
    products = [(min(w * lo, w * hi), max(w * lo, w * hi))
                for w, (lo, hi) in zip(invariant.weights, bounds)]
    lower = sum(lo for lo, _ in products)
    upper = sum(hi for _, hi in products)
    for guard in (*action.guards, invariant):
        if guard.weights != invariant.weights:
            continue
        if guard.op in ("eq", "ge"):
            lower = max(lower, guard.rhs)
        if guard.op in ("eq", "le"):
            upper = min(upper, guard.rhs)
    if lower > upper:
        return "disabled_by_constraints"
    lo, hi = lower + change, upper + change
    if (invariant.op == "eq" and lo == hi == invariant.rhs
        or invariant.op == "le" and hi <= invariant.rhs
        or invariant.op == "ge" and lo >= invariant.rhs):
        return "interval_bound"
    return None


def _expression(weights, variables):
    terms = [f"({w} * {x})" for w, x in zip(weights, variables) if w]
    return "(" + " + ".join(terms or ["0"]) + ")"


def _condition(predicate, variables):
    value = _expression(predicate.weights, variables)
    if predicate.op == "eq":
        return f"({value} == {predicate.rhs})"
    if predicate.op == "le":
        return f"({value} < {predicate.rhs + 1})"
    return f"({predicate.rhs - 1} < {value})"


def _bounded(variables, caps):
    return [term for v, cap in zip(variables, caps)
            for term in (f"(-1 < {v})", f"({v} < {cap + 1})")]


def _shift(variables, delta, steps):
    return [f"({v} + ({d} * {steps}))" if d else v for v, d in zip(variables, delta)]


def _guard(conditions, success, failure):
    if not conditions:
        return success
    if len(conditions) == 1:
        return f"if ({conditions[0]}) {{ {success} }} else {{ {failure} }}"
    tests = ", ".join(conditions)
    pattern = ", ".join(["true"] * len(conditions))
    return f"match ({tests}) {{ ({pattern}) => {{ {success} }} _ => {{ {failure} }} }}"


def _emit(protocol, macros, spec_hash):
    values = [f"r{i}" for i in range(len(protocol.resources))]
    names = ", ".join(values)
    caps = [f"cap{i}" for i in range(len(protocol.roles))]

    def reply(status, variables=values, version="version"):
        state = ", ".join(variables)
        return f'state!(({version}, {state})) | ret!(("{status}", [{state}], {version}))'

    denied = reply("DENIED")
    handlers = []
    admission = []

    def add(operation, roles, body):
        handler = f"run{len(handlers)}"
        args = ", ".join("@" + value for value in values)
        handlers.append(f"    contract {handler}(@version, {args}, ret) = {{ {body} }} |")
        for role in roles:
            index = protocol.roles.index(role)
            admission.append(
                f'          ({index}, "{operation}") => {{ {handler}!(version, {names}, *ret) }}'
            )

    for action in protocol.actions:
        target = _shift(values, action.delta, "1")
        checks = [*_bounded(target, protocol.caps),
                  *(_condition(guard, values) for guard in action.guards)]
        add(action.name, action.roles, _guard(checks, reply("OK", target, "version + 1"), denied))

    for goal, action, pivot, slope, bound in macros:
        target = _shift(values, action.delta, "steps")
        last_input = _shift(values, action.delta, "(steps - 1)")
        checks = [
            *_bounded(target, protocol.caps),
            *(_condition(g, point) for g in action.guards for point in (values, last_input)),
            *(_condition(p, target) for p in goal.predicates),
        ]
        final = _guard(checks, reply("OK", target, "version + 1"), denied)
        # Check the repetition bound before evaluating any scaled expression.
        body = _guard(["0 < steps", f"steps < {bound + 1}"], final, denied)
        current = _expression(pivot.weights, values)
        steps = f"{pivot.rhs} - {current}" if slope == 1 else f"{current} - {pivot.rhs}"
        add(goal.name, (goal.role,),
            f"new count in {{ count!({steps}) | for (@steps <- count) {{ {body} }} }}")

    private = ", ".join(["state", "dispatch", *caps, *(f"run{i}" for i in range(len(handlers)))])
    initial = ", ".join(map(str, protocol.initial))
    references = ", ".join("bundle+{*" + cap + "}" for cap in caps)
    dispatch = "\n".join([
        "match (who, op) {", *admission, f"          _ => {{ {denied} }}", "        }",
    ])
    ready = _guard([f"version < {MAX_VERSION}"], dispatch, reply("EXHAUSTED"))
    cas = _guard(["expected == version"], ready, reply("STALE"))
    inspect = _guard(['op == "inspect"'], reply("STATE"), cas)
    return "\n".join([
        "// Rho Foundry symbolic counters; spec sha256 " + spec_hash,
        "contract factory(ready) = {",
        f"  new {private} in {{",
        f"    state!((0, {initial})) |",
        *handlers,
        *(f"    contract {cap}(@op, @expected, ret) = "
          f"{{ dispatch!({index}, op, expected, *ret) }} |" for index, cap in enumerate(caps)),
        "    contract dispatch(@who, @op, @expected, ret) = {",
        f"      for (@(version, {names}) <- state) {{ {inspect} }}",
        "    } |",
        f"    ready!({references})",
        "  }",
        "}",
        "",
    ])


def compile_symbolic(raw):
    protocol = parse(raw)
    proofs = {}
    for action in protocol.actions:
        proof = [_obligation(inv, action, protocol.caps) for inv in protocol.invariants]
        if None in proof:
            raise SpecError(f"symbolic preservation not established for {action.name}, "
                            f"invariant {proof.index(None) + 1}")
        proofs[action.name] = proof

    actions = {action.name: action for action in protocol.actions}
    macros = []
    for goal in protocol.goals:
        require(len(goal.actions) == 1, f"symbolic goal {goal.name} requires one primitive")
        action = actions[goal.actions[0]]
        pivots = [(pred, _dot(pred.weights, action.delta))
                  for pred in goal.predicates if pred.op == "eq"]
        pivot = next(((p, slope) for p, slope in pivots if abs(slope) == 1), None)
        require(pivot is not None, f"symbolic goal {goal.name} needs a unit-rate equality")
        bound = min(cap // abs(d) for cap, d in zip(protocol.caps, action.delta) if d)
        macros.append((goal, action, *pivot, bound))

    spec_hash = digest(raw)
    source = _emit(protocol, macros, spec_hash)
    require(len(source.encode()) <= 1_000_000, "symbolic source budget exceeded")
    return {
        "schema": "rho-foundry/symbolic-v1",
        "name": protocol.name,
        "spec_sha256": spec_hash,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "resources": list(protocol.resources),
        "initial": list(protocol.initial),
        "capacities": list(protocol.caps),
        "roles": list(protocol.roles),
        "max_version": MAX_VERSION,
        "preservation": proofs,
        "macros": {goal.name: {"primitive": action.name, "max_steps": bound}
                   for goal, action, _, _, bound in macros},
    }, source
