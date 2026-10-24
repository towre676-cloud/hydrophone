# Hydrophone fusion instrument

This repository contains the clay/string/hydrophone physical design, the recovered Dyletsky engines, their Fusion decision integration, and an offline signal-computing workbench. The proposed object uses a 600 × 320 × 240 mm frame, four dry strings, a clay-controlled bridge, a vented water cell and hydrophone, and a separate slow force/displacement instrument. No physical instrument has been assembled or calibrated by these software replays.

Start with the [13-page engineering design](docs/reports/Fusion_Instrument_Design.pdf), the [top-view drawing](docs/reports/Fusion_Instrument_Top_View.png), and the [CAD source](design/fusion_design/src/Fusion_Instrument_Layout.scad). The complete source/evidence packet is preserved under [design/fusion_design](design/fusion_design/), including the passive model, source audits, original Dyletsky code, exact replay records and cross-session handoff. The original ZIP deliverables are retained in [archives](archives/).

## Run the computing side

The new `instrument` package uses Python 3.10 or later and only the standard library. It renders labelled scores into reproducible common-input PCM WAV files, jointly fits measured multitone amplitude/phase, preserves slow mechanical baselines and signed work, and analyzes hash-bound raw-run manifests. Windows users can run `run_instrument.bat`.

```bash
python -m unittest discover -s tests -v
python -m instrument demo --output-dir results/instrument_demo
python -m instrument render design/fusion_design/dyletsky/output/instrument_score.json --wav results/drive.wav --output results/drive.json
python -m instrument analyze-run results/instrument_demo/run.json --output results/analysis.json
```

The demo generates explicitly synthetic three-channel WAV and slow CSV records at four actual recovered Dyletsky tuning targets. It compares the recovered complex ratios with known synthetic gains and phases. The [computing documentation](docs/INSTRUMENT_COMPUTING.md) gives the real-recording commands, mathematics and interpretation limits. [Saved receipts](receipts/instrument_demo/) preserve the replay results; generated raw files can be reproduced under `results/`.

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

Calibration, actual drive measurement, clock alignment, material history coverage, probe disturbance and actuator envelopes remain physical work. The five research repositories have defined service interfaces in the design packet; live bindings are not claimed. The initial parallel-session README is retained verbatim in [the source snapshot](docs/source_snapshots/INITIAL_README.md), alongside the now-merged computing workbench. New signal work uses a separate namespace, and the earlier design ZIP/PDF remain archived.
