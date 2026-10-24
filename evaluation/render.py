"""Use the physical session's renderer for the exact registered probe."""
from instrument.drive import render_score
from .protocol import exact, digest


def render_probe(core, path):
    settings = core["excitation"]
    if exact(settings["attack_release_s"]) != exact("0.005") or any(exact(p) for p in settings["phase_rad"]):
        raise ValueError("Current physical-session renderer requires 5 ms fades and zero phase")
    frequencies = settings["frequencies_Hz"]
    if len(frequencies) != 4:
        raise ValueError("The registered probe has exactly four fixed tones")
    score = {"schema": "fusion.score/1", "engine_id": core["task"]["engine"],
             "strategy": core["task"]["strategy"], "experiment_id": core["experiment_id"],
             "events": [{"event_id": "probe-" + str(i + 1), "spelling": spelling, "octave": 4,
                         "voice": i + 1, "target_Hz": float(exact(value)), "start_s": 0,
                         "duration_s": float(exact(settings["duration_s"])), "source_amplitude": 1}
                        for i, (spelling, value) in enumerate(zip(("C", "D", "E", "G"), frequencies))]}
    result = render_score(score, path, sample_rate=settings["sample_rate_Hz"],
                          peak=float(exact(settings["normalized_pcm_peak"])))
    result["experiment_core_sha256"] = digest(core)
    result["intended_start_s_relative_to_write_end"] = core["timing_s_relative_to_write_end"]["dyletsky_probe_start"]
    return result
