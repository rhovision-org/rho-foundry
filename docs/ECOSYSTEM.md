# Choose the contract model that fits the application

| Project | Role |
| --- | --- |
| [Foundry](https://github.com/rhovision-org/rho-foundry) | Write linear conditions and guarded updates. Compile large counters with inductive proofs and supported arithmetic goals. |
| [Forge](https://github.com/rhovision-org/rho-forge) | Express workflow dependencies through consumption and production. Give independent actors their own revision scopes. |
| [Weave](https://github.com/rhovision-org/rho-weave) | Extract role-authorized transitions from enumerated machine artifacts and synthesize a recovery policy. |
| [Observer](https://github.com/rhovision-org/rho-observer) | Select a read anchor, report freshness and explain conflicting or incomplete sources. |

Choose the [symbolic quota](SYMBOLIC.md) for a large guarded ledger and Forge for several independent venues. Use an enumerated machine when a downstream policy needs its finite state table. Observer's anchor describes the source evidence for a particular block. It can be used by the application independently of its choice of contract compiler.
