# M03 physical prototype and acquisition release

The current build extends this preserved checkpoint with [M04 completion](mechanics_completion/README.md), [E02 electrical changes](E02_INTEGRATION.md), the [live writer readout](readout/README.md) and [commissioning procedures](commissioning/README.md). Use those current dimensions, parts and configuration identifiers together. The [task adapter](task_adapter/README.md) binds actual raw records to the mathematical session's feature definitions, but blocks the M04 detached writer cell as a permanent clay-force port. The [amendment draft](../experiments/M04_PROTOCOL_AMENDMENT_DRAFT.json) is awaiting a versioned mathematical/physical protocol decision before confirmation.

This is the construction and commissioning workstream for the combined clay, string, water-cell, hydrophone and Dyletsky instrument. The immutable earlier design/evidence packet remains in `design/fusion_design/`. The M03 mechanics here supersede its assembly coordinates where explicitly stated. No assembly, calibration, hardware capture or retained-material-memory experiment has been performed by these software checks.

M03 has a 600 × 360 mm base, widened from the earlier 320 mm design to fit the captive manual writer. The external interface, conditioning, filter, supplies and computer remain on an adjacent dry bench. The complete current bench system is unquoted; the earlier package's planning budget does not price this revised sourced metrology chain. Candidate part selection is not availability confirmation or a purchase.

Start with `mechanics/README.md` and its dimensioned drawing, then `electronics/README.md` for the candidate parts and electrical connections. `calibration/README.md` supplies the commissioning sequence and `calibration/experiment_interface.json` supplies the measurement conditions that the mathematical task must consume. Hardware is not released for a numerical travel/force setting merely because its parts have been selected: the independent installed-system checks in those documents remain necessary. All mechanical limits below are provisional engineering commissioning ceilings, not certified ratings.

The build starts with four manually tuned dry strings and a single common exciter. A captive manual screw writes the clay while the water rod is disconnected; an inline bidirectional force sensor and independent position sensor retain the writing-port history. The reader is the indexed bridge/rod/diaphragm path with separate hydrophone and bridge-acceleration sensing. Initial writing stops at the first of 5 N or 0.25 mm; possible larger envelopes require the mechanics checks. Initial reading stays below 10 micrometres of actually measured diaphragm motion about its wet equilibrium. A DAC number cannot enforce that displacement. Mechanical stop adjustment, amplifier limits and direct observations govern commissioning; Python is not an emergency-stop or real-time displacement interlock.

Acoustic operation on the assembled water path remains blocked until dynamic diaphragm/boss motion has a qualified bound. The proposed 50 Hz slow laser cannot measure its motion near 300 Hz, and bridge acceleration is a different mechanical port. Use an independently calibrated dynamic displacement/vibration measurement or a verified bridge-to-diaphragm transfer with uncertainty. Nominal optical resolution and a low digital command do not close that gate.

## Executable probe and capture path

The common baseline channel order is IN1 hydrophone, IN2 bridge acceleration, IN3 electrical command loopback and IN4 external slow-logger sync marker. OUT1 carries the excitation and OUT2 is silent. A compatible single duplex device must expose all four input channels and two output channels to the selected PortAudio host API; its manufacturer channel count alone does not establish that OS/driver configuration. Record and verify the physical mapping before connecting the exciter. Audio inputs share one selected device stream; slow force/position samples keep their separate native logger clock. Electrical loopback is voltage-like information, never force. The minimum build has no dynamic force transducer at the vibrating bridge.

All commands except explicit device listing and `capture --execute` run without the optional audio dependency. Run from the repository root. Use a new output directory each time; command, capture and sealed run directories are deliberately not overwritten.

```bash
python -m instrument probe design/fusion_design/dyletsky/output/instrument_plan.json --output-dir results/probe_001
python -m instrument capture results/probe_001/probe.json --output-dir results/capture_001
python -m instrument bench-demo --output-dir results/synthetic_bench_001
```

The first command compiles the genuine C/D/E/G recovered Gen2 targets into a stationary, PCM16 stereo probe, not a varying musical score. The default has one second of silence, eight seconds of faded multitone stimulus, then one second of silence. Its declared fitting window excludes the first and last second of stimulus; actual settling must still be checked. The digital peak ceiling defaults to 0.01 full scale and is not a calibrated force/travel ceiling. The second command is a dry-run: it neither imports the audio driver nor creates an output directory. The third creates an explicitly synthetic full file replay, including nonzero DAC/ADC clock drift, raw marker replay, sealing and known complex gain recovery. It is not a mechanical simulation or a physical measurement.

After the installed hardware has passed the documented commissioning checks, an operator can install the optional dependency, identify the actual duplex device index, then use the explicit execution form. These commands are available for a future operator; no device execution formed part of this repository release.

```bash
python -m pip install -r hardware/requirements-capture.txt
python -m instrument devices
python -m instrument capture results/probe_001/probe.json --output-dir results/capture_001 --device 7 --commissioning-id YOUR_COMPLETED_RECORD_ID --execute
```

The device index above is illustrative. The acquisition callback fills every output buffer, saves bounded PCM input, preserves host ADC/DAC timestamps as diagnostics, records all reported stream flags, and retains partial/flagged captures for review. A flagged capture has an unknown lost-sample count; it cannot be sealed as a clean run. Absence of reported flags is not independent proof of physical sample continuity. Python callback timing has not been measured on the target computer, and real driver/format support remains unverified. All gain/phantom/attenuator settings and protective amplifier controls are physical configuration records.

