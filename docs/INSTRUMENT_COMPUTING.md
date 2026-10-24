# Physical instrument computing

The implemented path is recovered Dyletsky source to a labelled score, deterministic common-input waveform, hash-bound recorded channels, numerical features and an explicitly qualified decision. The four physical strings are manually tuned resonances. Eight software voices and seventeen spelling labels do not create eight independently driven strings or seventeen independent resonators.

## Reproduce

Run from the repository root with Python 3.10 or later. The signal package uses only the standard library. The archived independent algebra and passive-model replay additionally require the numerical packages listed in the design packet. Node is needed only for regenerating and independently comparing the recovered JavaScript engines.

```bash
python -m unittest discover -s tests -v
python -m instrument demo --output-dir results/instrument_demo
python -m instrument render design/fusion_design/dyletsky/output/instrument_score.json --wav results/drive.wav --output results/drive.json
python -m instrument analyze-run results/instrument_demo/run.json --output results/analysis.json
python verify_all.py --node node --numerical
```

The demo creates three PCM channels at the four actual Gen2 tuning targets and a separate synthetic load/hold/unload/rest CSV. It records their digests and known gain/phase truth. No laboratory recording is invented. The saved receipt in `receipts/instrument_demo/` can be regenerated with the demo command; its raw files are generated under `results/`.

## Waveform generation

`instrument.drive.render_score` renders each event as a sinusoid with a short raised-cosine attack and release. Events superpose into one mono PCM16 input. The complete mix is normalized once to the declared digital peak, with timing, spelling, engine, source amplitude and phase labels retained in the manifest. Rendering the recovered 68-event example at 48 kHz produces 2,069,724 frames, or 43.11925 seconds, with zero rail samples at the default 0.2 peak. The source choir's formants, panning and room are separate from this deliberately controlled excitation adapter; the offline audition retains its original note synthesizer.

A normalized PCM command is not measured force or pressure. Rendering opens no audio device. An amplifier, current limit, actual drive measurement and validated force/travel envelope are still required before driving the object. The output records `hardware_execution_enabled=false`.

## Joint tone analysis

For one selected stationary window, fit every declared frequency simultaneously using a DC column, a centered linear trend and cosine/sine pairs. The implementation uses scaled, column-pivoted Householder QR rather than normal equations. For a fitted pair `a cos(omega t) + b sin(omega t)`, the complex amplitude is `a - i b`; dividing response by drive yields a relative complex channel ratio. The optional bridge reference also gives reference/drive and hydrophone/reference ratios.

```bash
python -m instrument tones recording.wav --frequencies 261.626 292.395733 326.759563 391.125346 --drive-channel 0 --response-channel 1 --reference-channel 2 --start 2 --end 4 --output results/tones.json
```

Rail samples, unresolved denominators, invalid or aliased frequencies, singular fits and unsupported PCM encodings are rejected. Reports include file and selected-PCM digests, window coordinates, channel map, conditioning, fitted DC/trend and residual diagnostics. Absence of rail codes does not rule out analog preamp overload. Residual noise and coefficient diagnostics are not deterministic calibration bounds. Omitted tones, nonlinearities, transients, changing state, clock drift and uncalibrated channel transfer remain possible causes of bias. Choose steady windows explicitly and preserve their relation to the input score.

## Slow mechanics

The CSV requires `time_s`, `force_N` and `displacement_m`, with optional `stage` and `temperature_C`. Timestamps must strictly increase and numbers must be finite. Preserve absolute raw baselines and time since preparation; a detrended acoustic response can erase information about a material's initial state.

The signed sampled writer-port work is `W = sum((F[i]+F[i+1])/2 * (x[i+1]-x[i]))`. It remains a path-work estimate for an open path and may be negative when stored energy returns through the measured port. Closure tests require declared force and displacement tolerances. Geometric and force return do not establish internal-state or thermodynamic closure, and the code never labels this work as identified clay dissipation.

With uniform sample-error declarations `eF` and `ex`, the conservative arithmetic bound adds `eF*abs(delta_x) + 2*ex*abs(Fbar) + 2*eF*ex` over segments. Exact Fraction arithmetic and outward conversion enclose this sampled calculation. Between-sample variation and undersampling are explicitly excluded, so the interval is not automatically a bound on continuous physical work.

```bash
python -m instrument slow slow.csv --position-tolerance 0.000001 --force-tolerance 0.01 --hold-window 1 2 --hold-drift 0.000001 --force-error 0.01 --position-error 0.000001 --output results/slow.json
```

These numbers are example declarations. A hold is eligible only with sufficient samples, a declared window or consistent hold labels, and displacement drift inside its stated tolerance. Reports retain force change, duration and baseline. They do not infer a relaxation time, modulus or persistent memory without a validated model.

## Shared evidence boundary

`instrument.run.analyze_run` consumes the canonical `fusion.run/1` acquisition record through the original `computing.acquisition.audit_run` auditor. Add `analysis.tones` with explicit `frequencies_Hz`, `drive_channel`, `response_channel` and optional `reference_channel`/window; channel labels map through the declared channel map. Original `logger_time_s` values remain in the slow output. The compact standalone layout is separately named `hydrophone.signal-run/1`. Both require a `synthetic` or `physical_measurement` origin declaration, relative raw paths and SHA256 values. It checks file identity and computes the audio/slow features. Calibration, clock and origin metadata remain declarations; digest agreement does not authenticate a laboratory event. Path traversal and mismatched raw bytes are rejected. The output separately records bytes checked, features computed and physical interpretation unqualified.

The recovered Fusion finite-action engine is already connected to actual Dyletsky calibration targets in `design/fusion_design/dyletsky/fusion_bridge.py`. Its synthetic error/action tables are not silently replaced by residual RMS from real recordings. Building that bridge to physical evidence requires validated estimator uncertainty, probe disturbance, material-state coverage and action error. The current code issues zero hardware commands.

The parallel computing music CLI wraps its proxy score under a score key. Use --score-key score when rendering that wrapper. The renderer accepts onset_s/amplitude aliases as well as start_s/source_amplitude and rejects contradictory pairs. It preserves event spelling, source metadata and voice numbering; it does not turn the twelve-class proxy into independent enharmonic tuning.
