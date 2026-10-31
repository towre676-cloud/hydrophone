# The Unfinished Song — Adaptive Orchestral Book I

An original coordinated score for **Ash & Aether: Clay and Water**, composed and rendered with Hydrophone's existing sampled orchestral infrastructure. The October 24 chamber symphony and *The Water Remembers* suite remain intact.

**30 scored arrangements, 90 delivery stems, 24 seamless loop arrangements, 15.36 minutes of distinct loop material.** Each environment has three transformations; each transformation contains three synchronized stems. Layer combinations are arrangements of that material, not additional claimed minutes of composition.

| Gameplay family | Original cue | Lead and color |
|---|---|---|
| Exploration | Roads That Remember | Flute and harp |
| Settlement | Lanterns at the Kiln | Oboe and harp |
| Interior | Letters by the Stove | Clarinet and celesta |
| Dungeon | The Well Below Names | Bassoon and harp |
| Atmospheric | A Sky of Unspoken Things | Flute and celesta |
| Combat | Clay Against Iron | Violin, viola and timpani |
| Boss | The Furnace Remembers | Horn, trombone and timpani |
| Victory | A Name Returned | Trumpet and harp |

Ash, Water and Aether themes share D modal minor. The variations use retrograde, contour inversion, exchanged answers, harmonic rotation, octave changes and a second-half thematic exchange. Six finite cues provide victory, boss arrival, rest, revelation, chapter ending and combat exit, with resolved final melodic notes and retained release tails. This is an authored composition grammar; it does not re-ingest the corpus or copy source melodies.

## Files and reproduction

- `audio/`: stereo 32 kHz Vorbis game delivery; `masters/`: PCM16 lossless FLAC stems.
- `scores/`: complete editable performed-event scores; `midi/`: portable GM MIDI.
- `manifest.json`: sample clocks, stems, SHA256 digests, themes, intensity layers, transition policy and gameplay rules.
- `validation.json`: decoded sample counts, peaks and loop seam checks.
- `transition-validation.json`: all 552 directed arrangement pairs at all 16 bar positions, plus every event overlay on every loop.
- `audition.mp3`: eight environments joined into a listening sequence.
- `build-receipt.json`: source hashes, dependency versions and rebuild commands.
- `integration/aa/` at repository root: tested Web Audio transport, integration instructions and listening-room source.

From the repository root, with Python, NumPy, ffmpeg and the pinned FluidSynth assets:

```sh
python -m pip install -r symphony/requirements.txt
python assets/symphony/fetch_soundfont.py --native-linux
python -m symphony.adaptive
python -m symphony.adaptive.validate
python -m symphony.adaptive.reproduce
python -m symphony.adaptive.measure_delivery
python -m unittest discover -s tests -p 'test_symphony*.py'
python -m unittest discover -s tests -p 'test_adaptive_score.py'
node --test integration/aa/orchestral-soundtrack.test.mjs
```

The exact score grammar is deterministic. Delivery encoding uses ffmpeg bitexact flags. A repeated encode is checked for byte identity; the receipt pins the tested rendering environment. Cross-platform native library differences can change synthesized PCM and therefore asset hashes. No corpus acquisition is needed.

The live mobile game can use a smaller Vorbis quality-2 delivery profile built with `python -m symphony.adaptive.deploy --output-dir PATH`. This derives from the same retained lossless masters and carries a separate manifest and decoded-audio validation. The complete package retains quality-5 delivery and lossless masters.

## Musical and technical loop contract

Every loop is 16 bars in 4/4 at 100 BPM: **38.4 seconds / 1,228,800 stereo frames**. Bed, theme and motion start on the same audio clock. The complete five-second synthesized release tail is folded into the next cycle. A 128-frame periodic boundary correction removes the remaining sample discontinuity without inserting a silent gap. The source renderer's room, sampled articulations, section layering, per-note expression and vibrato are retained. The adaptive score uses equal temperament and a fixed ensemble pulse so all stems stay aligned.

Full-intensity sums target −23 LUFS, with shared gain across stems so balancing survives layering. The manifest retains actual loudness and true-peak readings. Individual stems are deliberately not normalized independently. Calm reduces motion and leaves the melody quieter; alert adds motion; danger restores the complete orchestration. Linear constant-sum crossfades avoid the correlated-material boost of an equal-power crossfade. Short cues use 0.22 overlay gain.

The runtime plays at most two cycles of one variation before the existing director chooses another. Its remembered history and three-variation pools prevent immediate replay. Manual next, continuous/spacious/ambient pacing, volume, voice ducking, hidden-tab pause and selected full-length performances retain the game's existing controls. Pausing cancels both audible and future scheduled sources and resumes the musical offset. Generation guards reject late downloads. Incoming cues wait for the next bar after their stems have loaded; the 2.4-second bound applies to scheduling after load, not network download time.

## Integration and validation scope

The current A&A source was inspected through its Sites repository. A dedicated transport extends its existing AdaptiveSoundtrack rather than replacing the game's director. Scene selection routes to exploration, settlement, interior, dungeon or atmosphere; battle and boss flags override field selection. Hero HP below 35% and boss flags raise danger intensity. Discovery, victory and story-transition hooks trigger short cues. Listening-room performances remain available through their existing selection path.

The eight-family score includes a victory loop pool for reuse; the current game uses the short victory sting when returning to exploration. The combat-exit and rest cues are available to the adapter; call sites determine whether a particular gameplay rest emits them. Cinematic movies retain their own authored audio and pause the gameplay score.

The automated audio checks establish decoded lengths, measured loudness, seam discontinuities, transition peaks and event-overlay headroom for the tested files. They do not substitute for extended listening on the player's headphones, speakers or device. Browser playback verification and source/deployment receipts are retained separately with the integration.

## Rights and preservation

These are newly authored compositions and generated performances. The renderer uses GeneralUser GS 2.0.3; its license is retained under `assets/symphony/LICENSE-GeneralUserGS.txt`. Retain that notice with redistributed sample-bank assets. Corpus and performance-data provenance remains in the original engine documentation. No source corpus or performance recording is embedded in this package.
