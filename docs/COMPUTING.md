# Computing implementation

The package implements the decision contract: retain every hypothesis compatible with the observation and return an action only when the certified acceptable-action sets share a member. `computing.object_adapter` supports a separate native-unit closed interval for each feature and hypothesis. Features are grouped by acquisition protocol, so one excitation observed by several sensors is charged once. Action evaluations are PASS_WITH_BOUND, FAIL_WITH_BOUND or UNRESOLVED. Missing evidence does not become a zero error bar.

## Exact acquisition planning

`computing.panel_search.optimize(contract)` covers minimal incompatible hypothesis collections using grouped acquisitions. A protocol excludes a collection when one of its feature coordinates has no common value across the collection. Closed endpoints count as possible readings. The implementation reduces duplicate and subsumed cover constraints, obtains a greedy upper bound, and searches with exact rational branch-and-bound, memoization and valid disjoint-constraint packing lower bounds. Cost, protocol count and protocol order have deterministic tie-breaking.

`verify_matching_bound(contract, result)` checks feasibility and a matching disjoint-obstruction packing bound without repeating the optimization search. Not every optimum has a tight bound of this particular form; when the bound is weaker, completed exact search supplies the optimization result but the compact verifier correctly declines to certify it alone. Neither result authenticates the input model. Infeasibility of conservative outer bounds is not proof of physical impossibility.

The original exhaustive implementation remains in `computing.fusion_engine`. Randomized test instances compare the new optimum with exhaustive optima. A synthetic menu containing 36 protocols represents 68,719,476,736 possible panels; its redundant structure reduces to three constraints and is solved in 37 search nodes, with matching cost and lower bound 3. This is a constructed algorithm test. Generating all minimal action obstructions can still be exponential in the hypothesis/action population.

The underlying decision-region and hyperedge viewpoint has established precedents, notably [Javdani et al.,2014](https://proceedings.mlr.press/v33/javdani14.html). The repository makes no novelty claim for general decision-region determination.

## Rigorous finite-hold memory bounds

The passive illustrative material law is `F=k0*e+k1*(e-z)`, `dz/dt=(e-z)/tau`. During a constant-deformation hold its exact solution is `z=(1-d)e+d*z0`, `F=k0*e+k1*(e-z0)d`, with `d=exp(-t/tau)`. `computing.memory.hold_bounds` covers rational boxes for stiffnesses, deformation, initial memory, hold epoch, relaxation time and readout error.

`exp_neg_bounds` uses alternating Taylor bounds after scaling the argument into[0,1], then interval squaring. A conservative base tolerance controls the final enclosure width. A large-argument bound avoids enormous unnecessary denominators. Every returned exponential endpoint is rational. State and force extrema are enclosed by multiaffine corner evaluation over the resulting independent box; relaxing dependencies may enlarge the interval but does not invalidate containment.

The output covers every instantaneous snapshot in the declared uncertain epoch. It does not claim a finite-window average or a changing-deformation stroke. Initial-memory force contrast decays during a hold. Thus waiting longer can turn an informative force experiment into an unresolved decision even when the algebraic model is exact. Parameters remain synthetic until calibration and discrepancy bounds establish the physical domain.

## Dyletsky and four strings

`computing.dyletsky.solve_tuning` replays the archived36-row interval proxy with11 gauge-fixed offsets, thirteen named weighting strategies, optional custom priorities, ridge regularization, and the weighted RMS matching the actual objective `sum(w*r*r)/sum(w)`. It exposes exact familywise cancellation using integer column sums, while the weighted solve itself uses ordinary numerical Gaussian elimination. A small numerical residual is reported rather than presented as an exact enclosure.

`make_score` preserves the17 supported note spellings and exports `fusion.score/1`. Enharmonic notes share offsets through the explicit12-class proxy; spelling preservation does not establish a full17-degree tuning engine. Events retain onset, duration, amplitude, tolerance, voice and target frequency. The scheduler checks four voices and half-open event boundaries. Manual retuning execution and timing remain unqualified.

`ideal_string_plan` computes ideal fixed-length/fixed-linear-density frequency and tension ratios, including `T_new/T_old=2**(cents/600)`. Declared tension bounds can reject a request; absent bounds remain unresolved. The actual shared bridge, flexibility, friction, stretch, fluid loading and actuator mapping are not supplied by this ideal formula.

## Raw acquisition audit

`computing.acquisition.audit_run` inspects actual16/24/32-bit integer PCM WAV bytes, hashes raw files, checks sample rates/channel labels/full-scale samples and requires finite strictly increasing slow CSV timestamps. A declared affine clock map establishes an arithmetic overlap calculation only. Clock identifiers and residual claims are not authenticated. Raw hydrophone voltage is not converted into pressure.

The CLI rejects duplicate JSON keys and nonfinite constants, preserves decimal input tokens exactly, and reports validation errors without turning malformed input into an empty successful population. `plan`, `decide`, `memory`, `music`, `audit-run` and `demo` are runnable commands. Outputs remain offline recommendations, bounds or audit records; no physical command driver is implemented.
