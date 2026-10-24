"""Create explicit synthetic raw records for the acquisition audit CLI.

These waveforms demonstrate the file interface, not the instrument physics.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import wave


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    rate, count = 8000, 2000
    channels, drive = [], []
    for i in range(count):
        t = i / rate
        envelope = math.sin(math.pi * i / count) ** 2
        u = int(5000 * envelope * math.sin(2 * math.pi * 196 * t))
        drive.append(u)
        channels.extend([int(4000 * envelope * math.sin(2 * math.pi * 261.625565 * t)),
                         int(0.6 * u), int(0.3 * u), u])
    for name, values, channel_count in (("multichannel_audio.wav", channels, 4),
                                         ("drive_command.wav", drive, 1)):
        with wave.open(str(output / name), "wb") as stream:
            stream.setnchannels(channel_count)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(struct.pack("<" + "h" * len(values), *values))
    slow_name = "slow_force_displacement.csv"
    with (output / slow_name).open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["logger_time_s", "force_N", "displacement_m", "temperature_C"])
        for i in range(6):
            t = i / 20
            writer.writerow([str(t), str(0.1 + 0.32 * math.exp(-t / 10)), "0.001", "20"])
    def record(name):
        return {"path": name, "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
    run = {"schema": "fusion.run/1", "run_id": "synthetic-interface-example",
           "specimen_id": "NO_PHYSICAL_SPECIMEN", "data_origin": "synthetic",
           "history_protocol": "synthetic-nonphysical-waveform-example",
           "calibration_id": "SYNTHETIC_ONLY", "validity_domain": "interface demonstration only",
           "raw_files": {"multichannel_audio": record("multichannel_audio.wav"),
                         "slow_force_displacement": record(slow_name),
                         "drive_command": record("drive_command.wav")},
           "audio": {"sample_rate_Hz": rate,
                     "channel_map": ["string_raw", "bridge_raw", "hydrophone_raw", "drive_reference_raw"],
                     "gain_per_channel": [1, 1, 1, 1], "missing_samples": 0},
           "sync": {"offset_s": "0", "drift_rate": "0", "sync_residual_s": "0",
                    "method": "synthetic shared generation clock",
                    "drive_to_audio": {"offset_s": "0", "drift_rate": "0", "sync_residual_s": "0",
                                       "method": "synthetic shared generation clock"}}}
    (output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    return output / "run.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results/acquisition"))
    args = parser.parse_args()
    print(generate(args.output_dir))
