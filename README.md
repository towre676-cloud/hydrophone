# Hydrophone fusion instrument

## Listen to the orchestra

The computing side now composes and performs original symphonic music. Open the downloaded self-contained [Clay and Water listening room](music/clay_and_water/player.html), or listen directly to the [six-minute chamber symphony](music/clay_and_water/performance.mp3). A shorter [The Water Remembers](music/the_water_remembers/player.html) suite and [MP3](music/the_water_remembers/performance.mp3) provide a second three-movement performance. Each player embeds its actual audio and MIDI, so it works offline after download. `run_symphony.bat` opens the prepared chamber symphony on Windows without installing anything.

The new `symphony` package uses actual analysis of 1,474 score editions by 136 composers and 12,741 performed MIDI files from 49 named pianists. Composer-balanced melodic/rhythmic priors inform original themes; measured performance priors inform bounded phrasing and dynamic controls. Real sampled instrument sounds, independent note expression, vibrato, microtuning, orchestral placement and room response produce the audible performance. The scores, performer and composer indexes, ingestion receipts, sources and audio are inspectable. This is a sampled virtual orchestra; no live recording of the unassembled physical object is claimed.

See [the symphonic engine](docs/SYMPHONIC_ENGINE.md) for architecture, provenance and generation commands, and [the listening catalogue](music/README.md) for the prepared works. The physical clay/string/water build and experiment work below remain preserved. Its musical role is an expressive instrument and future conductor input; the new symphonic engine is directly playable now.

The latest completion work is [M04 mechanics](hardware/mechanics_completion/README.md), the [E02 integration overlay](hardware/E02_INTEGRATION.md), the [live calibrated writer display](hardware/readout/README.md), and [commissioning tools](hardware/commissioning/README.md). These add the actual captive screw/connectors, stops, retainers, guard and compact exciter mount, with a distinct current geometry and electrical configuration. M03/E01 remain preserved design checkpoints.

**Physical v1 tuning registration is blocked for the supplied removable writer.** Its inline force cell is unloaded after disconnection, so it cannot supply the v1 post-disconnection clay-force/relaxation features. The [return handoff](docs/handoffs/M04_Return_to_Review_Hidden_Math_20261024.md) and [versioned protocol amendment draft](experiments/M04_PROTOCOL_AMENDMENT_DRAFT.json) put force measurement before the manual changeover and reserve a transfer/settling interval. The draft has not replaced the other session's v1 core. Software replay is executable; the physical port, timing and calibration claims remain unqualified.

This repository contains the clay/string/hydrophone physical design, the recovered Dyletsky engines, their Fusion decision integration, and a signal-computing and acquisition workbench. The preserved M03 precursor uses a 600 × 360 mm base, four dry strings, a clay-controlled bridge, a vented water cell and hydrophone, and a separate slow force/displacement instrument. Its manual writer widens the earlier 320 mm base; the original packet remains unchanged. Conditioning, filtering and computer hardware occupy an adjacent dry bench. No physical instrument has been assembled or calibrated by these software replays.

The current physical-build workstream starts at [hardware/README.md](hardware/README.md): revised M03 assembly/fabrication geometry, a sourced candidate electrical chain, staged calibration, a stationary genuine-Dyletsky probe, opt-in duplex PCM capture, raw clock-marker replay, and canonical raw-run sealing. The [experiment interface](hardware/calibration/experiment_interface.json) and [handoff to Review Hidden Math](docs/handoffs/Physical_Build_to_Review_Hidden_Math_20261024.md) keep the physical build aligned with the other session's task and success criteria. The earlier packet below is preserved unchanged.

Start with the [13-page engineering design](docs/reports/Fusion_Instrument_Design.pdf), the [top-view drawing](docs/reports/Fusion_Instrument_Top_View.png), and the [CAD source](design/fusion_design/src/Fusion_Instrument_Layout.scad). The complete source/evidence packet is preserved under [design/fusion_design](design/fusion_design/), including the passive model, source audits, original Dyletsky code, exact replay records and cross-session handoff. The original ZIP deliverables are retained in [archives](archives/).

## Run the computing side

The new `instrument` package uses Python 3.10 or later and only the standard library. It renders labelled scores into reproducible common-input PCM WAV files, jointly fits measured multitone amplitude/phase, preserves slow mechanical baselines and signed work, and analyzes hash-bound raw-run manifests. Windows users can run `run_instrument.bat`.

```bash
python -m unittest discover -s tests -v
python -m instrument demo --output-dir results/instrument_demo
python -m instrument render design/fusion_design/dyletsky/output/instrument_score.json --wav results/drive.wav --output results/drive.json
python -m instrument analyze-run results/instrument_demo/run.json --output results/analysis.json
python -m instrument bench-demo --output-dir results/synthetic_bench_001
python -m instrument probe design/fusion_design/dyletsky/output/instrument_plan.json --output-dir results/probe_001
python -m instrument capture results/probe_001/probe.json --output-dir results/capture_001
```

The original demo generates explicitly synthetic three-channel WAV and slow CSV records at four actual recovered Dyletsky tuning targets. The bench demo also exercises clock drift, marker replay and canonical sealing. Both compare recovered complex ratios with known synthetic gains and phases. `capture` defaults to a dry-run with no device access. Actual acquisition requires the optional audio dependency, an explicit duplex device and commissioning ID, and `--execute`; hardware operation remains unverified. The [computing documentation](docs/INSTRUMENT_COMPUTING.md) gives the real-recording commands, mathematics and interpretation limits. [Saved receipts](receipts/instrument_demo/) preserve the earlier replay results; generated raw files can be reproduced under `results/`.

