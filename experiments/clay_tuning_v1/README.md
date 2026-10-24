# Clay history and a useful tuning action

This is the shared experiment core for the physical-design session and Review Hidden Math. It asks whether history-sensitive observations improve an actual future tuning decision against a memoryless predictor and a digital predictor that already knows the preparation log. It does not score successful recognition of a history label as musical utility.

The fixed target is the recovered Gen2 hex_nat E4 target 326.759563456652 Hz. The candidate actions are HOLD and manual retune upward by 5 cents. HOLD remains available. The primary outcome is failure to remain within 2 cents of the target in an independent 18–20 second window after the write ends. The requested action must be achieved within0.5 cents, and the outcome estimator needs an independently qualified error bound at most 1 cent. The other three strings remain reference resonances.

`contract.json` specifies the two write histories, four-tone excitation, channels/features, timing, policy arms, actions, endpoints, fixed horizon and comparison family. A qualification binding must supply actual stroke/force limits, calibration and synchronization records, the validated pitch-estimator bound, transfer/extractor revisions, the action procedure and waveform digest. These fields remain unfilled in `hardware_binding_template.json`; the core alone is not a physically registered experiment. Mechanical qualification must precede development measurements. It must not select settings by looking at confirmation outcomes.

## Run the evaluation software

```bash
python -m evaluation demo --output-dir results/evaluation
python -m evaluation observability --output results/observability.json
python -m evaluation probe --wav results/probe.wav --output results/probe_manifest.json
```

The demo generates actual-action synthetic episodes and evaluates four cases. A stipulated retained-state-to-pitch coupling can pass the registered tuning criterion. A material state that is observable but has no tuning consequence fails. Different optimal actions hidden from all available observations also fail. A predictable nuisance that affects tuning but is unchanged by the write history fails the history-linked gate. All four remain synthetic, and the fixed-wait demonstration establishes no total-time saving.

The probe command uses the physical session's existing renderer, preserving its zero-phase and 5 ms fade conventions. The two-second 48 kHz mono command combines the four recovered calibration targets at normalized PCM peak 0.05. This is a software waveform, not qualified physical force or pressure. It opens no device.

## Bind, fit once, and register

```bash
python -m evaluation bind experiments/clay_tuning_v1/contract.json qualified_binding.json --origin physical_measurement --output bound.json
python -m evaluation freeze bound.json development.json confirmation_blocks.json --output registration.json
python -m evaluation decide registration.json pre_action_features.json --arm fusion_full
python -m evaluation score registration.json confirmation.json --record-root recorded_sources --output results/physical_evaluation.json
```

The block file is a list of 64 distinct planned block IDs. Development data contain randomized actual-action episodes on freshly prepared replicates, including both actions. Each row supplies `cohort=development`, declared origin, day/cartridge identities, actual action, features, and independently scored outcome/error. Frozen policies, their learned scaling, contract, development digest and randomized confirmation schedule are bound into the registration hash. Confirmation rows cannot train policies. Frozen numerical coefficients round-trip through JSON without changing their digest.

Confirmation supplies one fresh preparation for each condition/history/policy cell: six policies, two histories, and three conditions give 36 episodes per raw block. No episode supplies a manufactured two-action counterfactual table. Record each physical cartridge by its actual identity, including a separate reference cartridge. A block occupies one acquisition day and can contain several cartridge identities. Sharing any clay or reference cartridge, or an acquisition day, merges blocks into a single statistical unit. A small pilot is useful descriptively but cannot pass this fixed-horizon confirmation. The planned 64 independent units and 2304 episodes reflect conservative inference, rather than a promise that one afternoon of recordings can certify a small improvement.

## Conditions and baselines

Connected clay, rod-disconnected clay, and a qualified reference cartridge are separate registered conditions. Rod disconnection also changes mechanical loading; its result is a pathway diagnostic. The reference needs independently declared mass/stiffness matching. Neither condition by itself proves that clay memory caused a measured effect.

The baseline set includes the best constant action from development, a memoryless current-state quadratic ridge predictor, a digital predictor that additionally receives the known write log, and a digital predictor with the complete measured feature set. Fusion-full deliberately uses the identical full digital predictor. Its purpose here is to expose the acquisition/decision interface, not manufacture an advantage over digital computation. Fusion-reduced uses the predeclared feature subset and prospectively omits the multitone protocol. Every policy uses the same action menu and independent future outcome.

The fitted regressions are empirical action-wise predictors with ridge 0.01 and development-derived scaling. They are not deterministic physical error envelopes. Their held-out performance is what this experiment tests. Exact finite-panel certificates elsewhere in the repository remain conditional on valid hypothesis/error/action tables; they cannot be substituted for confirmation evidence.

## What a positive result means

The material-information verdict requires connected-condition improvement of more than10 percentage points against both the memoryless and known-write-log predictors. It additionally bounds the probability of a positive reference-condition gain below 0.1. Together these establish a strictly positive difference between registered-condition gains under the sampling assumptions. They do not establish a ten-percentage-point interaction. A sixth history-linked gate requires definite discordance of actual H0/H1 constant-policy outcomes, different Fusion actions for the two histories, and successful actual Fusion outcomes. This rejects a merely predictive nuisance with no write-history effect. The rod-disconnected results and same-measurement digital results are reported separately.

