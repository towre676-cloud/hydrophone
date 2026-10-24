# Live writer observations

`writer_display.py` supplies the operator display missing from the original batch logger. It consumes the same T7 stream that writes the native voltage CSV, converts signed force and actual plate-position observations through a supplied installed calibration, and shows a large **STOP** message whenever an observation is unqualified. It sends no motor, amplifier or audio command. It is a conditional operator aid, not a force interlock or a hard realtime control system.

The initial absolute limits remain **±5 N** and **±0.25 mm** relative to the installed calibration datum. The display reports the calibrated value, its current error interval, a conservative upper sample age and the declared filter-lag bound. A nominal value below a limit still produces STOP when its uncertainty reaches that limit. The two axes retain their separate sequential sample offsets and filter delays; the code does not make them simultaneous or remove filter lag.

## Run the offline demonstration

```sh
python hardware/readout/writer_display.py --demo --output-dir results/writer_readout_demo
```

The demo uses [writer_calibration.synthetic.json](writer_calibration.synthetic.json) and [writer_session.synthetic.json](writer_session.synthetic.json). Its initial view is within the synthetic observation limits; its final view stops at nominal force 4.94 N and position 0.249 mm because the declared uncertainties reach the limits. Every view says **DEMO ONLY — NO PHYSICAL WRITING**. The demonstration imports no hardware SDK and opens no device. The demo refreshes only its explicitly synthetic environment timestamp; it does not claim a physical temperature measurement.

Running the program with no options prints an offline STOP message. A synthetic record is rejected by the hardware command before the SDK/capture path is loaded.

## Installed calibration and hardware run

Start from the blocked [writer_calibration.template.json](writer_calibration.template.json) and [writer_session.template.json](writer_session.template.json). The physical template selects the current E02 five-channel scan `[AIN0, AIN2, AIN4, AIN6, AIN8]`; E01's four-channel scan is also supported when explicitly recorded. E02's additional `raw_temperature_V` is retained without inferring Celsius from a nominal sensor slope. The force/position display currently uses the independently measured temperature interval and measurement time in the session record. The session expires after the calibrated environmental hold interval. It must not be refreshed without a new observation.

An enabled physical record needs status `measured_with_declared_scope` and evidence type `physical_calibration_declared`. Changing those strings is not a calibration procedure. The program checks declarations and consistency; it cannot authenticate reference measurements or establish a uniform error bound from finite reference points. In particular, a fit residual, manufacturer tolerance or ADC code size cannot replace `total_error_SI` and its independent `uniform_bound_justification_id`.

The record and session must identify the installed ADC, force sensor, position sensor, mechanics, filter configuration and complete signal chains. Both signed load directions must be qualified. The declared excitation domain is checked against every observed AIN6 voltage. The independently measured temperature interval, calibration dates and environmental observation age are checked continuously. The start callback checks the actual opened T7 serial, accepted scan rate and channel/range/resolution/read-block configuration against the record. External sensor and filter identity checks remain operator-declared evidence.

Only after the installed reference, timing, filter, load-direction and motion qualifications have been completed:

```sh
python hardware/readout/writer_display.py --execute --identifier ACTUAL_NUMERIC_T7_SERIAL --profile E02 --calibration measured_writer_calibration.json --context installed_writer_session.json --duration 30 --output-dir results/writer_run_001
```

The program uses the existing optional LabJack native LJM installation/Python wrapper through [the T7 capture adapter](../electronics/t7_capture.py). It does not install software. The main thread owns capture and normal Ctrl+C cleanup; a separate watchdog renders every 0.2 seconds, including when a device read blocks. Display scheduling, the host OS, stdout and SDK calls have no guaranteed realtime deadline. A stalled display cannot protect the specimen. The operator's qualified hand-step/check/dwell procedure and mechanical limits remain necessary.

Use a new output directory for every run. A STOP after samples arrive latches for the rest of that run; later valid samples cannot silently restore an in-range display. Finish the capture, investigate the cause and begin a new run. When acquisition ends the screen says STOP even if the last observation was in range. The program never emits a command authorizing manual advancement.

## What the live error interval means

For each role the installed signed affine model is

\[
q=(V-V_0)s.
\]

`total_error_SI` bounds the complete static installed measurement chain over the declared raw/SI, direction, temperature and excitation domain. It already includes the ADC/raw-voltage contribution. `raw_error_bound_V` additionally guards calibrated voltage-domain edges and headroom; it is not added to the static error a second time.

