# Hydrophone fusion instrument

This repository brings the clay/string/hydrophone physical design and its offline computing workbench together. It preserves the engineering packet, CAD, design arithmetic, passive mechanical model, fusion research report, and integration handoff. The proposed object uses a 600 × 320 × 240 mm frame, four dry strings, a clay-controlled bridge, a vented water cell and hydrophone, and a separate slow plunger. No physical instrument has been assembled or calibrated by these computing replays.

The computing package now selects grouped experiments with exact costs and bounded observations, consumes transcripts to make qualified model decisions, propagates material memory through uncertain hold times using rigorous rational exponential bounds, and exports Dyletsky-derived tuning targets and spelling-preserving four-voice score events. It also audits raw multichannel PCM WAV and slow force/displacement CSV records. Everything in the core uses the Python standard library.

## Run the computing workbench

From the repository directory, run:

```bash
python -m computing demo --output-dir results/demo
python -m unittest discover -s tests -v
```

The demo replays the original 600 interval-panel comparisons and 16 grouped-acquisition comparisons, then writes an exact panel plan, memory-hold bounds and numerical tuning results. Tests additionally compare branch-and-bound plans with exhaustive optima, independently check exponential enclosures, validate score spelling/timing, and exercise real WAV/CSV parsing. Windows users can also run `run_computing.bat`.

```bash
python -m computing plan examples/object_contract.json
python -m computing decide examples/object_contract.json examples/transcript_low_memory.json
python -m computing memory examples/memory_hold.json
python -m computing music --strategy diatonic_thirds --strings examples/four_strings.json --score examples/score_events.json
```

The four-string numbers are illustrative declarations, not measured tensions or approved commands. The tuning solver has twelve pitch-class offsets; its score exporter preserves all seventeen supported spellings and explicitly records the enharmonic aliasing. Four selected physical strings do not realize eleven independent tuning controls. Manual tuning and its timing remain unqualified.

## Physical design and prior work

Start with [the engineering design PDF](docs/reports/Fusion_Instrument_Design.pdf), [the top-view drawing](docs/reports/Fusion_Instrument_Top_View.png), and [the OpenSCAD source](design/fusion_design/src/Fusion_Instrument_Layout.scad). The complete other-session design packet is preserved under `design/fusion_design/`, including its repository audit, interfaces and illustrative passive model. Its optional NumPy/SciPy/Matplotlib dependencies are separate from the dependency-free computing core.

The earlier [fusion research report](docs/reports/Fusion_Research.html) and [integration handoff](docs/reports/Integration_Handoff.html) retain their original dates and evidence limits. The three original ZIP deliverables remain in `archives/`. Some earlier handoff fields say drawings were unavailable at that checkpoint; the newer design packet is now included here. [The integration notes](docs/INTEGRATION.md) identify the current shared boundary.

## Raw acquisition interface

```bash
python examples/create_synthetic_run.py --output-dir results/acquisition
python -m computing audit-run results/acquisition/run.json
```

This produces explicit synthetic WAV/CSV examples and validates their bytes, digests, sample rates, channel map, full-scale samples, slow timestamps, and declared clock overlap. It does not authenticate a laboratory event, pressure calibration, actual clock synchronization or the fitted physical model. A physical run must preserve the raw slow baseline and waveforms: incremental transfer features can hide initial material memory.

## Computing scope

The exact experiment planner works on a declared finite hypothesis population, tri-state action evidence, grouped acquisition costs, and rectangular outer observation bounds. A successful result covers that model. Unknown actions, missing bounds and out-of-model readings remain explicit. Obstruction generation is still exponential; the branch-and-bound search reduces the panel-search burden without claiming general polynomial scaling.

All current outputs mark physical readiness false and issue zero hardware commands. Drivers, calibration, actuator envelopes, finite probe-disturbance models and live external-repository bindings remain outstanding. [Computing documentation](docs/COMPUTING.md) describes the implemented mathematics and limitations.