## Join clocks and raw records

The slow logger records force, position and its physically sampled sync marker on its native scan clock. Preserve the native count/voltage file and its calibrated SI derivative. The canonical slow CSV requires `logger_time_s,force_N,displacement_m`; optional stage and temperature fields survive the raw file. A 50 scans/s logger does not provide microsecond edge precision: its picking allowance must cover scan spacing, channel skew, threshold/interpolation behavior and conditioning delay unless independently characterized. USB packet arrival time is not sample time.

The T7's within-scan channels are sequential and the force/laser paths include separate physical filters. Record these sample offsets and transfers in `slow_pairing`; a marker clock map does not remove their delays. SI derivative rows must use a validated time-pairing method or an explicitly settled-hold scope. The sampled path-work calculation is arithmetic on supplied pairs, not proof that uncorrected filtered channels measured the same physical epoch. `electronics/t7_capture.py` preserves raw voltages and stream gaps; it deliberately does not apply nominal force/length conversion.

Use at least three paired electrical markers spanning the measurement. For logger/ADC timing, record its physical marker on both logger and audio IN4, then save `logger_markers.csv` with `logger_time_s,audio_time_s`. The separate drive/ADC map must come from the electrical command loopback on IN3, not the external logger markers. The `align-drive` command below extracts three command-template anchors and checks their ambiguity; it needs the optional alignment dependencies. Manual independently reviewed markers are also accepted as `drive_markers.csv` with `drive_time_s,audio_time_s`.

```bash
python -m instrument clockfit results/logger_markers.csv --source-key logger_time_s --error 0.03 --source-pick-error 0.02 --audio-pick-error 0.0001 --method "recorded physical sync edges, declared scan and conditioning allowance" --output results/logger_clock.json
python -m pip install -r hardware/requirements-alignment.txt
python -m instrument align-drive results/capture_001/probe.json results/capture_001/multichannel_audio.wav --loopback-channel 2 --min-delay 0 --max-delay 0.25 --error 0.001 --output-dir results/drive_alignment_001
```

The example timing allowances and delay search range are declarations to replace with supported values, not certified uncertainties. The matcher uses known command onset, midpoint and offset templates; it rejects clipped/unresolved input, weak matches, search-boundary peaks and ambiguous competing delays. It reports integer-sample anchors, not invented fractional-sample precision. Analog filtering can bias a correlation delay and requires independent checking. Clock JSON must be stored beside its raw marker CSV. The fit uses exact rational least squares, checks at least three increasing marker pairs and rejects a declared error smaller than observed residual plus declared picking allowances. Marker residuals cannot bound unsampled between-marker clock deviations; the stated affine map and bound remain assumptions to validate. The seal step replays the actual marker bytes, rejects edited maps, and preserves both marker CSVs. Its analysis window stays inside measured clock brackets and the actual slow sample support; declared maximum slow sample gaps are checked. DAC/ADC drift changes both the window and the tone frequency used in the ADC-domain fit.

Copy `operator_metadata.template.json`, fill its identity/configuration/conditions, and supply installed gain declarations and the largest permissible slow sampling gap. For physical records, replace its unfilled status, identify the setup and retain native raw slow files through relative path/SHA256 records in `native_slow_raw_files`. Explicitly label unavailable/not-applicable conditions; a nonempty declaration is not evidence of its truth. The seal requires the native slow evidence and copies it into the run directory. The template is not calibration evidence. Then seal the audio capture, imported slow CSV, independent clocks and operator record into one canonical `fusion.run/1` directory.

```bash
python -m instrument seal results/capture_001/capture.json --slow results/slow_force_displacement.csv --metadata results/operator_metadata.json --logger-clock results/logger_clock.json --drive-clock results/drive_alignment_001/drive_clock.json --output-dir results/run_001
python -m instrument analyze-run results/run_001/run.json --output results/run_001/analysis.json
```

The sealed directory preserves raw WAV/CSV bytes, command, probe, capture record, operator record, both marker files and clock fits; hashes bind the canonical manifest and provenance. Any final auditor failure leaves `REJECTED_run.json`, not an accepted `run.json`. Analysis produces digital complex channel ratios and sampled slow writer-port work. The optional calibration reference utility supplies SI values only under explicitly scoped calibration records. None of these commands automatically turns features into a certified Fusion observation or sends a tuning/write action. The parallel mathematical workstream must first supply its decision task, admissible action sets, observation uncertainty model and success criteria.

## Verification and implementation sources

Run `python verify_all.py --node node --numerical` for the complete software/evidence replay. Optional numerical dependencies include those already used for the earlier model and algebra checks; `requirements-alignment.txt` covers the new template matcher. The synthetic bench replay and tests deliberately challenge marker tampering, missing slow coverage, clock drift, WAV/frame contradictions, callback flags and dry-run gating.

The capture API follows the upstream [sounddevice raw stream documentation](https://python-sounddevice.readthedocs.io/en/latest/api/raw-streams.html) and [stream/callback documentation](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html), checked 2026-10-24. The callback is a bounded engineering implementation, not a hard real-time guarantee. Its optional version range and driver backend must be recorded during physical commissioning. Manufacturer sources and their applicability limits are maintained in `electronics/` and `calibration/sources.json`.