Fresh USB delivery is not sample freshness. For sample index \(n\), actual accepted nominal scan rate \(r\), calibrated lower clock factor \(k_-\), first-scan lower offset \(b_-\), channel offset \(d\) and channel-offset error \(e_d\), the earliest admissible host acquisition time is

\[
t_-=t_{\mathrm{start,call,before}}+b_-+(n/r)k_-+d-e_d.
\]

The capture adapter records host times immediately before and after `eStreamStart`; these call brackets alone do not qualify the first-scan origin or clock rate. The record's independent clock-origin evidence and factor interval are mandatory. An old scan arriving in a new callback retains its old index-derived age. Nonzero device or library backlog also produces STOP. A clock map that puts the earliest sample in the future is inconsistent and produces STOP.

At display time \(t\), the current error used for the limit check is

\[
E_{\mathrm{current}}=E_{\mathrm{static}}+v_{\max}\,[\max(0,t-t_-)+\tau_{\max}].
\]

Here `max_abs_slew_SI_per_s` is an independently qualified continuous-time variation bound at the measured port, and `filter_lag_bound_s` is an independently qualified channel-lag bound for that same motion domain. A nominal group-delay number at one frequency does not supply this bound. If those bounds or their evidence are missing, the display stays STOP. This does not prove that the operator obeys the declared motion domain. An excessive observed between-sample change can falsify the slew declaration and stop the display; passing that check cannot bound unobserved motion between samples. The display is suitable only for its qualified slow writing scope, with acoustic drive disabled.

The software uses exact rational arithmetic on the supplied decimal representations for the affine conversion, clock interval, current-error model and limit comparisons. It rounds reported interval endpoints outward and includes rounding of the nominal display value in the reported symmetric error. This arithmetic does not make a supplied physical error bound true. A bound may be supplied as a decimal string to preserve digits beyond binary float precision.

The limit decision is STOP if \(|q|+E_{\mathrm{current}}\geq L\), either current interval leaves its calibrated SI domain, a raw-voltage interval reaches a calibrated headroom edge, sample age exceeds its qualified maximum, data contain a sentinel/gap/nonfinite value, or any identity/domain/timing check fails. The position measurement is the actual plate target; upstream hand-stage travel cannot replace it.

## Tare and provenance

The optional API call `set_display_tare(operator_note)` saves the current raw row, absolute calibrated values, calibration identity and note as an informational relative display reference. It requires a fresh in-range observation. It does **not** change `zero_raw_V`, native voltages, absolute SI samples or either limit. The CLI never silently zeroes either channel. Changing the physical/calibration datum requires a new documented reference and reviewed calibration record.

Each hardware run writes `native/` through the original T7 adapter and a separate `readout/` containing `writer_observations.csv` and `writer_readout.json`. The derivative CSV retains sample index, native `logger_time_s`, original force/position/excitation/optional temperature voltages, qualified SI values, current error, age, status and pairing identity. An unqualified raw/SI domain has blank SI columns. No interpolation, sample-time shift, filter deconvolution or re-zeroing is applied. The report retains the complete supplied calibration/session, canonical JSON hashes, native start/end events, native raw-file hashes from the capture receipt, derivative hash and STOP/tare history. Preserve all native files alongside the derivative; the display does not convert writer-port work into clay dissipation.

The observer contract is `WriterReadout.observe(event)`, also available by calling the object directly. Events have schema `hydrophone.t7-observation/1` and kinds `start`, `block` or `end`, as emitted by the T7 adapter. The `snapshot()` method lets a separate watchdog evaluate age even without callbacks. `render_terminal(snapshot)` creates the human-readable display. `close()` flushes the derivative and writes the provenance report. A physical live display and complete reference procedure must be qualified on the actual assembled fixture before any write; no physical measurements or device commands have been performed in this workstream.

## Offline verification

```sh
python -m unittest discover -s hardware/readout -p 'test_writer_display.py' -v
```

The tests include known affine values and independent age/error arithmetic, decimal-bound perturbations, fresh callbacks containing old scans, watchdog expiry, uncertainty reaching limits before nominal values, gap/backlog/clipping/domain rejection, signed-direction and temperature scope, E02 raw-temperature preservation, tare invariance, synthetic hardware rejection and integration through the actual T7 adapter with a mocked SDK. They do not establish a physical timing or measurement bound. [writer_calibration.schema.json](writer_calibration.schema.json) describes nullable blocked/proposal records; `validate_calibration` is the stricter enabled-run validator.
