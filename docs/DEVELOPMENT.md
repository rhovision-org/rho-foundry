# Working on Foundry

`foundry/core.py` validates the input and explores reachable states. It derives authorized goal paths and reuses that analysis for both generated artifacts. `foundry/symbolic.py` proves preservation for guarded counter moves and emits arithmetic Rholang. The CLI is in `foundry/__main__.py`. Inputs in `examples/` cover a reservation, escrow and the million-seat hold quota.

```sh
python3 -m unittest discover -s tests -v
python3 -m foundry examples/reservation.json --out reservation
python3 -m foundry examples/hold-quota.json --symbolic --out quota
```

The [input and output reference](SPECIFICATION.md) covers the enumerated protocol. The [symbolic guide](SYMBOLIC.md) describes the proof obligations and ordered counter replies. `tools/runtime_check.py` and `tools/probe_symbolic.py` run both backends against a pinned Rholo binary. They compare the small quota's behavior with the enumerated reference and exercise the large quota at native execution scale.

When editing a guard or proof rule, include a spec where the move is allowed and one where preservation is inconclusive or the move must be denied. For an output-format change, check the actor capability API and the downstream Weave interface for enumerated machines. [Interface map](ECOSYSTEM.md) · [CI workflow](../.github/workflows/ci.yml)
