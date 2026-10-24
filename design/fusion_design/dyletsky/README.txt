DYLETSKY / FUSION SOFTWARE INTEGRATION 0.2
24 October 2026

The actual recovered source engines are preserved byte-for-byte in archive/.
v6_core.mjs extracts the 37-row spelled model. gen2_core.mjs extracts the
43-row Gen2(3) model, injecting a seeded random generator for replay.
They have different note orderings, spellings, interval targets and weight
rules. Events join by spelling and explicit basis, never by an assumed index.

Open output/Dyletsky_Fusion_Audition.html for a single-file offline audition
with the recovered original Gen2 Web Audio note synthesizer. There are no
external web dependencies. Its new headless scheduler retains phrase flow,
register-specific solves, note choice and local/phrase memory. It omits
audio-side random consumption, changing modes, room visuals, drone and
percussion. Those source functions are retained in the archive/core.

The score contains 68 generated events over five visited phrase categories,
but only four distinct pitch spellings in this seeded example. Seventeen
labels are available to the model; musical diversity is not established.
An actual browser executable was unavailable for QA. Syntax and every event's
Web Audio graph construction were tested with a mock DOM/audio contract;
that does not establish real-time browser sound quality.

Run from this directory with Node.js >=20 and Python >=3.10:
    python extract_engines.py
    node dyletsky_runner.mjs
    node verify_extraction.mjs
    python verify_algebra.py
    python fusion_bridge.py --score output/instrument_score.json
    python build_audition.py
    node verify_audition.mjs

verify_algebra.py uses NumPy for an independent augmented least-squares
comparison; its exact Fraction/Bareiss reconstruction is separate from JS.
fusion_bridge.py and ordinary replay otherwise use the Python standard library.

The other session's actual Fusion decision engine is copied unchanged into
recovered_fusion/. Its full replay and original manifest were verified.
The integration calls its real optimizer on actual Dyletsky calibration
targets crossed with explicitly synthetic observation/action hypotheses.

Physical plan: one polyphonic common exciter input, four manually tuned dry
strings, measured clay/water response. No automatic retuning, no independent
seventeen-string actuator, no force inferred from digital audio level, and
no physical execution enabled. Material measurements remain to be made.

Important source semantics are in output/engine_audit.json and
output/algebra_verification.json. v6's ET label means uniform weights,
not zero-offset equal temperament. Its m3 labels use augmented-second
spelling and its legacy RMS squares weights. Gen2 averages style weights
within each interval family, discarding pitch-specific locations. Its
musical energy and sampling procedure have no physical-energy or exact
stationary-distribution interpretation established here.