The familywise error allocation is 0.05 across six predeclared tests. Superiority and cost use conservative independent-block Hoeffding tails, evaluated with rational exponential enclosures. Reduced-policy noninferiority and the reference guard use an exact binomial sufficient criterion based on whether a block can be worse. The latter assumes independent units with a common indicator probability. Bounds permitting worsening count as worsening. The history-linked gate uses an exact upper tail against a one-half discordance bound. Under its null, the two histories have equal fixed-action failure probabilities and their fresh preparations are conditionally independent within the block. Ambiguous outcomes count as non-events in the fixed denominator. The policies, horizons, margins and comparison family must be fixed before confirmation; optional stopping is unsupported.

Measurement uncertainty remains separate from sampling uncertainty. A pitch-error interval straddling the success boundary yields a failure-loss interval [0,1]. A failed action or unresolved/missing outcome is an operational failure under the specified rule. Future features, changed targets, wrong policy actions, altered registration, development overlap, duplicated preparations, missing digests, wrong acquisition menus and incomplete fixed horizons prevent a positive finding.

## Costs and the timing trap

Costs attach to complete acquisition protocols and include preparation, reset, calibration share, acquisition, waiting, computation, retuning and verification. Unused channels from one recorded pluck do not create an acquisition saving. A reduction claim additionally requires prospective protocol omission, noninferior held-out outcomes and a statistically supported total-cost saving. Equalizing scoring epochs by waiting through an omitted probe preserves causal timing but can eliminate a wall-clock saving. The synthetic positive fixture intentionally exercises this case and returns cost reduction NOT_DEMONSTRATED.

## Physical-owner handoff

Implement the normalized write histories with an independently qualified stroke no greater than 0.25 mm and a measured force limit no greater than 5 N, following M03 provisional commissioning ceilings. Both histories last 21 seconds and end at the same declared time 0. Preserve slow force/displacement baselines, raw string/direct-vibration/water signals, the observed drive and elapsed time since writing. Use identical qualified E4 plucks for the common 0–1 s pre-action pitch check and the 18–20 s outcome readout. A fixed-frequency driven response is not a natural-pitch estimate. Implement the shared phases: slow features 1–2 s, probe 2–4 s, decision by 5 s, manual action 5–17 s and independent pitch outcome 18–20 s. Qualify the pitch estimator and action achievement, and record clock bounds. If these timings are impractical, revise and re-register the core before collecting confirmation; never relabel late actions as on-time successes.

The physical acquisition/analyzer should produce the episode ledger expected by `evaluation.evaluate`, with lineage to the existing `fusion.run/1` records. Physical scoring requires a record root: each episode references its raw-run manifest, pre-action feature JSON and independent outcome JSON by relative path and SHA256. The evaluator checks their bytes, invokes the raw WAV/CSV auditor, and checks that feature/outcome records agree with the ledger. These checks still do not authenticate a laboratory event, calibration validity or causal exchangeability. Results distinguish byte-verified sources and conditional physical inference from an authenticated physical claim.

A failed acquisition, unresolved pitch or failed action remains an assigned operational failure instead of disappearing from the denominator. For physical rows with noncompleted status, provide a hash-bound `fusion.failed-episode/1` failure log containing ticket_id, status and reason through `failure_record_path`/`failure_record_sha256`. Complete rows require the raw/pre/outcome records; failure logs do not pretend that missing waveforms exist.

The binding also requires independent dynamic diaphragm motion qualification within the provisional 10 micrometre ceiling. This requirement follows the M03 physical handoff; the software waveform does not release combined operation. Register distinct full-probe and reduced no-probe command digests. Retain the observed electrical drive in both arms so omission can be checked. The channel-ratio and slow-force feature definitions, read disturbances and pitch validation scope are fixed in the core.

Within a block, connected and rod-disconnected episodes retain the same actual clay cartridge across histories and policies; the reference has its own fixed identity. Reusing one reference cartridge across all 64 planned blocks merges all of them into one independent unit, so that pilot cannot certify this confirmation criterion. Distinct labels must never stand in for distinct specimens.

Completed episodes cannot reuse a raw-run identity, raw manifest digest or physical audio digest across randomized cells. The known-log and condition features must match the assigned preparation and condition. These consistency checks prevent simple copied-evidence and comparator-label errors; they still do not authenticate physical events.

`confirmation_episode.template.json` exposes the required ledger fields with unfilled measurements. The saved synthetic results and probe metadata are in `receipts/history_tuning/`, with the consolidated check record at `verification/history_tuning_20261024.json`. The probe command renders the two-second segment. If acquisition wraps it with synchronization markers, qualify its placement and quiet measurement windows, and bind the hash of the actual complete per-protocol `drive_command.wav` retained in the raw manifest. Retain segment provenance; a wrapper must not change the registered excitation.