## Exact decision and memory workbench

The parallel session's `computing` package is also merged here. It supplies grouped experiment planning, qualified finite-model decisions, rational finite-hold memory enclosures and a raw acquisition auditor. Its archived music command is a distinct 36-row, twelve-pitch-class comparator with explicit enharmonic aliasing. Strategy labels and equal-temperament behavior are not interchangeable with the recovered v6/Gen2 engines.

```bash
python -m computing demo --output-dir results/computing_demo
python -m computing plan examples/object_contract.json
python -m computing decide examples/object_contract.json examples/transcript_low_memory.json
python -m computing memory examples/memory_hold.json
python -m computing music --strategy diatonic_thirds --score examples/score_events.json > results/proxy_music.json
python -m instrument render results/proxy_music.json --score-key score --wav results/proxy_drive.wav --output results/proxy_drive.json
```

Canonical `fusion.run/1` raw records use the shared auditor and can enter the new signal analysis with an explicit tone/window configuration. The compact standalone demo uses `hydrophone.signal-run/1`. Score timing/amplitude aliases are reconciled explicitly; contradictory values reject. The [integration notes](docs/INTEGRATION.md) explain these boundaries.

## Clay-history tuning experiment

The shared [experiment core and run instructions](experiments/clay_tuning_v1/README.md) fix one E4 decision: HOLD or retune upward by 5 cents, then score an independent future pitch window. The new `evaluation` package freezes development-only policies and a randomized confirmation schedule, enforces single-action episode records, separates measurement and sampling uncertainty, and compares memoryless, preparation-log and same-measurement digital baselines. It reports useful information and measurement cost separately. The [mathematical limits](docs/HISTORY_TUNING_MATH.md) include the linear-SLS observability null and a history-linked action test.

```bash
python -m evaluation demo --output-dir results/evaluation
python -m evaluation probe --wav results/history_probe.wav --output results/history_probe.json
python -m evaluation observability --output results/history_observability.json
```

The positive fixture stipulates useful material-to-pitch coupling; three null fixtures must fail. All are synthetic. A qualified [hardware binding](experiments/clay_tuning_v1/hardware_binding_template.json), actual calibration/readout evidence and registration before confirmation remain necessary. The [return handoff to the physical session](docs/handoffs/Review_Hidden_Math_to_Physical_Build_20261024.md) aligns this core with M03, including its provisional motion/force ceilings and separate full/reduced command bindings. No physical utility or total-time saving has been demonstrated.

## Dyletsky and shared Fusion decisions

Both recovered engines are executable and preserved separately: v6 has 37 interval rows and Gen2(3) has 43. Their spelling rules, bases, target cents and style weights differ. All thirteen v6 and eight Gen2 static strategies were checked against independent exact rational solutions and augmented least squares. Seventeen pitch labels and eight software voices feed one common exciter input; the four physical strings remain manually tuned. Source musical energy is not mechanical energy in joules.

```bash
node design/fusion_design/dyletsky/dyletsky_runner.mjs
node design/fusion_design/dyletsky/verify_extraction.mjs
python design/fusion_design/dyletsky/fusion_bridge.py --score design/fusion_design/dyletsky/output/instrument_score.json
python verify_all.py --node node --numerical
```

The final command also runs optional independent algebra and passive-model calculations, requiring NumPy, SciPy and Matplotlib. The core Python signal workbench does not require these packages. Open the [single-file audition](design/fusion_design/dyletsky/output/Dyletsky_Fusion_Audition.html) locally for the recovered Web Audio note synthesis. Its mocked graph/syntax check passed; actual browser playback remains unverified.

The other session's unchanged [Fusion decision engine](design/fusion_design/dyletsky/recovered_fusion/fusion_engine.py) passes its 600-check archive replay. Its new bridge consumes the genuine Dyletsky targets with explicitly synthetic observation/action tables. A common acceptable correction can remain available when several states are unresolved. Those exact conditional decisions do not establish measured sensor savings, a physical speedup or a validated clay-state model. The earlier [fusion research report](docs/reports/Fusion_Research.html) and [shared handoff](design/fusion_design/Fusion_Physical_Integration_Handoff_20261024.json) preserve their evidence boundaries.

## Physical evidence boundary

Audio reports are uncalibrated digital channel ratios. Slow force/displacement reports preserve absolute baselines and signed writer-port work, with optional outward sample-error enclosures. Neither audio residual RMS nor path-work area automatically certifies a material parameter, error bound, memory state or dissipation. The software rejects clipped or unresolved tone fits, invalid clocks/values, raw-file digest mismatches and unsafe manifest paths. Physical readiness remains false and zero hardware commands are issued.

Calibration, actual dynamic input-force measurement, installed clock qualification, material history coverage, probe disturbance and actuator envelopes remain physical work. The new opt-in calibration reference utility rejects disabled templates and distinguishes pressure/voltage, pressure/acceleration and pressure/force; it has no completed physical calibration to apply. The five research repositories have defined service interfaces in the design packet; live bindings are not claimed. The initial parallel-session README is retained verbatim in [the source snapshot](docs/source_snapshots/INITIAL_README.md), alongside the now-merged computing workbench. New signal work uses a separate namespace, and the earlier design ZIP/PDF remain archived.
